"""
Tests pour supervise_all.py : import, build_doctor, run_once, rapport.
"""

from unittest.mock import MagicMock


from supervision.bot_doctor import BotDoctor
from supervision.custom_module import CustomTradingModule


class TestImport:
    def test_importable_without_logs_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import supervise_all  # ne doit pas crasher même sans logs/

        assert supervise_all is not None

    def test_build_doctor_returns_bot_doctor(self):
        import supervise_all

        doctor = supervise_all.build_doctor()
        assert isinstance(doctor, BotDoctor)

    def test_build_doctor_with_custom_modules(self):
        import supervise_all

        modules = [CustomTradingModule("Test", True)]
        doctor = supervise_all.build_doctor(modules=modules)
        assert len(doctor.modules) == 1

    def test_build_doctor_with_custom_notifier(self):
        import supervise_all

        notifier = MagicMock()
        doctor = supervise_all.build_doctor(notifier=notifier)
        assert doctor.notifier is notifier


class TestRunOnce:
    def test_returns_health_score_and_report(self):
        import supervise_all

        modules = [CustomTradingModule("A", True), CustomTradingModule("B", True)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=MagicMock())
        result = supervise_all.run_once(doctor)
        assert "health_score" in result
        assert "report" in result

    def test_health_score_all_healthy(self):
        import supervise_all

        modules = [CustomTradingModule("A", True), CustomTradingModule("B", True)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=MagicMock())
        result = supervise_all.run_once(doctor)
        assert result["health_score"] == 100.0

    def test_health_score_all_unhealthy(self):
        import supervise_all

        modules = [CustomTradingModule("A", False), CustomTradingModule("B", False)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=MagicMock())
        result = supervise_all.run_once(doctor)
        assert result["health_score"] == 0.0

    def test_report_length_matches_modules(self):
        import supervise_all

        modules = [CustomTradingModule(f"M{i}", True) for i in range(4)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=MagicMock())
        result = supervise_all.run_once(doctor)
        assert len(result["report"]) == 4

    def test_notifier_called_on_unhealthy(self):
        import supervise_all

        notifier = MagicMock()
        modules = [CustomTradingModule("Sick", False)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=notifier)
        supervise_all.run_once(doctor)
        notifier.notify.assert_called_once()

    def test_notifier_not_called_when_all_healthy(self):
        import supervise_all

        notifier = MagicMock()
        modules = [CustomTradingModule("OK", True)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=notifier)
        supervise_all.run_once(doctor)
        notifier.notify.assert_not_called()

    def test_run_once_multiple_times_updates_report(self):
        import supervise_all

        modules = [CustomTradingModule("M", True)]
        doctor = supervise_all.build_doctor(modules=modules, notifier=MagicMock())
        r1 = supervise_all.run_once(doctor)
        r2 = supervise_all.run_once(doctor)
        assert r1["health_score"] == r2["health_score"]


class TestCustomNotifier:
    def test_notifies_on_custom_keyword(self, capsys):
        from supervise_all import CustomNotifier

        n = CustomNotifier()
        n.notify("custom alert!")
        captured = capsys.readouterr()
        assert "ALERTE CUSTOM" in captured.out

    def test_silent_on_non_custom_message(self, capsys):
        from supervise_all import CustomNotifier

        n = CustomNotifier()
        n.notify("ordinary message")
        captured = capsys.readouterr()
        assert captured.out == ""
