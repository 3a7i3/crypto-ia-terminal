import logging
from unittest.mock import MagicMock

import pytest

from core.quant import logging_alerts


@pytest.fixture(autouse=True)
def clean_logger_handlers():
    """Isole chaque test : sauvegarde et restaure les handlers du logger."""
    original_handlers = list(logging_alerts.logger.handlers)
    original_level = logging_alerts.logger.level
    yield
    logging_alerts.logger.handlers = original_handlers
    logging_alerts.logger.setLevel(original_level)


@pytest.fixture()
def file_logger(tmp_path):
    """Redirige le logger vers un fichier temporaire, retourne son chemin."""
    log_file = tmp_path / "quant_system.log"
    logging_alerts.logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging_alerts.logger.addHandler(handler)
    return log_file


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLogLevels:
    def test_info(self, file_logger):
        logging_alerts.log_and_alert("info", "message info")
        content = _read(file_logger)
        assert "message info" in content
        assert "INFO" in content

    def test_error(self, file_logger):
        logging_alerts.log_and_alert("error", "message error")
        content = _read(file_logger)
        assert "message error" in content
        assert "ERROR" in content

    def test_warning(self, file_logger):
        logging_alerts.log_and_alert("warning", "message warning")
        content = _read(file_logger)
        assert "WARNING" in content

    def test_critical(self, file_logger):
        logging_alerts.log_and_alert("critical", "message critique")
        content = _read(file_logger)
        assert "CRITICAL" in content

    def test_debug(self, file_logger):
        logging_alerts.log_and_alert("debug", "message debug")
        content = _read(file_logger)
        assert "DEBUG" in content

    def test_unknown_level_defaults_to_info(self, file_logger):
        logging_alerts.log_and_alert("UNKNOWN_LEVEL", "fallback info")
        content = _read(file_logger)
        assert "fallback info" in content
        assert "INFO" in content

    def test_warn_alias(self, file_logger):
        logging_alerts.log_and_alert("warn", "alias warn")
        content = _read(file_logger)
        assert "WARNING" in content


class TestAlertDispatch:
    def test_notifier_called_when_alert_true(self, file_logger):
        notifier = MagicMock()
        logging_alerts.log_and_alert(
            "error", "alerte critique", alert=True, notifier=notifier
        )
        notifier.notify.assert_called_once()
        call_arg = notifier.notify.call_args[0][0]
        assert "alerte critique" in call_arg
        assert "ERROR" in call_arg

    def test_notifier_not_called_when_alert_false(self, file_logger):
        notifier = MagicMock()
        logging_alerts.log_and_alert(
            "info", "silencieux", alert=False, notifier=notifier
        )
        notifier.notify.assert_not_called()

    def test_notifier_not_called_when_none(self, file_logger):
        logging_alerts.log_and_alert(
            "error", "sans notifier", alert=True, notifier=None
        )
        content = _read(file_logger)
        assert "sans notifier" in content

    def test_broken_notifier_does_not_propagate(self, file_logger):
        broken = MagicMock()
        broken.notify.side_effect = RuntimeError("réseau mort")
        logging_alerts.log_and_alert(
            "error", "msg avec notifier cassé", alert=True, notifier=broken
        )
        content = _read(file_logger)
        assert "msg avec notifier cassé" in content
        assert "réseau mort" in content or "Erreur notifier" in content
