"""
runtime_coordinator.py — Orchestrateur des cycles d'exécution (B-01)

Remplace la boucle while True centralisée d'advisor_loop.py via le pattern strangler.
Coordonne le cycle : signal → intelligence → decision → risk → execution → learning.

Garanties :
  - Aucune décision orpheline : cycle interrompu → decision = None
  - Timeout par couche : une couche lente n'immobilise pas le cycle
  - Chaque cycle porte un cycle_id signé
  - Le résultat est publié sur SystemStateBus après chaque cycle

Pattern strangler :
  coordinator.register_layer("signal",     signal_fn,     timeout_ms=200)
  coordinator.register_layer("risk",       risk_fn,       timeout_ms=100)
  coordinator.register_layer("execution",  exec_fn,       timeout_ms=300)
  result = coordinator.run_cycle(ctx)
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from cold_start.warmup_signer import sign
from observability.json_logger import get_logger
from runtime.execution_context import ExecutionContext
from runtime.lifecycle_manager import LifecycleManager
from runtime.system_state_bus import CHANNEL_SYSTEM_CYCLE, SystemStateBus

_log = get_logger("runtime.runtime_coordinator")

_DEFAULT_LAYER_TIMEOUT_MS = float(os.getenv("P10_LAYER_TIMEOUT_MS", "500.0"))

# Couches critiques : un échec interrompt le cycle (pas de décision orpheline)
_CRITICAL_LAYERS = frozenset({"signal", "risk"})


# ── Types de résultats ────────────────────────────────────────────────────────


@dataclass
class LayerResult:
    name: str
    success: bool
    duration_ms: float
    output: Any = None
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


@dataclass
class CycleResult:
    cycle_id: str
    success: bool
    duration_ms: float
    layers: list[LayerResult] = field(default_factory=list)
    decision: Optional[dict] = None
    error: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "layers": [r.to_dict() for r in self.layers],
            "decision": self.decision,
            "error": self.error,
            "ts": round(self.ts, 3),
        }

    def to_signed_dict(self) -> dict:
        d = self.to_dict()
        d["signature"] = sign(d)
        return d


# ── Définition d'une couche ───────────────────────────────────────────────────


@dataclass
class _LayerDef:
    name: str
    fn: Callable
    timeout_ms: float


# ── RuntimeCoordinator ────────────────────────────────────────────────────────


class RuntimeCoordinator:
    """
    Orchestre l'exécution des cycles de décision.

    Les couches sont enregistrées dans l'ordre d'exécution via register_layer().
    La couche nommée "decision" est celle dont l'output est retenu comme décision.
    Les couches "signal" et "risk" sont critiques : leur échec interrompt le cycle.
    """

    def __init__(
        self,
        bus: Optional[SystemStateBus] = None,
        lifecycle: Optional[LifecycleManager] = None,
    ) -> None:
        self._bus = bus or SystemStateBus()
        self._lifecycle = lifecycle
        self._layers: list[_LayerDef] = []
        self._cycles_run: int = 0
        self._active_cycle_id: Optional[str] = None
        self._lock = threading.Lock()

    # ── API publique ──────────────────────────────────────────────────────────

    def register_layer(
        self,
        name: str,
        fn: Callable,
        timeout_ms: float = _DEFAULT_LAYER_TIMEOUT_MS,
    ) -> None:
        """
        Enregistre une couche dans l'ordre d'exécution.
        La couche "decision" doit retourner un dict (la décision candidate) ou None.
        """
        self._layers.append(_LayerDef(name=name, fn=fn, timeout_ms=timeout_ms))
        _log.debug(
            "[Coordinator] couche enregistrée: %s (timeout=%.0fms)", name, timeout_ms
        )

    def run_cycle(self, context: ExecutionContext) -> CycleResult:
        """
        Exécute un cycle complet avec le contexte donné.

        - Le contexte est gelé (freeze()) au début — immuable pendant le cycle.
        - Si une couche critique (signal/risk) échoue, le cycle s'arrête sans décision.
        - Le résultat est publié sur CHANNEL_SYSTEM_CYCLE.
        """
        cycle_id = context.cycle_id
        frozen = context.freeze()

        with self._lock:
            self._active_cycle_id = cycle_id

        cycle_start = time.perf_counter()
        layers_results: list[LayerResult] = []
        decision: Optional[dict] = None
        cycle_error = ""

        try:
            for layer_def in self._layers:
                lr = self._run_layer(layer_def, frozen)
                layers_results.append(lr)

                if (
                    lr.success
                    and layer_def.name == "decision"
                    and lr.output is not None
                ):
                    decision = lr.output

                if not lr.success and layer_def.name in _CRITICAL_LAYERS:
                    cycle_error = (
                        f"couche critique '{layer_def.name}' échouée: {lr.error}"
                    )
                    decision = None  # jamais de décision orpheline
                    _log.warning(
                        "[Coordinator] cycle %s interrompu — %s", cycle_id, cycle_error
                    )
                    break

        except Exception as exc:
            cycle_error = str(exc)
            decision = None
            _log.error("[Coordinator] cycle %s exception: %s", cycle_id, exc)

        finally:
            with self._lock:
                self._active_cycle_id = None

        duration_ms = (time.perf_counter() - cycle_start) * 1000
        success = not cycle_error and all(
            r.success or r.name not in _CRITICAL_LAYERS for r in layers_results
        )

        result = CycleResult(
            cycle_id=cycle_id,
            success=success,
            duration_ms=duration_ms,
            layers=layers_results,
            decision=decision,
            error=cycle_error,
        )

        self._cycles_run += 1
        self._bus.publish(CHANNEL_SYSTEM_CYCLE, result.to_dict())

        _log.info(
            "[Coordinator] cycle=%s %s %.1fms decision=%s",
            cycle_id,
            "OK" if success else "FAIL",
            duration_ms,
            "OUI" if decision else "NON",
        )

        return result

    def shutdown(self) -> None:
        """
        Arrêt propre.
        Si un cycle est en cours, il est invalidé (décision annulée).
        """
        with self._lock:
            active = self._active_cycle_id

        if active:
            _log.warning(
                "[Coordinator] shutdown pendant cycle %s — décision annulée", active
            )
            with self._lock:
                self._active_cycle_id = None

        _log.info("[Coordinator] arrêt propre — %d cycles exécutés", self._cycles_run)

    @property
    def cycles_run(self) -> int:
        return self._cycles_run

    @property
    def layer_names(self) -> list[str]:
        return [ld.name for ld in self._layers]

    @property
    def is_idle(self) -> bool:
        with self._lock:
            return self._active_cycle_id is None

    # ── Exécution d'une couche avec timeout ───────────────────────────────────

    def _run_layer(
        self, layer_def: _LayerDef, context: ExecutionContext
    ) -> LayerResult:
        """
        Exécute fn(context) dans un thread avec timeout.

        Note : en Python, un thread dépassant le timeout continue en arrière-plan
        (les threads ne sont pas interrompibles). Le résultat est simplement ignoré.
        """
        result_holder: list = []
        error_holder: list = []

        def _target() -> None:
            try:
                out = layer_def.fn(context)
                result_holder.append(out)
            except Exception as exc:
                error_holder.append(str(exc))

        start = time.perf_counter()
        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=layer_def.timeout_ms / 1000.0)
        duration_ms = (time.perf_counter() - start) * 1000.0

        if t.is_alive():
            error = f"timeout {layer_def.timeout_ms:.0f}ms"
            _log.warning(
                "[Coordinator] couche %s — timeout (%.0fms)",
                layer_def.name,
                layer_def.timeout_ms,
            )
            return LayerResult(
                name=layer_def.name, success=False, duration_ms=duration_ms, error=error
            )

        if error_holder:
            _log.warning(
                "[Coordinator] couche %s erreur: %s", layer_def.name, error_holder[0]
            )
            return LayerResult(
                name=layer_def.name,
                success=False,
                duration_ms=duration_ms,
                error=error_holder[0],
            )

        return LayerResult(
            name=layer_def.name,
            success=True,
            duration_ms=duration_ms,
            output=result_holder[0] if result_holder else None,
        )
