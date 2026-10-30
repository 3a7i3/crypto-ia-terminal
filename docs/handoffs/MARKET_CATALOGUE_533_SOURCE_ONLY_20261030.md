# MARKET-CATALOGUE-01 — préparation source du 30 octobre 2026

Mission #533. Branche `feat/market-catalogue-heatmap-20261030`.
Base exacte : `0967a56924cc9fccc8b8cee386b591ba3fa5f885`.
Statut au présent rapport : **préparé et testé**, non fusionné, non installé,
non démarré sur les services actifs. Aucune admission scientifique.

## Résultat préparé

La source v1.1 optionnelle publie toutes les observations datées de la fenêtre
et toutes les lignes au seuil, sans modifier les fonctions de score/classement.
L’interface conserve 20 résultats par page, cherche dans tout le catalogue fourni,
rend les symboles sous le seuil consultables et propose une carte compacte.
Elle conserve la compatibilité v1.0 et explique sa couverture partielle.

Les tests synthétiques placent BTC hors des 20 premiers et ETH sous le seuil.
Ils vérifient le changement explicite de population, les fenêtres UTC 1 h/4 h,
les exclusions, le clavier, la pagination, les filtres et le remplacement
d’une source lors des relectures.

Les métriques Δscore 5/15 min, RVOL, densité courte et transitions datées ne sont
pas calculables à partir de la capture actuelle. Leur protocole est documenté
dans [MARKET-TIMING-01](../research/MARKET_TIMING_01_PROTOCOL.md), sans multiplier
le score ni promouvoir un tri scalping/institutionnel.
Le contrat figure dans [MARKET-CATALOGUE-01](../contracts/MARKET_CATALOGUE_01.md).

## Vérification locale réellement effectuée

Sur `crypto-restore-01`, accès Remote Desktop Commander confirmé comme
`lecanada26`, UID 1001. Checkout, dépendances, fixtures et build isolés sous
`~/crypto-install/worktrees/market-catalogue-533-20261030` et
`~/crypto-install/audit-browser/market-catalogue-533-20261030`.

| Contrôle | Résultat |
| --- | --- |
| Python ciblé + intégralité `tests/cross_stack/` | 160 PASS |
| Frontend complet, 20 fixtures synthétiques | 509 PASS, 39 fichiers, aucun skip |
| Contrat serveur local / PWA | 17 PASS |
| TypeScript + build production | PASS |
| Ruff des 5 fichiers Python concernés | PASS |
| Audit npm production | 0 vulnérabilité déclarée |
| Chromium avec sandbox, 1440/768/393 px, clair/sombre | 361 assertions PASS |
| Scénarios navigateur / captures | 20 scénarios, 50 contrôles de largeur et 50 captures |
| Débordement horizontal / erreur JS / requête externe ou mutante | 0 |
| Contraste minimal des tuiles, texte normal | clair 8,16:1 ; sombre 7,14:1 |

Toutes les API de l’audit navigateur sont interceptées avec des fixtures
issues des producteurs/lecteurs réels. Aucun serveur HTTP n’est lancé pour
cet audit et aucun appel n’atteint l’API active. Service workers bloqués.
La normalisation finale de fin de ligne ne change pas les exécutables construits.

Avertissements de l’environnement isolé : option pytest-asyncio non chargée ;
dépréciation Starlette/httpx de la pile verrouillée ; avertissement Vite sur
son futur chargeur de configuration. Les contrôles ci-dessus sont réussis ;
ces avertissements ne sont pas présentés comme des certifications runtime.

## État actif préservé

Garde-fou #532, SHA256
`69049ae900d6aaec454292b664d1e755f4c505cbe99cbc08226ddab9b9b95119`,
relancé en lecture seule à **2026-10-30T22:32:49Z** :
`READ_ONLY_MARKET_PRESENTATION_PASS`.

- API PID 79546 ; web PID 143612 ; mêmes processus et durcissement.
- Présentation : un seul fichier `cryptoradar_market_snapshot.json`.
- SHA256 `46c2f0d3704f3dbf6dcc4df541870a7cb72fadd2ca812736c87d3243d40eaa4e`.
- Aucun start/stop/restart/reload/enable, donnée d’origine modifiée, lecture des
  JSONL récupérés, collecteur, notification ou moteur activé.

## Preuves conservées et prochaine action

Les preuves locales sont dans le répertoire d’audit ci-dessus.
`visual/checks.json` : SHA256
`cd1c1df826989ccd433b5c923e7ab75441be481af3c3cd038c11d936160c1a9e`.
`live-final.json` : SHA256
`6dc21509862ca24ae5f6e1e79541842625caa4ac4748ffb8a7d5ad580f823613`.
Le workflow cross-stack régénère le catalogue, teste React et publie les
captures synthétiques dans ses artifacts GitHub. La CI de la PR reste à
consulter à son HEAD exact ; les résultats locaux ne la remplacent pas.

Prochaine action source : revue du diff exact et contrôles de la PR.
Prochaine action runtime : définir une admission distincte comprenant le
lecteur API compatible v1.1, l’interface exacte, la source autorisée et le rollback.
La capture active de 20 lignes ne peut pas être complétée à partir de ses
seuls agrégats. L’autorisation ponctuelle #532 reste consommée.
