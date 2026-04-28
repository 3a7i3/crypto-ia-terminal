class EmailNotifier:
    def __init__(self, smtp_server, from_addr, to_addr):
        self.smtp_server = smtp_server
        self.from_addr = from_addr
        self.to_addr = to_addr

    def notify(self, subject, message):
        footer = (
            "\n\n"
            "ℹ️ Documentation enrichie :\n"
            "- Guide complet, usages et plan d’action : README_CONSOLIDATED.md\n"
            "- Exemples dashboards : DASHBOARD_USAGE_TEMPLATES.md\n"
            "- Checklist projet : ACTION_PLAN_CHECKLIST.md\n"
            "\n"
            "ℹ️ Enhanced documentation :\n"
            "- Full guide, usage, and action plan: README_CONSOLIDATED.md\n"
            "- Dashboard examples: DASHBOARD_USAGE_TEMPLATES.md\n"
            "- Project checklist: ACTION_PLAN_CHECKLIST.md"
        )
        full_message = message + footer
        # TODO: Implémenter l'envoi d'email réel
        print(f"[EMAIL] {subject}: {full_message}")
