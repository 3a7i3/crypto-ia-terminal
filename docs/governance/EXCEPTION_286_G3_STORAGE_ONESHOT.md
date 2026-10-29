# Texte proposé pour #286 — exception G3 `storage` (essais ponctuels) — NON PUBLIÉ
Statut : **brouillon préparé pour revue. Ni publié, ni exécuté.** À poster par Mathieu (3a7i3) ou publié par Claude sur son instruction explicite. La fenêtre proposée précédemment (jusqu'au 2026-10-16 à 23:59 UTC) n'a jamais été publiée sur #286 et est caduque : aucune autorisation `storage` n'existe à ce jour. Ce dossier est **distinct** de tout dossier d'activation frontend (candidat main `8ff089b26cd15190e8be34c11b75b0b17c471ef6`) : deux dossiers, deux autorisations ; la fusion source de #458 n'autorise aucune activation, et cette exception n'autorise rien côté frontend. Ce texte ne rétroagit sur rien : l'exception G3 `runtime-service` n'a pas de publication préalable établie sur #286 (voir [résultats du run](../runbooks/PASSIVE_PUBLISHERS_G3_RUN_RUNTIME_SERVICE_RESULTS.md)) et son usage est consommé. G4 et G5 attendent la réussite de `storage`.

---

**EXCEPTION GOV-286-PUBLISHERS-G3-STORAGE-ONESHOT — un seul usage**

Date de décision : *[à renseigner par Mathieu]* (UTC) — Autorisant : Mathieu (3a7i3)

`ACTIVE_BURN_IN_IMMUTABILITY_GUARD` reste actif. J'autorise, pour ces seules opérations, les lancements ponctuels de systemd strictement décrits ci-dessous, et rien d'autre.

**0. Version du script**
Version corrigée par la PR #452, commit complet `e1e4df9d9b116f380936e61a10a16753e4897452` (main ; le brouillon d'exception lui-même est dans le commit `da258220e5898a24f264b08ff717afc673ac0743`, #456, et cette mise à jour dans le commit de sa propre PR). Elle remplace, pour cette exception seulement, le script du commit `589d3ea1bb4123e7a61f3420a1c3af9a4055bb4a` utilisé le 2026-10-15 pour `runtime-service` (bloc `9810f2412d09717da86474c65248fb1d19ddd700d56ed5d8355964d17cccdfa4`, script `4a125f6e17d973999ec37df6bec830013116c079ecfd3e4dc1ba88ebcb513e39`). Différences : (a) le texte « never run since boot/reload » devient « no start recorded in the property observed at this moment; this property alone does not prove the full history » ; (b) la durée n'est calculée que si l'horodatage de démarrage est > 0, sinon elle reste NOT_AVAILABLE (plus de « 0ms » issu de deux zéros). Aucune autre ligne du script ne change (7 lignes dans le bloc généré, unités et empreintes d'unités identiques, 38 tests G3 verts). **Limite** : cette correction n'invente pas de mesure ; durée et compteurs (`MemoryPeak`, `CPUUsageNSec`) peuvent rester NOT_AVAILABLE et ne sont pas des preuves.

**1. Empreintes imposées (toutes doivent correspondre, sinon l'exception ne s'applique pas)**
- Bloc `g3_paste_block.sh` : SHA-256 `3d03794cc3328664510073bae125792a4cf307ae5791e7c923627a164c7e335d` (14488 octets).
- Script G3 interne : SHA-256 `19abde8d0bdde248a6ab9d4c5c023869482194488b745a73a376b542c28b55b9` (13611 octets).
- Unités déjà installées par G2 (aucune modification) : `crypto-publish-runtime-service.service` `0ef373c474b380a03944d08a00c4b3666e8c0a3269039a9b2d704545dca0b1ad` ; `crypto-publish-runtime-service.timer` `d1c779f0d9ebe3c9315e1b1ea0e9ef6695e9e1278d8d37755222c0023b3e53bd` ; `crypto-publish-storage.service` `72149a4174344f226063c4a714b690cddbc21a0e9dd91f2921a62271b6b0d4a1` ; `crypto-publish-storage.timer` `afeacf3ea6687980a7c19b012e1c6cc0b7be791d023a487be604e30bf68e18f4`.

**2. Périmètre autorisé (et seulement celui-ci)**
Pour le seul publisher **`storage`** (la série `runtime-service` a été exécutée le 2026-10-15 à 19:47Z ; son usage est consommé et n'est pas rouvert) :
1. **Au plus trois** `systemctl start crypto-publish-storage.service` (le service oneshot, jamais le timer), espacés d'au moins 5 s, l'un après l'autre. Le plafond de 3 est codé en dur dans le script (`RUNS=3`) ; la série s'arrête au premier écart, donc 1 à 3 lancements ; **aucun lancement supplémentaire, aucune reprise**. Une surcharge de ce plafond n'existe qu'en mode test (`G3_TEST=1`, variables `G3_RUNS`, `G3_GAP`, `G3_UNITDIR`, `G3_OUTDIR`, `G3_OWNER`, `G3_SRC`, `G3_PYBIN`, `G3_HEALTH`) : l'exception ne s'applique pas si une variable `G3_*` est présente dans l'environnement (le bloc `run` ci-dessous le vérifie avant tout). 
2. Effets attendus : écriture atomique de l'artefact du publisher dans `/home/mathieu/operator_presentation/` (`storage_snapshot.json`, `mathieu` 0600) ; entrées de journal ; état d'exécution d'unité (Result, horodatages, compteurs) ; `storage` ne lit que les métadonnées de `decision_packets_*.jsonl` sans les ouvrir.
3. Lectures : `systemctl show` sur les quatre unités publisher et sur `crypto-advisor`, `crypto-operator-api`, `crypto-operator-web` ; `GET http://127.0.0.1:8090/healthz` ; validateurs de contrat de la release déployée `1728b3ad952b87d903ccb7442579000da292b848` exécutés en tant que `mathieu` avec un environnement vide ; `journalctl -u <service>` en lecture.

**3. Exécution et mécanisme sudo**
- `plan` : exécuté par `mathieu` **sans sudo** (lecture seule ; il copie le script dans un dossier temporaire de l'utilisateur, vérifie son empreinte, l'exécute puis supprime la copie).
- `run` : l'opérateur `mathieu` lance le bloc `g3_paste_block.sh` en `sh` **sous son propre compte** ; le bloc exécute **un seul** `sudo sh -c …` qui (1) crée un dossier `/run/g3priv.XXXXXX` (root, `umask 077`), (2) y copie le script lu sur son entrée standard, (3) recalcule le SHA-256 de cette copie et refuse de continuer s'il diffère de `19abde8d0bdde248a6ab9d4c5c023869482194488b745a73a376b542c28b55b9`, (4) exécute la copie protégée en root, (5) supprime le dossier. Les seuls verbes `systemctl` de cette copie sont `show` et `start crypto-publish-storage.service` (3 fois au plus). Elle lit aussi des métadonnées (`stat`, listage du dossier de présentation, `healthz`), crée un dossier temporaire `/tmp/g3.XXXXXX` supprimé à la fin, et lance les validateurs de contrat via `runuser -u mathieu` avec un environnement vide (privilèges abandonnés). Elle n'écrit rien d'autre que ce que le service démarré écrit lui-même (artefact et journal).
- `sudo -l` dans le bloc `run` ne sert qu'à **afficher** les droits existants avant la confirmation `RUN` ; il n'élève rien. Cette exception **s'appuie sur les droits sudo déjà en place** (rapportés par l'opérateur le 2026-10-15) ; elle n'en crée, n'en élargit et n'en modifie aucun, et ne modifie aucun fichier sudoers.
- Aucun agent n'exécute sudo, `plan` privilégié ni `run`. Toute modification du bloc, du script ou d'une unité annule l'exception.

**4. Explicitement exclu**
`systemctl enable`, `disable`, `stop`, `restart`, `reload`, `daemon-reload`, `link`, `mask`, `edit` (aucun n'apparaît dans le script, testé : seuls `show` et `start` du service sélectionné) ; tout démarrage ou activation d'un **timer** ; le publisher `events` ; le drop-in et le redémarrage de l'API (G4) ; les timers et l'observation prolongée (G5) ; Advisor, API et web : aucun redémarrage ni modification ; le checkout gelé, l'epoch, la config, `PB_MAX_POSITIONS`, PPL/FIN, stratégie, signaux, risk, sizing ; toute collecte, tout stress PAPER, TESTNET, LIVE, écriture exchange, Watchdog ; lecture d'`EnvironmentFile` ou de `.env` ; toute modification d'une unité, de droits ou de sandbox. **G4 et G5 restent exclus** et demandent chacune une exception et une autorisation propres.

**5. Conditions avant exécution** (le script les contrôle et s'arrête sans rien lancer sinon)
Advisor, API, web et les quatre unités publisher avec `NeedDaemonReload=no` ; empreintes, propriétaire et mode des quatre unités conformes ; services et timers `inactive`, timers `disabled`, aucun lien d'activation ; dossier de présentation `mathieu 700` ; validateurs de la release importables ; `healthz` 200 ; au moins 10 Mio libres. Si l'une diffère, ne pas exécuter et me prévenir.

**6. Arrêt au premier écart**
Après chaque lancement : `start` rc 0, `Result=success`, `ExecMainStatus=0`, service `inactive` ; artefact fichier ordinaire, `mathieu` 0600, taille 1 octet à 1 Mio, **issu de ce lancement** (inode/mtime changés depuis avant le lancement **et** `generated_at_utc`, `observed_at_utc` et mtime situés dans la fenêtre [heure avant `start` − 0,5 s ; heure après `start` + 0,5 s], vérifiés par le script lui-même) ; contrat valide selon les validateurs de la release déployée (un résultat faux, une exception ou un fichier illisible donne un code de sortie non nul : 1 = invalide ou pas de ce lancement, 2 = erreur) ; timers toujours `inactive`/`disabled` ; Advisor/API/web strictement inchangés (état, PID, NRestarts, InvocationID, heure de démarrage, drop-ins) ; `healthz` 200. **Dossier de présentation** : seuls `runtime_service_snapshot.json` et `storage_snapshot.json` y sont admis ; tout autre fichier est refusé ; le dossier n'a pas à être vide et rien n'y est supprimé. L'artefact de l'**autre** publisher, s'il existe (`runtime_service_snapshot.json`, 878 octets, issu du run du 2026-10-15 19:47Z, doit être préservé), est autorisé mais doit rester strictement inchangé (inode, taille, mtime et SHA-256) ; s'il est absent, il doit le rester. Au premier écart la série s'arrête ; **rien n'est réessayé, réparé ni nettoyé** et la sortie complète m'est transmise. Un blocage de sandbox ne se corrige jamais par un retrait global de restrictions : toute levée est une proposition séparée, pour une unité et une directive, avec preuve (voir le tableau de diagnostic du plan G3).

**7. Expiration et consommation**
Fenêtre de validité : du **[début, UTC, à fixer par Mathieu]** au **[fin, UTC, à fixer par Mathieu]** (expiration ferme ; aucune valeur par défaut n'est proposée ici, la fenêtre est laissée à la décision de Mathieu). L'usage est consommé dès le lancement de `G3_MODE=run` (réussi, échoué, interrompu ou annulé) ; une nouvelle tentative exige une nouvelle exception. Le `plan` frais doit avoir été exécuté **dans la fenêtre**, après la publication de l'exception, et lu avant le `run`.

**8. Mesures** : durée et consommation ne sont pas retenues comme preuves (cf. run `runtime-service` : `duration=0ms`, compteurs NOT_AVAILABLE) ; NOT_AVAILABLE reste NOT_AVAILABLE, jamais 0.

**9. Retour arrière — limites** : identiques à l'exception précédente (aucune configuration durable modifiée ; pas de `reset-failed` ni de nettoyage autorisés ; retrait de `storage_snapshot.json` seulement sur ma demande, commande fournie alors).

**10. Portée de la preuve** : ni cadence sous timer (G5), ni raccordement de l'API (G4), ni vues Système ; pas de certification du runtime. La sortie sera consignée sur #286 après coup.

Signé : *[Mathieu (3a7i3), commentaire GitHub sur #286]*

---

# Blocs prêts à exécuter (non exécutés), publisher `storage`
**a. Téléchargement + `plan` frais (sans sudo, lecture seule)**
```sh
(
D="$HOME/g3-staging"; F="$D/g3_paste_block.sh"
H=3d03794cc3328664510073bae125792a4cf307ae5791e7c923627a164c7e335d
U=https://raw.githubusercontent.com/3a7i3/crypto-ia-terminal/e1e4df9d9b116f380936e61a10a16753e4897452/deploy/passive_publishers/g3_paste_block.sh
mkdir -p -m 700 "$D" && rm -f "$F.part" &&
curl -fsS --proto '=https' --tlsv1.2 -m 60 -o "$F.part" "$U" &&
echo "$H  $F.part" | sha256sum -c - &&
mv -f "$F.part" "$F" && chmod 600 "$F" &&
G3_MODE=plan G3_PUB=storage sh "$F"
echo "transfer+plan exit status: $?"
)
```

**b. `run` (sudo, trois lancements au plus, arrêt au premier écart) — après autorisation explicite et plan frais `RESULT: OK`**
```sh
(
F="$HOME/g3-staging/g3_paste_block.sh"
H=3d03794cc3328664510073bae125792a4cf307ae5791e7c923627a164c7e335d
echo "$H  $F" | sha256sum -c - &&
! env | grep -q '^G3_' &&
sudo -l &&
printf 'G3 ONESHOT storage (exception #286 G3 storage). Tapez RUN pour lancer: ' &&
read -r A && [ "$A" = RUN ] &&
G3_MODE=run G3_PUB=storage sh "$F"
echo "g3 run chain exit status: $?"
)
```
Le script compare Advisor/API/web avant et après (état, PID, NRestarts, InvocationID, démarrage, drop-ins), exige les timers `inactive`/`disabled`, et refuse si `runtime_service_snapshot.json` change (inode, taille, mtime, SHA-256). `! env | grep -q '^G3_'` échoue (et donc arrête la chaîne) si une variable `G3_*` est définie. Après un échec : ne rien relancer, transmettre la sortie complète.
