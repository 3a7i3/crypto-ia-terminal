"""Panel registry used by tests and tooling.

This module keeps lightweight metadata about dashboard/panel entrypoints so
test code can inspect tutorial coverage without importing full Streamlit apps.
"""

from __future__ import annotations

from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent


PANEL_SPECS = [
    {
        "module": "dashboard.alert_dashboard",
        "label": "Supervision & Auto-Heal",
        "source": WORKSPACE_ROOT / "dashboard" / "alert_dashboard.py",
    },
    {
        "module": "supervision.botdoctor_dashboard",
        "label": "BotDoctor Dashboard",
        "source": WORKSPACE_ROOT / "supervision" / "botdoctor_dashboard.py",
    },
    {
        "module": "evolution_dashboard",
        "label": "Evolution Multi-Monde",
        "source": WORKSPACE_ROOT / "evolution_dashboard.py",
    },
    {
        "module": "evolution_3d_view",
        "label": "3D Evolution Viewer",
        "source": WORKSPACE_ROOT / "evolution_3d_view.py",
    },
    {
        "module": "crypto_quant_v16.ui.quant_dashboard",
        "label": "Quant V16 Panel",
        "source": WORKSPACE_ROOT / "crypto_quant_v16" / "ui" / "quant_dashboard.py",
    },
    {
        "module": "quant_hedge_ai.dashboard.quant_terminal_v12",
        "label": "Quant Terminal V12",
        "source": WORKSPACE_ROOT / "quant_hedge_ai" / "dashboard" / "quant_terminal_v12.py",
    },
    {
        "module": "ai_autonomous_loop.feedback_dashboard",
        "label": "Feedback Dashboard",
        "source": WORKSPACE_ROOT / "ai_autonomous_loop" / "feedback_dashboard.py",
    },
]


__all__ = ["PANEL_SPECS", "WORKSPACE_ROOT"]