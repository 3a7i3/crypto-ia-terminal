"""
capital_deployment/tests/test_f05_phase_certifier.py — F-05 Phase Certifier

Tests de certification :
  - certify() avec force=True réussit toujours
  - certify() sans force échoue si KPIs insuffisants
  - HMAC signature vérifiable après certify()
  - Signature invalide avec mauvaise clé
  - save() + load() round-trip préserve la certification
  - is_certified() = True après certify + verify
  - is_certified() = False si certification absente
  - all_certified_to() valide la chaîne de phases
  - certified_phases() retourne les phases certifiées
  - PhaseCertification.to_dict() complet
  - PhaseCertification.from_dict() round-trip

Total : 11 tests
"""

from __future__ import annotations

import time

import pytest

from capital_deployment.phase_certifier import PhaseCertification, PhaseCertifier
from capital_deployment.phase_kpi_tracker import PhaseKPITracker, TradeRecord


def _make_trade(pnl: float, ts: float) -> TradeRecord:
    return TradeRecord(
        ts=ts,
        pnl=pnl,
        symbol="BTC",
        side="buy",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        signed=True,
    )


def _empty_tracker(phase: str = "F-01") -> PhaseKPITracker:
    return PhaseKPITracker(phase=phase, initial_capital=100.0)


class TestCertifyForce:
    def test_certify_force_true_always_succeeds(self):
        """certify(force=True) réussit quel que soit l'état des KPIs."""
        certifier = PhaseCertifier(key=b"test_key")
        tracker = _empty_tracker("F-01")
        cert = certifier.certify("F-01", tracker, force=True)
        assert cert.phase == "F-01"
        assert cert.hmac_sig != ""

    def test_certify_force_false_fails_empty_tracker(self):
        """certify(force=False) lève ValueError si critères non remplis."""
        certifier = PhaseCertifier(key=b"test_key")
        tracker = _empty_tracker("F-01")
        with pytest.raises(ValueError, match="non certifiable"):
            certifier.certify("F-01", tracker, force=False)


class TestHMACSignature:
    def test_signature_verifiable_after_certify(self):
        """La certification est vérifiable avec la même clé."""
        key = b"secret_p10_key"
        certifier = PhaseCertifier(key=key)
        tracker = _empty_tracker("F-01")
        cert = certifier.certify("F-01", tracker, force=True)
        assert cert.verify(key) is True

    def test_signature_invalid_with_wrong_key(self):
        """Signature invalide avec une clé différente."""
        certifier = PhaseCertifier(key=b"correct_key")
        tracker = _empty_tracker("F-01")
        cert = certifier.certify("F-01", tracker, force=True)
        assert cert.verify(b"wrong_key") is False

    def test_empty_sig_not_verified(self):
        """PhaseCertification sans signature → verify() = False."""
        cert = PhaseCertification(
            phase="F-01",
            certified_at=time.time(),
            duration_days=7.0,
            final_win_rate=0.5,
            final_sharpe=1.5,
            final_max_drawdown=0.01,
            total_trades=10,
            unsigned_decisions=0,
            hmac_sig="",
        )
        assert cert.verify(b"any_key") is False


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        """save() + load() préserve les certifications."""
        path = tmp_path / "certs.json"
        key = b"roundtrip_key"
        certifier1 = PhaseCertifier(key=key)
        tracker = _empty_tracker("F-01")
        certifier1.certify("F-01", tracker, force=True)
        certifier1.save(path)
        assert path.exists()

        certifier2 = PhaseCertifier(key=key)
        certifier2.load(path)
        assert certifier2.is_certified("F-01")

    def test_load_missing_file_silently(self, tmp_path):
        """Chargement d'un fichier absent → pas d'exception."""
        certifier = PhaseCertifier()
        certifier.load(tmp_path / "nonexistent.json")  # ne doit pas crasher


class TestIsCertified:
    def test_is_certified_true_after_certify(self):
        """is_certified() = True après certify."""
        certifier = PhaseCertifier(key=b"key")
        tracker = _empty_tracker("F-01")
        certifier.certify("F-01", tracker, force=True)
        assert certifier.is_certified("F-01") is True

    def test_is_certified_false_absent(self):
        """is_certified() = False si phase non certifiée."""
        certifier = PhaseCertifier()
        assert certifier.is_certified("F-01") is False
        assert certifier.is_certified("F-99") is False

    def test_all_certified_to_requires_chain(self):
        """all_certified_to() = True seulement si toutes les phases précédentes le sont."""
        certifier = PhaseCertifier(key=b"key")
        tracker = _empty_tracker("F-01")
        certifier.certify("F-01", tracker, force=True)
        certifier.certify("F-02", tracker, force=True)

        assert certifier.all_certified_to("F-02") is True
        assert certifier.all_certified_to("F-03") is False  # F-03 manquante

    def test_certified_phases_list(self):
        """certified_phases() retourne la liste des phases certifiées."""
        certifier = PhaseCertifier(key=b"key")
        tracker = _empty_tracker("F-01")
        certifier.certify("F-01", tracker, force=True)
        certifier.certify("F-03", tracker, force=True)
        phases = certifier.certified_phases()
        assert "F-01" in phases
        assert "F-03" in phases
        assert "F-02" not in phases


class TestSerialization:
    def test_to_dict_complete(self):
        """PhaseCertification.to_dict() contient tous les champs requis."""
        cert = PhaseCertification(
            phase="F-02",
            certified_at=time.time(),
            duration_days=14.0,
            final_win_rate=0.52,
            final_sharpe=1.3,
            final_max_drawdown=0.025,
            total_trades=42,
            unsigned_decisions=0,
        )
        cert.sign(b"key")
        d = cert.to_dict()
        for key in (
            "phase",
            "certified_at",
            "duration_days",
            "final_win_rate",
            "final_sharpe",
            "final_max_drawdown",
            "total_trades",
            "unsigned_decisions",
            "hmac_sig",
        ):
            assert key in d, f"Clé manquante: {key}"

    def test_from_dict_roundtrip(self):
        """PhaseCertification.to_dict() → from_dict() round-trip."""
        key = b"roundtrip"
        cert1 = PhaseCertification(
            phase="F-03",
            certified_at=1_700_000_000.0,
            duration_days=21.0,
            final_win_rate=0.55,
            final_sharpe=1.6,
            final_max_drawdown=0.05,
            total_trades=100,
            unsigned_decisions=0,
        )
        cert1.sign(key)
        d = cert1.to_dict()
        cert2 = PhaseCertification.from_dict(d)
        assert cert2.phase == "F-03"
        assert cert2.final_sharpe == pytest.approx(1.6, abs=0.001)
        assert cert2.verify(key) is True
