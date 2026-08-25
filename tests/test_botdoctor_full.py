"""
Tests complets pour BotDoctor, ModuleStatus et health_score.
"""

from unittest.mock import MagicMock


from supervision.bot_doctor import BotDoctor, ModuleStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class HealthyModule:
    name = "HealthyA"
    is_healthy = True


class UnhealthyModule:
    name = "UnhealthyB"
    is_healthy = False


class CallableHealthyModule:
    name = "CallableOK"

    def is_healthy(self):
        return True


class CallableUnhealthyModule:
    name = "CallableKO"

    def is_healthy(self):
        return False


class CrashingModule:
    name = "Crasher"

    @property
    def is_healthy(self):
        raise RuntimeError("disk full")


# ---------------------------------------------------------------------------
# ModuleStatus
# ---------------------------------------------------------------------------


class TestModuleStatus:
    def test_to_dict_keys(self):
        s = ModuleStatus("mod", True)
        d = s.to_dict()
        assert set(d) == {"name", "is_healthy", "last_checked", "error"}

    def test_last_checked_is_iso_string(self):
        s = ModuleStatus("mod", True)
        assert "T" in s.last_checked  # format ISO 8601

    def test_error_none_by_default(self):
        s = ModuleStatus("mod", True)
        assert s.error is None


# ---------------------------------------------------------------------------
# check_module — attribut booléen
# ---------------------------------------------------------------------------


class TestCheckModuleBool:
    def test_healthy_attr(self):
        doctor = BotDoctor([])
        status = doctor.check_module(HealthyModule())
        assert status.is_healthy is True
        assert status.error is None

    def test_unhealthy_attr(self):
        doctor = BotDoctor([])
        status = doctor.check_module(UnhealthyModule())
        assert status.is_healthy is False
        assert status.error is not None

    def test_name_taken_from_module(self):
        doctor = BotDoctor([])
        status = doctor.check_module(HealthyModule())
        assert status.name == "HealthyA"

    def test_name_fallback_to_str(self):
        class NoName:
            is_healthy = True

        doctor = BotDoctor([])
        status = doctor.check_module(NoName())
        assert isinstance(status.name, str)


# ---------------------------------------------------------------------------
# check_module — is_healthy callable
# ---------------------------------------------------------------------------


class TestCheckModuleCallable:
    def test_callable_healthy(self):
        doctor = BotDoctor([])
        status = doctor.check_module(CallableHealthyModule())
        assert status.is_healthy is True

    def test_callable_unhealthy(self):
        doctor = BotDoctor([])
        status = doctor.check_module(CallableUnhealthyModule())
        assert status.is_healthy is False
        assert status.error is not None

    def test_callable_raising_marks_unhealthy(self):
        doctor = BotDoctor([])
        status = doctor.check_module(CrashingModule())
        assert status.is_healthy is False
        assert "disk full" in status.error


# ---------------------------------------------------------------------------
# run() + get_report()
# ---------------------------------------------------------------------------


class TestRun:
    def test_all_healthy(self):
        doctor = BotDoctor([HealthyModule(), CallableHealthyModule()])
        statuses = doctor.run()
        assert all(s.is_healthy for s in statuses)

    def test_mixed_modules(self):
        doctor = BotDoctor(
            [HealthyModule(), UnhealthyModule(), CallableHealthyModule()]
        )
        statuses = doctor.run()
        healthy = [s for s in statuses if s.is_healthy]
        unhealthy = [s for s in statuses if not s.is_healthy]
        assert len(healthy) == 2
        assert len(unhealthy) == 1

    def test_get_report_matches_run(self):
        doctor = BotDoctor([HealthyModule(), UnhealthyModule()])
        doctor.run()
        report = doctor.get_report()
        assert len(report) == 2
        assert all(isinstance(r, dict) for r in report)

    def test_notifier_called_only_for_unhealthy(self):
        notifier = MagicMock()
        doctor = BotDoctor([HealthyModule(), UnhealthyModule()], notifier=notifier)
        doctor.run()
        assert notifier.notify.call_count == 1
        msg = notifier.notify.call_args[0][0]
        assert "UnhealthyB" in msg

    def test_notifier_error_does_not_crash(self):
        notifier = MagicMock()
        notifier.notify.side_effect = ConnectionError("réseau mort")
        doctor = BotDoctor([UnhealthyModule()], notifier=notifier)
        doctor.run()  # ne doit pas lever d'exception

    def test_run_updates_statuses(self):
        doctor = BotDoctor([HealthyModule()])
        assert doctor.statuses == []
        doctor.run()
        assert len(doctor.statuses) == 1


# ---------------------------------------------------------------------------
# health_score
# ---------------------------------------------------------------------------


class TestHealthScore:
    def test_all_healthy_gives_100(self):
        doctor = BotDoctor([HealthyModule(), CallableHealthyModule()])
        doctor.run()
        assert doctor.health_score == 100.0

    def test_all_unhealthy_gives_0(self):
        doctor = BotDoctor([UnhealthyModule(), CallableUnhealthyModule()])
        doctor.run()
        assert doctor.health_score == 0.0

    def test_half_healthy_gives_50(self):
        doctor = BotDoctor([HealthyModule(), UnhealthyModule()])
        doctor.run()
        assert doctor.health_score == 50.0

    def test_no_modules_gives_100(self):
        doctor = BotDoctor([])
        doctor.run()
        assert doctor.health_score == 100.0

    def test_score_before_run_gives_100(self):
        doctor = BotDoctor([UnhealthyModule()])
        # Pas encore lancé — statuses vide
        assert doctor.health_score == 100.0
