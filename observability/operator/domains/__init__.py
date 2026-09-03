"""The 11 canonical observability domains (mission §5).

Each module here defines:
- a frozen ``*Snapshot`` dataclass extending ``DomainSnapshot``;
- a pure ``compose_*_snapshot()`` function that takes already-computed,
  primitive/``ObservedValue``-typed inputs and returns a snapshot — it
  never imports or calls a producer module itself, so this package stays
  decoupled from the engine and free of import-time side effects;
- ``METRICS``: the ``MetricDefinition``s this domain contributes to the
  canonical registry;
- ``MODULES``: the ``ModuleDescriptor``s documenting which existing
  repository components are canonical/duplicated/legacy/unused for this
  domain (forensic inventory, mission §4).
"""
