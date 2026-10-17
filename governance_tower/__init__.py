"""Governance Tower — quatrième application, isolée, de supervision READ-ONLY.

GOV-TOWER-00 / #459. Prototype local : un panel conversationnel unique et
l'agent SENTINEL-01 (capacité OBSERVE_ONLY). Aucune autorité opérationnelle,
aucun déploiement, aucun accès runtime, PPL, FIN, exchange ou secret.

Ce paquet n'importe ni ``core``, ni ``paper_trading``, ni ``financial_institute``,
ni ``governance`` (routeur de décision runtime), ni ``observability.operator_api``.
Seuls les contrats d'observation purs ``observability.runtime_service_contract``
et ``observability.storage_contract`` sont réutilisés en lecture.
"""

GT_VERSION = "0.1.0"
AGENT_ID = "SENTINEL-01"
CAPABILITY = "OBSERVE_ONLY"
OPERATIONAL_AUTHORITY = "DENIED"
RUNTIME_DEPLOYED = False
