"""Colony registrar: gated births, including from a qualified descendant. SOURCE_ONLY, LAB_ONLY.

See docs/colony_registrar/REGISTRAR_CONTRACT.md. Called by the operator only;
no lab task, worker or module imports it, and it creates no individual by
itself.
"""

RUNTIME_DEPLOYED = False
