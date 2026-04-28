"""Re-export depuis core.quant.logging_alerts pour compatibilité terminal_core.*"""

from core.quant.logging_alerts import log_and_alert, logger, logging

__all__ = ["log_and_alert", "logger", "logging"]
