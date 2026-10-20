"""Colony nursery laboratory: SOURCE_ONLY, LAB_ONLY, NOT_DEPLOYED.

Separate from the quantitative machine, the Operator API and Governance
Tower runtime. Individuals run as child processes under an external
supervisor, on fixtures only. Nothing here touches a VPS, a PPL/FIN ledger,
an exchange, credentials or GitHub writes; no permission is ever inherited.
"""

RUNTIME_DEPLOYED = False
