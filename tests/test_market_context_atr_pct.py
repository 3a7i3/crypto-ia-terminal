"""`market_context` alimenté et `atr_pct` à la bonne échelle.

Deux défauts mesurés sur l'époque V4, corrigés ensemble parce qu'ils bloquent
la même hypothèse :

1. **`market_context` vide.** Champ présent dans 332 enregistrements sur 332,
   alimenté dans **0**. Cause : deux appelants de `record_open`, dont un seul
   passe le contexte — et c'est l'autre qui produit les trades. Le simulateur
   ne recevait pas les features, il ne pouvait donc rien transmettre.

2. **`atr_pct` introuvable.** Le recorder écrit `atr_ratio` (ATR / prix, un
   RATIO) ; `h4_atr_filter` lit `atr_pct` et le compare à `1.5` (un
   POURCENTAGE). Mesure : 0 enregistrement sur 1 421 portait `atr_pct`.

Le piège que ces tests verrouillent : mapper `atr_ratio` sur `atr_pct` sans
×100 ne lève aucune erreur. Le groupe « ATR haut » devient simplement vide et
H4 rend « non concluant » — c'est-à-dire **indiscernable d'un manque de
données**. Un défaut silencieux, pas une panne.
"""

from __future__ import annotations

import dataclasses

from analysis.base import _atr_pct_of
from paper_trading.mexc_simulator import MexcOrder, MexcPosition, OrderSide, OrderType
from paper_trading.recorder import MarketContext

# Seuil pré-enregistré de H4 : `h4_atr_filter(trades, atr_threshold=1.5)`.
H4_SEUIL = 1.5


class TestEchelleATR:
    """Le défaut silencieux : une unité, deux conventions."""

    def test_atr_pct_est_le_ratio_fois_cent(self):
        mc = MarketContext.from_features({"atr_ratio": 0.0158})
        assert mc.atr_ratio == 0.0158
        assert abs(mc.atr_pct - 1.58) < 1e-9

    def test_la_conversion_change_le_verdict_de_H4(self):
        """Sans ×100, ce trade sort du groupe « ATR haut » — silencieusement."""
        mc = MarketContext.from_features({"atr_ratio": 0.0158})
        assert mc.atr_pct >= H4_SEUIL, "1,58 % doit franchir le seuil de 1,5 %"
        assert mc.atr_ratio < H4_SEUIL, (
            "le ratio brut ne franchit jamais 1.5 : le mapper directement "
            "viderait le groupe et rendrait H4 non concluante en silence"
        )

    def test_absence_de_ratio_ne_fabrique_pas_de_zero(self):
        """`None` doit rester `None` : un 0.0 inventé serait un faux ATR bas."""
        mc = MarketContext.from_features({"rsi": 55})
        assert mc.atr_ratio is None
        assert mc.atr_pct is None

    def test_atr_pct_n_est_pas_lu_depuis_les_features(self):
        """Le nom `atr_pct` désigne un RATIO dans les modules d'exécution
        (`execution_optimizer.py:159` le compare à 0.015). On ne lit donc
        jamais cette clé : on dérive de `atr_ratio`, seule convention sûre."""
        mc = MarketContext.from_features({"atr_ratio": 0.02, "atr_pct": 999.0})
        assert abs(mc.atr_pct - 2.0) < 1e-9, "la clé piégée ne doit pas gagner"


class TestLectureParAnalyseur:
    """`_atr_pct_of` — ordre de recherche et replis."""

    def test_depuis_market_context_atr_pct(self):
        mc = MarketContext.from_features({"atr_ratio": 0.0158})
        op = {"market_context": dataclasses.asdict(mc)}
        assert abs(_atr_pct_of(op, {}) - 1.58) < 1e-9

    def test_repli_sur_atr_ratio_pour_les_enregistrements_anterieurs(self):
        op = {"market_context": {"atr_ratio": 0.0158}}
        assert abs(_atr_pct_of(op, {}) - 1.58) < 1e-9

    def test_repli_sur_la_racine_pour_les_schemas_historiques(self):
        assert _atr_pct_of({"atr_pct": 1.58}, {}) == 1.58

    def test_aucune_source_rend_none(self):
        assert _atr_pct_of({}, {}) is None

    def test_le_close_sert_de_repli_si_l_open_est_muet(self):
        cl = {"market_context": {"atr_ratio": 0.02}}
        assert abs(_atr_pct_of({}, cl) - 2.0) < 1e-9


class TestTransportDesFeatures:
    """Le simulateur doit pouvoir transmettre ce qu'il ne lit pas."""

    def test_ordre_sans_features_reste_valide(self):
        o = MexcOrder(
            order_id="X",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty_usd=10.0,
        )
        assert o.features == {}

    def test_position_sans_features_reste_valide(self):
        p = MexcPosition(
            pos_id="X",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            qty_usd=10.0,
            entry_price=1.0,
            tp_price=1.0,
            sl_price=1.0,
            fee_entry_usd=0.0,
            score=70,
            personality="p",
        )
        assert p.features == {}

    def test_les_features_traversent_ordre_et_position(self):
        feats = {"atr_ratio": 0.0158, "rsi": 55.0}
        o = MexcOrder(
            order_id="X",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty_usd=10.0,
            features=feats,
        )
        p = MexcPosition(
            pos_id=o.order_id,
            symbol=o.symbol,
            side=o.side,
            qty_usd=o.qty_usd,
            entry_price=1.0,
            tp_price=1.0,
            sl_price=1.0,
            fee_entry_usd=0.0,
            score=70,
            personality="p",
            features=o.features,
        )
        mc = MarketContext.from_features(p.features)
        assert abs(mc.atr_pct - 1.58) < 1e-9
        assert mc.rsi == 55.0

    def test_place_market_order_accepte_features(self):
        """Signature seulement : l'exécution réelle exige un prix live."""
        import inspect

        from paper_trading.mexc_simulator import MexcSimulator

        sig = inspect.signature(MexcSimulator.place_market_order)
        assert "features" in sig.parameters
        assert sig.parameters["features"].default is None, "doit rester optionnel"
