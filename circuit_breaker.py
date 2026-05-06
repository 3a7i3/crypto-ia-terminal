"""
circuit_breaker.py — Circuit-breaker proactif pour stabilité
Monitore: mémoire, latence, erreurs → arrêt/pause intelligent si seuils dépassés
"""

import logging
import psutil
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional

log = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    """États du circuit"""
    CLOSED = "closed"      # Normal
    HALF_OPEN = "half_open"  # Recup en cours
    OPEN = "open"          # Problème détecté, en pause


@dataclass
class Threshold:
    """Seuil de déclenchement"""
    name: str
    metric_name: str
    warning_level: float
    critical_level: float
    hysteresis: float = 0.1  # Pour éviter flickering


class CircuitBreaker:
    """Protège système contre dégradations"""

    THRESHOLDS = {
        "memory": Threshold(
            name="Memory Usage",
            metric_name="memory",
            warning_level=75.0,   # 75% alerte
            critical_level=90.0,  # 90% critique
        ),
        "latency": Threshold(
            name="Operation Latency",
            metric_name="latency",
            warning_level=2.0,    # 2s en ms
            critical_level=5.0,   # 5s en ms
        ),
        "error_rate": Threshold(
            name="Error Rate",
            metric_name="error_rate",
            warning_level=0.05,   # 5% erreurs
            critical_level=0.20,  # 20% erreurs
        ),
    }

    def __init__(self, check_interval: float = 5.0):
        self.state = CircuitState.CLOSED
        self.check_interval = check_interval
        self.is_running = False

        self._metrics: Dict[str, float] = {
            "memory": 0.0,
            "latency": 0.0,
            "error_rate": 0.0,
        }
        self._warning_count = 0
        self._critical_count = 0
        self._callbacks_on_critical: List[Callable] = []
        self._callbacks_on_recover: List[Callable] = []

    def register_on_critical(self, callback: Callable) -> None:
        """Enregistre callback si critique"""
        self._callbacks_on_critical.append(callback)

    def register_on_recover(self, callback: Callable) -> None:
        """Enregistre callback si récupération"""
        self._callbacks_on_recover.append(callback)

    def _get_memory_percent(self) -> float:
        """Retourne % mémoire utilisée"""
        try:
            return psutil.virtual_memory().percent
        except Exception as e:
            log.warning(f"Failed to get memory: {e}")
            return 0.0

    def update_metric(self, metric_name: str, value: float) -> None:
        """Update métrique spécifique"""
        if metric_name in self._metrics:
            self._metrics[metric_name] = value
        else:
            log.warning(f"Unknown metric: {metric_name}")

    def update_latency(self, latency_seconds: float) -> None:
        """Update latence (convertir en ms)"""
        self.update_metric("latency", latency_seconds * 1000)

    def update_error_rate(self, errors: int, total: int) -> None:
        """Update taux erreur"""
        if total > 0:
            rate = errors / total
            self.update_metric("error_rate", rate)

    def _check_thresholds(self) -> Dict[str, str]:
        """Vérifie tous seuils"""
        violations = {}

        # Update mémoire actuelle
        self._metrics["memory"] = self._get_memory_percent()

        for threshold_key, threshold in self.THRESHOLDS.items():
            value = self._metrics.get(threshold.metric_name, 0.0)

            if value >= threshold.critical_level:
                violations[threshold.name] = "CRITICAL"
            elif value >= threshold.warning_level:
                violations[threshold.name] = "WARNING"

        return violations

    def _handle_violations(self, violations: Dict[str, str]) -> None:
        """Traite violations détectées"""
        if not violations:
            # Pas de violation - peut récupérer
            if self.state == CircuitState.OPEN:
                log.info("✓ All thresholds OK, attempting recovery...")
                self.state = CircuitState.HALF_OPEN
                for callback in self._callbacks_on_recover:
                    try:
                        callback()
                    except Exception as e:
                        log.error(f"Callback error: {e}")
            self._warning_count = 0
            return

        # Violations détectées
        critical = any(v == "CRITICAL" for v in violations.values())
        self._warning_count += 1

        for name, level in violations.items():
            log.warning(f"⚠ {name}: {level} ({self._warning_count} consecutive)")

        if critical or self._warning_count >= 3:
            if self.state != CircuitState.OPEN:
                log.critical("🛑 CIRCUIT BREAKER OPENED - Pausing operations")
                self.state = CircuitState.OPEN
                self._critical_count += 1

                # Déclenche callbacks
                for callback in self._callbacks_on_critical:
                    try:
                        callback()
                    except Exception as e:
                        log.error(f"Callback error: {e}")

    def _monitor_loop(self) -> None:
        """Boucle de monitoring continu"""
        while self.is_running:
            try:
                violations = self._check_thresholds()
                self._handle_violations(violations)
            except Exception as e:
                log.error(f"Monitor loop error: {e}")

            time.sleep(self.check_interval)

    def start(self) -> None:
        """Lance monitoring en background"""
        if self.is_running:
            log.warning("Circuit breaker already running")
            return

        self.is_running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        log.info("Circuit breaker started")

    def stop(self) -> None:
        """Arrête monitoring"""
        self.is_running = False
        log.info("Circuit breaker stopped")

    def can_proceed(self) -> bool:
        """Vérifie si circuit permet d'avancer"""
        return self.state != CircuitState.OPEN

    def get_state(self) -> Dict[str, any]:
        """Retourne état actuel"""
        return {
            "state": self.state.value,
            "metrics": self._metrics.copy(),
            "warning_count": self._warning_count,
            "critical_events": self._critical_count,
            "can_proceed": self.can_proceed(),
        }

    def reset(self) -> None:
        """Reset le circuit"""
        log.info("Resetting circuit breaker")
        self.state = CircuitState.CLOSED
        self._warning_count = 0


# Singleton
_breaker_instance: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Retourne instance unique"""
    global _breaker_instance
    if _breaker_instance is None:
        _breaker_instance = CircuitBreaker(check_interval=5.0)
    return _breaker_instance


def enable_circuit_breaker(
    on_critical: Optional[Callable] = None,
    on_recover: Optional[Callable] = None,
) -> CircuitBreaker:
    """Active circuit breaker avec callbacks optionnels"""
    breaker = get_circuit_breaker()

    if on_critical:
        breaker.register_on_critical(on_critical)
    if on_recover:
        breaker.register_on_recover(on_recover)

    breaker.start()
    return breaker


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s"
    )

    breaker = get_circuit_breaker()

    def on_crit():
        print("🚨 CRITICAL ALERT!")

    def on_rec():
        print("✓ RECOVERED!")

    breaker.register_on_critical(on_crit)
    breaker.register_on_recover(on_rec)
    breaker.start()

    print("Testing circuit breaker (30s)...")
    for i in range(30):
        state = breaker.get_state()
        print(f"[{i}] State: {state['state']}, Memory: {state['metrics']['memory']:.1f}%")
        time.sleep(1)

    breaker.stop()
