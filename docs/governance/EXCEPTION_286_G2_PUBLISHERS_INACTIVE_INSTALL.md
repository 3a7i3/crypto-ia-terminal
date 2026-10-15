# Texte proposé pour #286 — exception G2 (installation inactive des publishers) — NON PUBLIÉ
Statut : **brouillon préparé pour revue. Ni publié, ni exécuté.** À poster par Mathieu (3a7i3) s'il décide de l'accorder. La préparation de ce texte n'autorise pas l'exécution. Suite du [résultat `plan`](../runbooks/PASSIVE_PUBLISHERS_G2_PLAN_RESULTS.md) et du [plan G2–G5](../runbooks/PASSIVE_PUBLISHERS_G2_G5_PLAN.md).

---

**EXCEPTION GOV-286-PUBLISHERS-G2-INACTIVE — usage unique**

Date de décision : *[à renseigner par Mathieu]* (UTC) — Autorisant : Mathieu (3a7i3)

`ACTIVE_BURN_IN_IMMUTABILITY_GUARD` reste actif. J'autorise, pour cette seule opération, la modification de systemd de production strictement décrite ci-dessous, et rien d'autre.

**1. Empreintes imposées (toutes doivent correspondre, sinon l'exception ne s'applique pas)**
- Bloc `g2_paste_block.sh`, commit `6e7f419ddbd234a2d2fe6b192e508c7e92a6e0f4` : SHA-256 `3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803` (23 110 octets).
- Script G2 interne : SHA-256 `9ad589ecd67ce9b414c8ef1128fe38a30650b55533a9f4dfb17d446baf3422d5` (22 348 octets).
- Unités (copies revues du dépôt) :
  - `crypto-publish-runtime-service.service` `0ef373c474b380a03944d08a00c4b3666e8c0a3269039a9b2d704545dca0b1ad`
  - `crypto-publish-runtime-service.timer` `d1c779f0d9ebe3c9315e1b1ea0e9ef6695e9e1278d8d37755222c0023b3e53bd`
  - `crypto-publish-storage.service` `72149a4174344f226063c4a714b690cddbc21a0e9dd91f2921a62271b6b0d4a1`
  - `crypto-publish-storage.timer` `afeacf3ea6687980a7c19b012e1c6cc0b7be791d023a487be604e30bf68e18f4`

**2. Périmètre autorisé (et seulement celui-ci)**
1. État et sauvegardes G2 : création de `/var/lib/crypto-publishers-g2/` (root, 0700) avec son manifeste et `backup/`.
2. Création du dossier de présentation `/home/mathieu/operator_presentation` (0700, `mathieu`), s'il est absent. Un dossier existant n'est jamais modifié.
3. Création des quatre fichiers d'unité ci-dessus dans `/etc/systemd/system/` (root:root 0644), par fichier temporaire caché, vérification d'empreinte puis renommage. Tout fichier de même nom existant serait sauvegardé puis remplacé (au dernier relevé, 2026-10-15T05:21Z : aucun n'existe).
4. `systemctl daemon-reload`.
5. Le `rollback` correspondant du même script.

**3. Exécution**
Par l'opérateur `mathieu` sous sudo, une seule fois, avec le bloc ci-dessus déjà présent dans `~/g2-staging/` (empreinte complète revérifiée avant usage ; le shell privilégié recopie le script dans `/run`, root 0700, et recalcule son empreinte sur cette copie avant de l'exécuter). Aucun agent n'exécute d'`apply`, de `rollback` ni de sudo. Toute modification du bloc, du script ou d'une unité annule l'exception.

**4. Explicitement exclu**
`systemctl enable`, `start`, `stop`, `restart`, `link`, `mask` (aucun n'apparaît dans le script, testé) ; tout drop-in ; toute unité autre que les quatre ; Advisor (`crypto-advisor`), API (`crypto-operator-api`) et web (`crypto-operator-web`) : aucun redémarrage ni modification ; le checkout gelé, l'epoch, la config, `PB_MAX_POSITIONS`, PPL/FIN, stratégie, signaux, risk, sizing ; toute collecte, tout stress PAPER, TESTNET, LIVE, écriture exchange, Watchdog ; lecture d'`EnvironmentFile` ou de `.env` ; les variables d'API des vues Système (G4) ; les timers (G5) ; les exécutions ponctuelles (G3). **G3 à G5 restent exclus** et demandent chacune une exception et une autorisation propres.

**5. Conditions avant exécution** (le script les contrôle et s'arrête sans rien écrire sinon)
Advisor, API et web avec `NeedDaemonReload=no` ; aucune des quatre unités actives ni activée ; dossier de présentation absent ou déjà `mathieu 700` ; empreintes des unités embarquées conformes ; `systemd-analyze verify` à 0 ; pas de manifeste G2 existant ; au moins 10 Mio libres. Si l'une diffère, ne pas exécuter et me prévenir.

**6. Expiration et consommation**
Valable jusqu'au *[à fixer par Mathieu, proposition : 2026-10-15 18:00 UTC]* pour l'`apply`, et pour une seule tentative : elle est consommée dès le lancement (réussie, échouée, interrompue ou annulée). Une nouvelle tentative exige une nouvelle exception. L'expiration ne s'applique pas au `rollback`, qui reste autorisé tant que `/var/lib/crypto-publishers-g2/manifest` existe.

**7. Rollback — conditions et limites**
- Le manifeste est écrit et synchronisé **avant** chaque action ; une interruption (Ctrl-C, TERM, perte du terminal) conserve un état récupérable et affiche la commande de reprise (même bloc avec `G2_MODE=rollback`). Un arrêt brutal (SIGKILL, coupure) n'a pas de récupération automatique mais laisse le manifeste ; le `rollback` le lit.
- Le `rollback` ne supprime que les fichiers créés dont l'empreinte est celle installée, restaure les sauvegardes avec vérification d'empreinte, supprime un fichier temporaire résiduel, recharge systemd et vérifie l'absence des unités. Un fichier modifié depuis par un tiers n'est jamais écrasé et compte comme échec.
- Il n'affiche `RESULT: OK (rollback complete and verified)` que s'il y a **zéro** échec ; sinon `RESULT: FAILED — ROLLBACK INCOMPLETE`, avec l'état et les sauvegardes conservés. Un dossier de présentation non vide est laissé en place (« by design » : aucun artefact n'est supprimé).
- Le `rollback` refuse si une des quatre unités est activée ou active (il faudrait défaire G3 à G5 d'abord).
- Limites : `daemon-reload` relit toutes les unités du système, pas seulement les nôtres (il est protégé par `NeedDaemonReload=no` sur les trois unités gardées, pas sur les autres) ; les tests prouvent la logique avec un faux `systemctl`, pas le comportement de systemd sur l'hôte ; le journal est dans un répertoire root (il protège contre un oubli ou un état périmé, pas contre root).

**8. Portée de la preuve**
Cette installation ne prouve ni le démarrage des unités, ni la publication d'artefacts, ni l'état des vues Système. Elle ne certifie pas le runtime. `systemctl show`/`verify` après `apply` (mode `verify`, sans écriture) et le relevé « Advisor / API / web avant et après » du script seront consignés sur #286 après coup.

Signé : Mathieu (3a7i3), commentaire GitHub sur #286.

---

# Bloc `apply` prêt à exécuter (non exécuté)
À coller dans la session `mathieu` utilisée pour le déploiement frontend (`sudo` y avait fonctionné), **uniquement après** publication de l'exception ci-dessus. Il réutilise `~/g2-staging/g2_paste_block.sh`, revérifie son empreinte complète, affiche `sudo -l` (lecture seule, aucun droit modifié) puis demande de taper `APPLY`.

```sh
(
F="$HOME/g2-staging/g2_paste_block.sh"
H=3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803
echo "$H  $F" | sha256sum -c - &&
sudo -l &&
printf 'Installation INACTIVE G2 (exception #286 G2). Tapez APPLY pour lancer: ' &&
read -r A && [ "$A" = APPLY ] &&
G2_MODE=apply sh "$F"
echo "g2 apply chain exit status: $?"
)
```
- Chaîne en `&&` : empreinte ≠ → arrêt ; pas de sudo → arrêt ; autre réponse que `APPLY` → arrêt, rien n'est écrit. Les deux codes de retour s'affichent (`G2 apply exit status` du bloc, puis la chaîne).
- Le shell privilégié ne s'exécute qu'après avoir recalculé l'empreinte `9ad589ec…` sur sa copie root dans `/run` (« HASH MISMATCH OF THE PROTECTED COPY: not run » sinon).
- Contrôle après `apply` (sans sudo, lecture seule) : même bloc avec `sudo -l`, la question et `G2_MODE=apply` remplacés par `G2_MODE=verify sh "$F"`.
- Annulation (même exception, sudo) : même bloc, `G2_MODE=rollback`. Un échec de `apply` imprime la marche à suivre ; ne rien relancer sans m'avoir montré la sortie.
- Testé localement avec un faux `sudo` : refus sur toute réponse autre que `APPLY`, arrêt sur empreinte invalide, un seul `sudo -l` avant exécution. Le comportement réel de `sudo` et de systemd sur l'hôte n'est pas prouvé.
