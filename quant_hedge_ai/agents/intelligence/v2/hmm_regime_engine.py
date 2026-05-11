"""
hmm_regime_engine.py — Hidden Markov Model Regime Detection

Remplace le RegimeDetector déterministe par un HMM probabiliste qui :
- Estime la distribution de probabilités sur les régimes (pas une classe unique)
- Maintient une matrice de transition apprise
- Permet la prédiction de changement de régime
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_PATH = Path("databases/hmm_regime_model.pkl")


@dataclass
class RegimeProbabilities:
    bull: float = 0.25
    bear: float = 0.25
    chop: float = 0.25
    high_vol: float = 0.25

    # Méta
    dominant: str = "chop"
    confidence: float = 0.25
    entropy: float = 1.0        # entropie de Shannon [0, log2(4)] : 0=certitude, 2=incertitude totale
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "bull": self.bull,
            "bear": self.bear,
            "chop": self.chop,
            "high_vol": self.high_vol,
            "dominant": self.dominant,
            "confidence": self.confidence,
            "entropy": self.entropy,
        }

    def is_transitioning(self, threshold: float = 0.35) -> bool:
        """True si aucun régime n'est dominant (incertitude de transition)."""
        return self.confidence < threshold

    def normalize(self) -> None:
        total = self.bull + self.bear + self.chop + self.high_vol
        if total > 0:
            self.bull /= total
            self.bear /= total
            self.chop /= total
            self.high_vol /= total
        self.dominant = max(["bull", "bear", "chop", "high_vol"], key=lambda r: getattr(self, r))
        self.confidence = getattr(self, self.dominant)
        probs = [self.bull, self.bear, self.chop, self.high_vol]
        self.entropy = -sum(p * np.log2(p + 1e-10) for p in probs)


class HMMRegimeEngine:
    """
    Moteur de détection de régime basé sur un Hidden Markov Model (HMM) à 4 états.

    États cachés : bull, bear, chop, high_vol
    Observations : vecteur de features (returns, volatilité, volume, momentum...)

    Entraîné de manière incrémentale sur les données live.
    Persiste le modèle sur disque pour survie aux redémarrages.
    """

    N_STATES = 4
    STATE_NAMES = ["bull", "bear", "chop", "high_vol"]
    MIN_SAMPLES_TRAIN = 50

    def __init__(self) -> None:
        self._model = None
        self._is_fitted = False
        self._training_buffer: list[list[float]] = []
        self._last_probs: dict[str, RegimeProbabilities] = {}
        self._load_model()

    # ------------------------------------------------------------------
    # API principale
    # ------------------------------------------------------------------

    def predict(self, symbol: str, features: dict[str, float]) -> RegimeProbabilities:
        """
        Prédit la distribution de probabilités de régime pour un symbole.
        Retourne une distribution uniforme si pas encore entraîné.
        """
        obs = self._extract_obs(features)
        self._training_buffer.append(obs)

        if not self._is_fitted or len(self._training_buffer) < self.MIN_SAMPLES_TRAIN:
            probs = self._heuristic_regime(features)
        else:
            probs = self._hmm_predict(obs)

        # Tenter un entraînement incrémental
        if len(self._training_buffer) >= self.MIN_SAMPLES_TRAIN and len(self._training_buffer) % 20 == 0:
            self._fit()

        import time
        probs.timestamp = time.time()
        self._last_probs[symbol] = probs
        return probs

    def get_last(self, symbol: str) -> RegimeProbabilities | None:
        return self._last_probs.get(symbol)

    def transition_matrix(self) -> np.ndarray | None:
        if self._model and hasattr(self._model, "transmat_"):
            return self._model.transmat_
        return None

    # ------------------------------------------------------------------
    # Entraînement
    # ------------------------------------------------------------------

    def _fit(self) -> None:
        try:
            from hmmlearn.hmm import GaussianHMM
            X = np.array(self._training_buffer)
            lengths = [len(X)]
            model = GaussianHMM(
                n_components=self.N_STATES,
                covariance_type="diag",
                n_iter=20,
                random_state=42,
            )
            model.fit(X, lengths)
            self._model = model
            self._is_fitted = True
            self._save_model()
            logger.debug("[HMMRegime] Modèle entraîné sur %d samples", len(X))
        except Exception as exc:
            logger.warning("[HMMRegime] Fit error: %s", exc)

    def _hmm_predict(self, obs: list[float]) -> RegimeProbabilities:
        """Décode les probabilités d'état pour l'observation actuelle."""
        try:
            X = np.array([obs])
            # Posterior state probabilities via forward algorithm
            log_prob, posteriors = self._model.score_samples(X)
            probs_array = posteriors[0]

            # Mapper les états HMM → régimes nommés (par variance apprise)
            state_vars = np.diag(self._model.covars_[..., 0].mean(axis=-1)) if hasattr(self._model, 'covars_') else np.arange(self.N_STATES)
            ordered_states = np.argsort(state_vars)

            # Heuristique : état low-var → chop, high-var → high_vol
            mapping = {
                ordered_states[0]: "chop",
                ordered_states[1]: "bull",
                ordered_states[2]: "bear",
                ordered_states[3]: "high_vol",
            }
            named = {name: 0.0 for name in self.STATE_NAMES}
            for state_idx, prob in enumerate(probs_array):
                regime_name = mapping.get(state_idx, "chop")
                named[regime_name] += float(prob)

            result = RegimeProbabilities(**{k: named[k] for k in self.STATE_NAMES})
            result.normalize()
            return result
        except Exception as exc:
            logger.debug("[HMMRegime] predict error: %s", exc)
            return self._heuristic_regime({})

    def _heuristic_regime(self, features: dict[str, float]) -> RegimeProbabilities:
        """Détection de régime heuristique (avant HMM entraîné)."""
        rsi = features.get("rsi_14", 50.0)
        atr = features.get("atr_pct", 0.01)
        ema_cross = features.get("ema_cross", 0.0)
        features.get("volume_ratio", 1.0)

        probs = RegimeProbabilities()

        if atr > 0.04:
            probs.high_vol = 0.6
            probs.bull = 0.15
            probs.bear = 0.15
            probs.chop = 0.1
        elif ema_cross > 0 and rsi > 55:
            probs.bull = 0.55
            probs.chop = 0.25
            probs.bear = 0.1
            probs.high_vol = 0.1
        elif ema_cross < 0 and rsi < 45:
            probs.bear = 0.55
            probs.chop = 0.25
            probs.bull = 0.1
            probs.high_vol = 0.1
        else:
            probs.chop = 0.5
            probs.bull = 0.2
            probs.bear = 0.2
            probs.high_vol = 0.1

        probs.normalize()
        return probs

    def _extract_obs(self, features: dict[str, float]) -> list[float]:
        """Extrait les features d'observation pour le HMM."""
        keys = ["rsi_14", "atr_pct", "ema_cross", "volume_ratio", "ob_imbalance", "funding_rate"]
        return [float(features.get(k, 0.0)) for k in keys]

    def _save_model(self) -> None:
        try:
            _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _MODEL_PATH.open("wb") as f:
                pickle.dump(self._model, f)
        except Exception as exc:
            logger.debug("[HMMRegime] save error: %s", exc)

    def _load_model(self) -> None:
        try:
            if _MODEL_PATH.exists():
                with _MODEL_PATH.open("rb") as f:
                    self._model = pickle.load(f)
                    self._is_fitted = True
                logger.info("[HMMRegime] Modèle chargé depuis %s", _MODEL_PATH)
        except Exception as exc:
            logger.debug("[HMMRegime] load error: %s", exc)
