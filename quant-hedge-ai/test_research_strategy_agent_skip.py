"""
Test d'intégration ResearchStrategyAgent pour quant-hedge-ai
Ce fichier a été renommé pour éviter les conflits d'import pytest
"""

if __name__ == "__main__":
    import os
    import sys

    try:
        sys.path.append(
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "../shared/agents/research_strategy_agent",
                )
            )
        )
        from agent import ResearchStrategyAgent
    except ImportError:
        from shared.agents.research_strategy_agent.agent import \
            ResearchStrategyAgent

    def test_agent_cycle():
        agent = ResearchStrategyAgent(simulation_mode=True, max_cycles=2)
        market_data = {"BTCUSDT": {"price": 50000, "volume": 1200}}
        system_state = {"exposure": 0.1}
        objectif = {"type": "croissance"}
        contraintes = {"max_drawdown": 0.15}
        result = agent.run_autonomous_cycle(
            market_data, system_state, objectif, contraintes
        )
        assert isinstance(result, list)
        assert len(result) > 0
        print("[quant-hedge-ai] Test OK", result)

    test_agent_cycle()
else:
    # Pytest ignore ce fichier pour éviter le mismatch
    import pytest

    pytest.skip(
        "Test ignoré pour éviter le conflit de nom de module avec crypto_quant_v16/test_research_strategy_agent.py",
        allow_module_level=True,
    )
