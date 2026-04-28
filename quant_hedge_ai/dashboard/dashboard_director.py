import streamlit as st


class DashboardDirector:
    def __init__(self, system_manager):
        self.system_manager = system_manager

    def get_system_status(self):
        return self.system_manager.collect_status()

    def restart_module(self, module_name):
        return self.system_manager.restart(module_name)

    def get_active_strategies(self):
        return self.system_manager.list_strategies()

    def trigger_evolution_cycle(self):
        return self.system_manager.run_evolution()

    def get_alerts(self):
        return self.system_manager.get_alerts()


# Dummy backend à remplacer par l’intégration réelle
class DummySystemManager:
    def collect_status(self):
        return {"data": "OK", "strategy": "OK", "risk": "OK", "execution": "OK"}

    def restart(self, module):
        return f"Module {module} redémarré."

    def list_strategies(self):
        return [
            {"name": "strat_1", "status": "active"},
            {"name": "strat_2", "status": "paused"},
        ]

    def run_evolution(self):
        return "Cycle d’évolution lancé."

    def get_alerts(self):
        return ["Alerte critique: drawdown élevé", "Info: tout est stable"]


system_manager = DummySystemManager()
director = DashboardDirector(system_manager)


def main():
    st.title("Dashboard Director (Streamlit)")
    st.header("État système")
    st.json(director.get_system_status())

    st.header("Stratégies actives")
    st.json(director.get_active_strategies())

    st.header("Alertes")
    for alert in director.get_alerts():
        st.warning(alert)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Redémarrer Data"):
            st.info(director.restart_module("data"))
    with col2:
        if st.button("Lancer Evolution"):
            st.success(director.trigger_evolution_cycle())


if __name__ == "__main__":
    main()
