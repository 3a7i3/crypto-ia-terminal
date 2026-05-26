# CURRENT_TASK

## Focus actuel

Preparer la suite P7 en verrouillant les pannes silencieuses, en corrigeant les problemes visibles, et en gardant une documentation courte de reprise.

## Contexte utile

- Le depot contient plusieurs systemes distincts, avec `quant-hedge-ai` comme priorite principale
- La documentation est abondante; un inventaire de surete existe maintenant dans `docs/MODULE_SAFETY_INVENTORY.md`
- L'audit des tests racine est bien avance, avec seulement quelques fichiers encore a revoir
- Des notes d'architecture existent deja sur les zones fragiles autour de `DecisionPacket`, des regimes et de la gouvernance risque
- Les composants P7 principaux existent deja : `RiskGovernor`, `CapitalThrottle`, `DynamicExposureManager`, `ComponentCircuitBreaker`

## Definition de termine

- `README.md`, `BUGS.md`, `ARCHITECTURE_NOTES.md` et `ROADMAP.md` refletent l'etat reel
- `docs/MODULE_SAFETY_INVENTORY.md` decrit les modules, avantages, vulnerabilites et controles
- Les tests P7/risk/safety peuvent etre relances des que Python local est restaure
- Le verdict `SystemSafetyAuditor` est cable dans `advisor_loop.py` pour bloquer les nouvelles positions si une couche critique P7 tombe

## Chantiers actifs

1. Restaurer l'environnement Python local (`BUG-007`)
2. Relancer les tests ajoutes/modifies : P7, risk gate, safety auditor
3. Verifier en dry-run le blocage `SystemSafetyAuditor`
4. Continuer la revue des tests racine encore ambigus

## Points d'attention

- Blocage validation local : `.venv` pointe vers un Python 3.11 absent
- Principal risque court terme : certaines exceptions critiques hors P7 sont encore catch/loggees sans `error_bus.emit()`
- Principal risque technique : contrats implicites entre moteur de signal, regimes, conviction et risk gate

## Prochaines actions

1. Restaurer Python/.venv puis executer `pytest tests/test_p7_validation.py tests/test_global_risk_gate.py tests/test_safety_auditor.py`
2. Verifier le verdict `SystemSafetyAuditor` en dry-run
3. Router les exceptions critiques restantes vers `error_bus.emit()`
4. Revoir les tests racine encore en zone grise
5. Faire vivre `ROADMAP.md` quand les priorites changent

## Notes

Cette page doit rester courte, concrete et orientee execution.
