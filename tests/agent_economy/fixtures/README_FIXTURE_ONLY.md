# FIXTURE_ONLY — AGENT-ECON A1 golden vectors

```text
FIXTURE_ONLY   NOT_REGISTRY_DATA   NOT_OPERATOR_DATA   NOT_DEPLOYED
```

`golden_vectors_FIXTURE_ONLY.json` holds synthetic AgentSpec / AgentRegistryEvent
material (`fixture_*` identities) and the expected identities, hashes, chain and
projection recomputed from the certified A1 contract formulas by the independent
stdlib reference in `tests/agent_economy/_reference.py`.

These are test vectors only. They are not agents, not registry data, not operator
data and are never deployed. No `.github/agents` profile is registered by them.
