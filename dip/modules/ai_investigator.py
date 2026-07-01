"""
dip/modules/ai_investigator.py — D10 AI Investigator Engine.

Génère des investigations textuelles des décisions en utilisant un LLM.
Modèle: claude-sonnet-4-6 (temperature=0.0 pour reproductibilité).
Fallback: template texte déterministe si le LLM est indisponible (ADR-0014).

Passif: produit uniquement des observations textuelles.
Jamais de recommandation de modification de seuil ni d'appel au moteur.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore
from dip.core.types import now_us
from dip.modules.causal_tree import get_causal_tree_engine
from dip.modules.counterfactual import get_counterfactual_engine
from dip.modules.decision_graph import get_graph_engine
from dip.modules.explainability import get_explainability_engine
from dip.modules.knowledge_base import get_knowledge_base

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InvestigationContext:
    packet_id: str
    symbol: str
    direction: str
    regime: str
    status: str
    graph_summary: str
    causal_summary: str
    explainability_grade: str
    counterfactual_summary: str
    knowledge_patterns: str


@dataclass(frozen=True)
class InvestigationResult:
    investigation_id: str
    packet_id: str
    hypothesis: str
    root_cause_analysis: str
    recommendations: str
    confidence: float
    source: str  # "llm" | "template"
    model: str
    latency_ms: int
    created_at_us: int
    disclaimer: str


@dataclass(frozen=True)
class InvestigationBatch:
    batch_id: str
    investigations: tuple[InvestigationResult, ...]
    total: int
    llm_count: int
    template_count: int
    avg_latency_ms: float


_DISCLAIMER = (
    "Cette analyse est générée automatiquement à des fins d'observation. "
    "Elle n'engage aucune modification du moteur de trading. "
    "Toute calibration requiert validation opérateur (CLAUDE.md § Statisticien)."
)

_LLM_MODEL = "claude-sonnet-4-6"
_LLM_TEMPERATURE = 0.0
_LLM_MAX_TOKENS = 800
_LLM_TIMEOUT_S = 30


# ── Context Builder ───────────────────────────────────────────────────────────


class ContextBuilder:

    def __init__(self, store: DIPStore) -> None:
        self._store = store

    def build(self, packet_id: str) -> Optional[InvestigationContext]:
        row = self._store.get_decision(packet_id)
        if not row:
            return None

        graph_engine = get_graph_engine()
        causal_engine = get_causal_tree_engine()
        exp_engine = get_explainability_engine()
        cf_engine = get_counterfactual_engine()
        kb = get_knowledge_base()

        graph = graph_engine.get_graph(packet_id)
        causal = causal_engine.build_causal_tree(packet_id)
        exp = exp_engine.compute_score(packet_id)

        # Graph summary
        if graph:
            layers_passed = [
                n.layer for n in graph.nodes if n.status.value != "BLOCKED"
            ]
            blocker = next(
                (n for n in graph.nodes if n.status.value == "BLOCKED"), None
            )
            graph_summary = (
                f"Pipeline: {' → '.join(layers_passed[:5])}{'...' if len(layers_passed) > 5 else ''}. "
                f"Bloqueur: {blocker.layer if blocker else 'aucun'} "
                f"(confiance finale: {graph.metrics.confidence_end:.2f})"
            )
        else:
            graph_summary = "Graphe non disponible."

        # Causal summary
        if causal:
            causal_summary = (
                f"Cause racine: {causal.root_cause.cause_type.value} "
                f"via {causal.root_cause.causal_node.layer}. "
                f"{causal.description}"
            )
        else:
            causal_summary = "Arbre causal non disponible."

        # Explainability
        exp_grade = exp.grade if exp else "?"
        cf_summary = "Non disponible."

        # Knowledge patterns
        patterns = kb.query_patterns(symbol=row.get("symbol"))
        if patterns:
            top = patterns[0]
            knowledge_patterns = (
                f"{len(patterns)} pattern(s) connu(s). Dominant: {top.description}"
            )
        else:
            knowledge_patterns = "Aucun pattern connu pour ce symbole."

        return InvestigationContext(
            packet_id=packet_id,
            symbol=row.get("symbol", "?"),
            direction=row.get("direction", "?"),
            regime=row.get("regime", "?"),
            status=row.get("status", "?"),
            graph_summary=graph_summary,
            causal_summary=causal_summary,
            explainability_grade=exp_grade,
            counterfactual_summary=cf_summary,
            knowledge_patterns=knowledge_patterns,
        )


# ── LLM Client ────────────────────────────────────────────────────────────────


class LLMClient:
    """
    Client Anthropic pour génération d'investigations.
    Lazy import: ne charge anthropic que si disponible.
    """

    def __init__(self) -> None:
        self._client = None
        self._available = None  # None = not yet checked

    def _ensure_client(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import anthropic

            self._client = anthropic.Anthropic()
            self._available = True
        except ImportError:
            self._available = False
        except Exception:
            self._available = False
        return self._available

    def generate(self, prompt: str) -> tuple[str, int]:
        """Retourne (texte, latency_ms). Raise si LLM indisponible."""
        if not self._ensure_client():
            raise RuntimeError("anthropic package non disponible")
        t0 = time.monotonic()
        try:
            msg = self._client.messages.create(
                model=_LLM_MODEL,
                max_tokens=_LLM_MAX_TOKENS,
                temperature=_LLM_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            text = msg.content[0].text if msg.content else ""
            return text, latency_ms
        except Exception as e:
            raise RuntimeError(f"LLM error: {e}") from e


# ── Template Fallback ──────────────────────────────────────────────────────────


class TemplateFallback:
    """Génère une investigation déterministe sans LLM (ADR-0014 compliant)."""

    @staticmethod
    def generate(ctx: InvestigationContext) -> tuple[str, str, str]:
        """Retourne (hypothesis, root_cause_analysis, recommendations)."""
        status_label = "approuvé" if ctx.status == "APPROVED" else "rejeté"

        hypothesis = (
            f"Le trade {ctx.direction} sur {ctx.symbol} en régime {ctx.regime} "
            f"a été {status_label}. "
            f"{ctx.graph_summary}"
        )

        root_cause = (
            f"Analyse causale: {ctx.causal_summary} "
            f"Score d'explicabilité: {ctx.explainability_grade}. "
            f"Contexte knowledge: {ctx.knowledge_patterns}"
        )

        recommendations = (
            "Observer l'évolution sur N≥50 décisions similaires avant toute conclusion. "
            "Aucune modification de seuil autorisée (CRI < 90 requis, cf. CLAUDE.md)."
        )

        return hypothesis, root_cause, recommendations


# ── Prompt Builder ────────────────────────────────────────────────────────────


def _build_prompt(ctx: InvestigationContext) -> str:
    return f"""Tu es un data scientist observateur pour un système de trading algorithmique.
Ta mission: analyser une décision de trading à des fins d'observation uniquement.

CONTRAINTES ABSOLUES:
- Tu ne recommandes JAMAIS de modifier un seuil ou paramètre du moteur
- Tu n'es qu'observateur passif (ADR-0007)
- Tout calibration nécessite N≥500 trades et CRI≥90 (CLAUDE.md)

DÉCISION ANALYSÉE:
- Packet ID: {ctx.packet_id}
- Symbole: {ctx.symbol} | Direction: {ctx.direction} | Régime: {ctx.regime}
- Résultat: {ctx.status}

DONNÉES DIP:
- Pipeline: {ctx.graph_summary}
- Causal: {ctx.causal_summary}
- Explicabilité grade: {ctx.explainability_grade}
- Contrefactuels: {ctx.counterfactual_summary}
- Patterns connus: {ctx.knowledge_patterns}

Rédige une investigation structurée en 3 parties courtes:
1. HYPOTHÈSE: Quelle est la cause apparente la plus probable? (2-3 phrases)
2. ANALYSE: Que révèlent les données DIP sur cette décision? (3-4 phrases)
3. OBSERVATION: Qu'observer sur les prochaines décisions similaires? (1-2 phrases)

Réponds en français. Sois factuel et précis. Maximum 200 mots."""


# ── Parser ────────────────────────────────────────────────────────────────────


def _parse_llm_response(text: str) -> tuple[str, str, str]:
    """Parse la réponse LLM en 3 sections."""
    hypothesis = ""
    root_cause = ""
    recommendations = ""

    current_section = None
    for line in text.split("\n"):
        ln = line.strip()
        if (
            ln.upper().startswith("1.")
            or "HYPOTHÈSE" in ln.upper()
            or "HYPOTHESE" in ln.upper()
        ):
            current_section = "h"
            ln = ln.split(":", 1)[-1].strip()
        elif ln.upper().startswith("2.") or "ANALYSE" in ln.upper():
            current_section = "a"
            ln = ln.split(":", 1)[-1].strip()
        elif ln.upper().startswith("3.") or "OBSERVATION" in ln.upper():
            current_section = "r"
            ln = ln.split(":", 1)[-1].strip()

        if current_section == "h" and ln:
            hypothesis += ln + " "
        elif current_section == "a" and ln:
            root_cause += ln + " "
        elif current_section == "r" and ln:
            recommendations += ln + " "

    hypothesis = hypothesis.strip() or text[:200]
    root_cause = root_cause.strip() or "Voir hypothèse."
    recommendations = recommendations.strip() or "Observer N≥50 décisions similaires."
    return hypothesis, root_cause, recommendations


# ── Engine ─────────────────────────────────────────────────────────────────────


class AIInvestigatorEngine:
    """D10 — Moteur d'investigation IA."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._ctx_builder = ContextBuilder(self._store)
        self._llm = LLMClient()
        self._lock = threading.Lock()
        self._cache: dict[str, InvestigationResult] = {}
        self._max_cache = 500

    def investigate(self, packet_id: str) -> InvestigationResult:
        if packet_id in self._cache:
            return self._cache[packet_id]

        ctx = self._ctx_builder.build(packet_id)
        if not ctx:
            return self._error_result(packet_id, "Décision introuvable.")

        # Essaye LLM, fallback sur template
        source = "template"
        model = "template"
        latency_ms = 0

        t0 = time.monotonic()
        try:
            prompt = _build_prompt(ctx)
            llm_text, latency_ms = self._llm.generate(prompt)
            hypothesis, root_cause, recommendations = _parse_llm_response(llm_text)
            source = "llm"
            model = _LLM_MODEL
        except Exception:
            hypothesis, root_cause, recommendations = TemplateFallback.generate(ctx)
            latency_ms = int((time.monotonic() - t0) * 1000)

        result = InvestigationResult(
            investigation_id=f"inv_{packet_id[:12]}_{now_us()}",
            packet_id=packet_id,
            hypothesis=hypothesis,
            root_cause_analysis=root_cause,
            recommendations=recommendations,
            confidence=0.80 if source == "llm" else 0.60,
            source=source,
            model=model,
            latency_ms=latency_ms,
            created_at_us=now_us(),
            disclaimer=_DISCLAIMER,
        )

        with self._lock:
            self._cache[packet_id] = result
            # Éviction LRU simple si cache trop grand
            if len(self._cache) > self._max_cache:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

        return result

    def batch_investigate(
        self, packet_ids: list[str], max_llm_calls: int = 5
    ) -> InvestigationBatch:
        results = []
        llm_count = 0
        latencies = []

        for pid in packet_ids[:50]:  # limite de sécurité
            use_llm = llm_count < max_llm_calls
            if not use_llm:
                # Forcer le template pour économiser les appels LLM
                ctx = self._ctx_builder.build(pid)
                if ctx:
                    h, r, rec = TemplateFallback.generate(ctx)
                    result = InvestigationResult(
                        investigation_id=f"inv_{pid[:12]}_{now_us()}",
                        packet_id=pid,
                        hypothesis=h,
                        root_cause_analysis=r,
                        recommendations=rec,
                        confidence=0.60,
                        source="template",
                        model="template",
                        latency_ms=0,
                        created_at_us=now_us(),
                        disclaimer=_DISCLAIMER,
                    )
                else:
                    result = self._error_result(pid, "Non trouvé.")
            else:
                result = self.investigate(pid)
                if result.source == "llm":
                    llm_count += 1

            results.append(result)
            latencies.append(result.latency_ms)

        return InvestigationBatch(
            batch_id=f"batch_{now_us()}",
            investigations=tuple(results),
            total=len(results),
            llm_count=llm_count,
            template_count=len(results) - llm_count,
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        )

    def get_recent_investigations(self, limit: int = 20) -> list[InvestigationResult]:
        rows = self._store.get_decisions(limit=limit)
        return [
            self._cache[r["packet_id"]] for r in rows if r["packet_id"] in self._cache
        ]

    def _error_result(self, packet_id: str, reason: str) -> InvestigationResult:
        return InvestigationResult(
            investigation_id=f"inv_err_{now_us()}",
            packet_id=packet_id,
            hypothesis=reason,
            root_cause_analysis="Données insuffisantes.",
            recommendations="Vérifier que la décision est enregistrée dans DIPStore.",
            confidence=0.0,
            source="template",
            model="none",
            latency_ms=0,
            created_at_us=now_us(),
            disclaimer=_DISCLAIMER,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[AIInvestigatorEngine] = None
_engine_lock = threading.Lock()


def get_investigator_engine() -> AIInvestigatorEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = AIInvestigatorEngine()
    return _engine
