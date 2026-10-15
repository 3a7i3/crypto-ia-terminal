# Rapport 4 — Gouvernance, non-feedback et non-mutation

**SATISFIED != CERTIFIED** ; **SOURCE_PROOF != RUNTIME_PROOF** ;
**CAPABILITY != AUTHORITY** ; **UNKNOWN != ZERO** ;
**HISTORICAL_RUNTIME_PROOF != CURRENT_RUNTIME_PROOF**.

Références recoupées dans #401, #286 et le commentaire constitutionnel
[#286 du 10 octobre](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6094710029) :

- epoch `BURN-IN-EPOCH-01-20260926T064144Z` ;
- source runtime historique `116634be0d3c015cce1cfa58be7da7255414fbfd` ;
- config SHA256 `9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4` ;
- `PB_MAX_POSITIONS=2`.

Ce sont des références de gouvernance historiques, pas une observation runtime
réeffectuée ici. #282 non finalisée, #286 ACTIVE. La clôture du burn-in n’a pas
été accomplie ; les étapes runtime S1 de l’issue ne sont pas exécutables dans
cette mission SOURCE-ONLY. Nouvelle epoch/GO après clôture : décision distincte.

## Preuves dans le périmètre de cette mission

Clone autonome sous `/workspace/crypto-ia-terminal`, branche isolée depuis main.
Ajouts limités à `research_stress/`, `tests/research_stress/` et ce dossier de
rapports. Aucun diff dans PAPER, PPL, FIN, PortfolioBrain, admission, Advisor,
stratégies, services, configuration active, dépendances ou workflows.
Pas d’installation de #397, pas de merge/cherry-pick, pas de dispatch de workflow.
Aucune commande VPS, systemctl, exchange ou Remote Desktop Commander exécutée.
Aucun secret production consulté. Aucun ledger production lu ou écrit.

Le runner est pur en mémoire ; la CLI lit explicitement le protocole et
éventuellement une **copie Research** déjà exportée, puis écrit uniquement stdout.
Aucun writer PPL/FIN/epoch, aucun moteur de trading, aucun promoteur, aucune
racine runtime ni découverte de service. L’utilisateur doit conserver stdout
dans une destination Research indépendante ; la CLI ne certifie pas un chemin
de redirection choisi par l’appelant. Aucun snapshot destiné à l’API active produit.

Tests : audit hook en processus neuf refuse écritures, sockets, subprocess et
mutations filesystem lors des imports transitifs + calcul ; vérification des
modules runtime interdits absents. Fixtures protégées et dataset hashés avant et
après exécution ; identité stable et contenu altéré rejeté. Les tests RB5 existants
complètent la preuve de non-feedback future-only. Ce n’est pas une preuve OS ou
une certification d’invariance du VPS contre d’autres acteurs concurrentiels.

Conclusion exacte : **aucune mutation ou rétroaction production effectuée par
cette mission**. L’état actuel externe de l’Advisor n’a pas été réobservé ; aucune
certification runtime PRE/POST n’est revendiquée. Ne pas interpréter le champ
source `NO_SOURCE_WRITE_OR_ACTIVATION_API` comme certificat runtime.

## Publication GitHub et rollback

Push uniquement de la branche Research ; Draft PR liée à #401, sans merge.
Audit des workflows suivis : Sphinx publication et notifications seulement sur
workflow_dispatch + main (#400 déjà intégré), bridge VPS seulement dispatch ou
push main du fichier audit_requests/request.json ; Testnet manuel non déclenché.
La PR déclenche les contrôles source applicables, pas un déploiement selon ces
workflows. Hooks/intégrations externes administrés hors Git ne sont pas attestés
absents ; aucune autorité sur eux ni certification globale de leurs effets.

Rollback de la proposition : fermer la Draft PR ou revenir au commit antérieur
sur une branche Research, conserver artifacts/provenance. Aucune opération
Advisor, retrait de service, activation FIN-02, Watchdog, TESTNET/LIVE, ordre
exchange ou rotation d’epoch ne fait partie de cette livraison.
