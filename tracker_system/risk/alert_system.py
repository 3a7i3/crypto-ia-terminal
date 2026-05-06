"""
P0 — SYSTÈME D'ALERTES TEMPS RÉEL
Détecte: perte quotidienne, drawdown maximal, concentration excessive
"""

from datetime import datetime
from typing import Optional, List, Dict, Tuple


class AlertSystem:
    """Système d'alertes pour détection de risques en temps réel"""

    def __init__(self,
                 initial_capital: float = 10000.0,
                 daily_loss_threshold: float = -100.0,
                 drawdown_threshold: float = 0.15,
                 position_concentration_threshold: float = 0.80):
        """
        Args:
            initial_capital: Capital initial (ex: 10000)
            daily_loss_threshold: Seuil perte quotidienne (ex: -100)
            drawdown_threshold: Seuil drawdown (ex: 0.15 = 15%)
            position_concentration_threshold: Concentration max (ex: 0.80 = 80%)
        """
        self.initial_capital = initial_capital
        self.daily_loss_threshold = daily_loss_threshold
        self.drawdown_threshold = drawdown_threshold
        self.concentration_threshold = position_concentration_threshold

        self.current_equity = initial_capital
        self.max_equity = initial_capital
        self.daily_pnl = 0.0
        self.daily_start_equity = initial_capital
        self.alerts: List[Dict] = []

    def update_equity(self, new_equity: float) -> None:
        """Met à jour le patrimoine courant (appelé après chaque trade)"""
        self.current_equity = new_equity
        self.daily_pnl = new_equity - self.daily_start_equity

        if new_equity > self.max_equity:
            self.max_equity = new_equity

    def reset_daily(self) -> None:
        """Réinitialise PnL quotidien (appelé chaque jour à minuit)"""
        self.daily_pnl = 0.0
        self.daily_start_equity = self.current_equity

    def check_daily_loss(self) -> Optional[str]:
        """Vérifie si perte quotidienne > seuil"""
        if self.daily_pnl < self.daily_loss_threshold:
            msg = f"ALERTE: Perte quotidienne {self.daily_pnl:.2f}$ > {self.daily_loss_threshold:.2f}$"
            self._record_alert("DAILY_LOSS", msg, "ROUGE")
            return msg
        return None

    def check_drawdown(self) -> Optional[str]:
        """Vérifie si drawdown depuis max > seuil"""
        if self.max_equity > 0:
            dd = (self.max_equity - self.current_equity) / self.max_equity
            if dd > self.drawdown_threshold:
                msg = f"ALERTE: Drawdown {dd:.1%} > {self.drawdown_threshold:.1%} — STOP TRADING!"
                self._record_alert("DRAWDOWN", msg, "ROUGE_URGENT")
                return msg
        return None

    def check_position_concentration(self, positions: List[Dict]) -> Optional[str]:
        """Vérifie si exposition totale > seuil"""
        total_exposure = sum(p.get('size', 0) for p in positions)

        if self.current_equity > 0:
            exposure_ratio = total_exposure / self.current_equity
            if exposure_ratio > self.concentration_threshold:
                msg = f"ALERTE: Concentration {exposure_ratio:.1%} > {self.concentration_threshold:.1%}"
                self._record_alert("CONCENTRATION", msg, "ORANGE")
                return msg
        return None

    def run_all_checks(self, positions: List[Dict]) -> List[str]:
        """Exécute tous les checks et retourne les alertes"""
        alerts = []

        loss_alert = self.check_daily_loss()
        if loss_alert:
            alerts.append(loss_alert)

        dd_alert = self.check_drawdown()
        if dd_alert:
            alerts.append(dd_alert)

        conc_alert = self.check_position_concentration(positions)
        if conc_alert:
            alerts.append(conc_alert)

        return alerts

    def _record_alert(self, alert_type: str, message: str, severity: str) -> None:
        """Enregistre une alerte pour historique"""
        self.alerts.append({
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "message": message,
            "severity": severity,
            "equity": self.current_equity,
            "daily_pnl": self.daily_pnl,
        })

    def get_alert_history(self) -> List[Dict]:
        """Retourne l'historique des alertes"""
        return self.alerts.copy()

    def get_critical_alerts(self) -> List[Dict]:
        """Retourne seulement les alertes ROUGE_URGENT"""
        return [a for a in self.alerts if a['severity'] == 'ROUGE_URGENT']

    def summary(self) -> Dict:
        """Résumé de l'état du risque"""
        dd = (self.max_equity - self.current_equity) / self.max_equity if self.max_equity > 0 else 0

        return {
            "current_equity": self.current_equity,
            "daily_pnl": self.daily_pnl,
            "drawdown": dd,
            "max_equity": self.max_equity,
            "total_alerts": len(self.alerts),
            "critical_alerts": len(self.get_critical_alerts()),
        }
