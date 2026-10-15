# Texte proposé pour #286 — exception G3 (essais ponctuels des publishers) — NON PUBLIÉ
Statut : **brouillon préparé pour revue. Ni publié, ni exécuté.** À poster par Mathieu (3a7i3) s'il décide de l'accorder. La préparation de ce texte n'autorise pas l'exécution. Suite de [G2 apply/verify](../runbooks/PASSIVE_PUBLISHERS_G2_APPLY_RESULTS.md) et du [plan G2–G5](../runbooks/PASSIVE_PUBLISHERS_G2_G5_PLAN.md).

---

**EXCEPTION GOV-286-PUBLISHERS-G3-ONESHOT — deux usages (un par publisher)**

Date de décision : *[à renseigner par Mathieu]* (UTC) — Autorisant : Mathieu (3a7i3)

`ACTIVE_BURN_IN_IMMUTABILITY_GUARD` reste actif. J'autorise, pour ces seules opérations, les lancements ponctuels de systemd strictement décrits ci-dessous, et rien d'autre.

**1. Empreintes imposées (toutes doivent correspondre, sinon l'exception ne s'applique pas)**
- Bloc `g3_paste_block.sh` : SHA-256 `af9470511fbc5f4dea71f7adc7840bd3ca10557adf651470cd3962a65e9378a8` (12973 octets).
- Script G3 interne : SHA-256 `bdc9c3b007b22428cf1654945d1ea2ed376ca86d7acc33193a44efa9688e69cb` (12096 octets).
- Unités déjà installées par G2 (aucune modification) : `crypto-publish-runtime-service.service` `0ef373c474b380a03944d08a00c4b3666e8c0a3269039a9b2d704545dca0b1ad` ; `crypto-publish-runtime-service.timer` `d1c779f0d9ebe3c9315e1b1ea0e9ef6695e9e1278d8d37755222c0023b3e53bd` ; `crypto-publish-storage.service` `72149a4174344f226063c4a714b690cddbc21a0e9dd91f2921a62271b6b0d4a1` ; `crypto-publish-storage.timer` `afeacf3ea6687980a7c19b012e1c6cc0b7be791d023a487be604e30bf68e18f4`.

**2. Périmètre autorisé (et seulement celui-ci)**
Pour **un publisher à la fois**, d'abord `runtime-service`, puis `storage` seulement si le premier est entièrement réussi :
1. Exactement **trois** `systemctl start crypto-publish-<publisher>.service` (le service oneshot sélectionné, jamais le timer), espacés d'au moins 5 s, l'un après l'autre. Six lancements au plus pour l'ensemble.
2. Effets attendus : écriture atomique de l'artefact du publisher dans `/home/mathieu/operator_presentation/` (`runtime_service_snapshot.json` ou `storage_snapshot.json`, `mathieu` 0600) ; entrées de journal ; état d'exécution d'unité (Result, horodatages, compteurs) ; `storage` ne lit que les métadonnées de `decision_packets_*.jsonl` sans les ouvrir.
3. Lectures : `systemctl show` sur les quatre unités publisher et sur `crypto-advisor`, `crypto-operator-api`, `crypto-operator-web` ; `GET http://127.0.0.1:8090/healthz` ; validateurs de contrat de la release déployée `1728b3ad952b87d903ccb7442579000da292b848` exécutés en tant que `mathieu` avec un environnement vide ; `journalctl -u <service>` en lecture.

**3. Exécution**
Par l'opérateur `mathieu` sous sudo, avec le bloc ci-dessus préalablement téléchargé et vérifié par empreinte (`G3_MODE=plan G3_PUB=<publisher>` d'abord, sans sudo ; puis `G3_MODE=run` sous sudo). Le shell privilégié recopie le script dans `/run` (root 0700), recalcule son empreinte sur cette copie et refuse de s'exécuter s'il n'est pas root-owned/protégé. Aucun agent n'exécute sudo, `plan` privilégié ni `run`. Toute modification du bloc, du script ou d'une unité annule l'exception.

**4. Explicitement exclu**
`systemctl enable`, `disable`, `stop`, `restart`, `reload`, `daemon-reload`, `link`, `mask`, `edit` (aucun n'apparaît dans le script, testé : seuls `show` et `start` du service sélectionné) ; tout démarrage ou activation d'un **timer** ; le publisher `events` ; le drop-in et le redémarrage de l'API (G4) ; les timers et l'observation prolongée (G5) ; Advisor, API et web : aucun redémarrage ni modification ; le checkout gelé, l'epoch, la config, `PB_MAX_POSITIONS`, PPL/FIN, stratégie, signaux, risk, sizing ; toute collecte, tout stress PAPER, TESTNET, LIVE, écriture exchange, Watchdog ; lecture d'`EnvironmentFile` ou de `.env` ; toute modification d'une unité, de droits ou de sandbox. **G4 et G5 restent exclus** et demandent chacune une exception et une autorisation propres.

**5. Conditions avant exécution** (le script les contrôle et s'arrête sans rien lancer sinon)
Advisor, API, web et les quatre unités publisher avec `NeedDaemonReload=no` ; empreintes, propriétaire et mode des quatre unités conformes ; services et timers `inactive`, timers `disabled`, aucun lien d'activation ; dossier de présentation `mathieu 700` ; validateurs de la release importables ; `healthz` 200 ; au moins 10 Mio libres. Si l'une diffère, ne pas exécuter et me prévenir.

**6. Arrêt au premier écart**
Après chaque lancement : `start` rc 0, `Result=success`, `ExecMainStatus=0`, service `inactive` ; artefact fichier ordinaire, `mathieu` 0600, taille 1 octet à 1 Mio, **rafraîchi par ce lancement**, contrat valide, aucun autre fichier dans le dossier de présentation ; timers toujours `inactive`/`disabled` ; Advisor/API/web strictement inchangés (état, PID, NRestarts, InvocationID, heure de démarrage, drop-ins) ; `healthz` 200. Au premier écart la série s'arrête ; **rien n'est réessayé, réparé ni nettoyé** et la sortie complète m'est transmise. Un blocage de sandbox ne se corrige jamais par un retrait global de restrictions : toute levée est une proposition séparée, pour une unité et une directive, avec preuve (voir le tableau de diagnostic du plan G3).

**7. Expiration et consommation**
Valable jusqu'au *[à fixer par Mathieu, proposition : 3 h après la décision]*. Chaque publisher consomme son usage dès le lancement de `G3_MODE=run` (réussi, échoué, interrompu ou annulé) ; une nouvelle tentative exige une nouvelle exception.

**8. Retour arrière — conditions et limites**
- G3 ne modifie aucune configuration durable : il laisse seulement les artefacts, des entrées de journal et un état d'exécution d'unité. Il n'y a pas de retour arrière automatique.
- Un service qui échoue reste en état `failed` jusqu'à un `reset-failed`, **non autorisé ici** (inoffensif : il n'est tiré par rien).
- Retrait des artefacts, si je le demande : suppression manuelle des deux fichiers nommés ci-dessus par `mathieu` (je fournirai la commande exacte). Le `rollback` G2 laisse un dossier non vide en place par conception ; les unités G2 restent inactives et il refuse si elles étaient actives/activées.
- Interruption (Ctrl-C, perte du terminal) : le oneshot déjà lancé se termine seul (`TimeoutStartSec=20s`) ; le script affiche l'état à vérifier et ne défait rien.
- Limites : les tests prouvent la logique avec un faux `systemctl`, pas le comportement réel du sandbox ni de `systemctl show` sous `PrivateNetwork` (c'est précisément ce que G3 exerce pour la première fois) ; les durées sous charge restent inconnues ; le journal n'est pas une preuve contre root.

**9. Portée de la preuve**
Ces essais ne prouvent ni la cadence sous timer (G5), ni l'état des vues Système, ni le raccordement de l'API (G4). Ils ne certifient pas le runtime. La sortie de chaque `run` sera consignée sur #286 après coup.

Signé : *[Mathieu (3a7i3), commentaire GitHub sur #286]*

---

# Blocs prêts à exécuter (non exécutés)
À utiliser **uniquement après** publication de l'exception ci-dessus. Le fichier est téléchargé par URL épinglée au commit (fournie dans la réponse au fil, car un commit ne peut pas contenir sa propre empreinte), vérifié par SHA-256, puis seulement exécuté. Remplacer `<PUB>` par `runtime-service`, puis (si tout est réussi) par `storage`.

**a. Téléchargement + `plan` (sans sudo, lecture seule ; écrit dans `~/g3-staging/` et deux dossiers temporaires de `/tmp`)**
```sh
(
D="$HOME/g3-staging"; F="$D/g3_paste_block.sh"
H=af9470511fbc5f4dea71f7adc7840bd3ca10557adf651470cd3962a65e9378a8
U=<URL épinglée au commit>
mkdir -p -m 700 "$D" && rm -f "$F.part" &&
curl -fsS --proto '=https' --tlsv1.2 -m 60 -o "$F.part" "$U" &&
echo "$H  $F.part" | sha256sum -c - &&
mv -f "$F.part" "$F" && chmod 600 "$F" &&
G3_MODE=plan G3_PUB=<PUB> sh "$F"
echo "transfer+plan exit status: $?"
)
```

**b. `run` (sudo ; trois lancements du service sélectionné)**
```sh
(
F="$HOME/g3-staging/g3_paste_block.sh"
H=af9470511fbc5f4dea71f7adc7840bd3ca10557adf651470cd3962a65e9378a8
echo "$H  $F" | sha256sum -c - &&
sudo -l &&
printf 'G3 ONESHOT <PUB> (exception #286 G3). Tapez RUN pour lancer: ' &&
read -r A && [ "$A" = RUN ] &&
G3_MODE=run G3_PUB=<PUB> sh "$F"
echo "g3 run chain exit status: $?"
)
```
- Chaîne en `&&` : empreinte ≠ → arrêt ; pas de sudo → arrêt ; autre réponse que `RUN` → arrêt, rien n'est lancé.
- Après un échec : ne rien relancer, me montrer la sortie complète.
- Le script affiche `RESULT: OK (all checks passed)` et `trials passed: 3/3` seulement si tout est vrai.
