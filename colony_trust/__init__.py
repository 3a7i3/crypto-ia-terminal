"""Authentication of colony lab records: SOURCE_ONLY, LAB_ONLY, LAB_TEST keys only.

See docs/colony_trust/THREAT_MODEL_AND_TRUST_CONTRACT.md. Not wired into
colony_lab.Supervisor; it holds no key and accepts no non-test trust root.
"""

RUNTIME_DEPLOYED = False
