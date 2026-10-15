# LAB-01 — commandes opérateur

Aucune de ces commandes n'a été exécutée par un agent, sauf le bloc 0a (autorisé le 2026-10-15, compte
`chatgpt-ro`, non privilégié). Les blocs 0b et 2 à 5 ne sont valables qu'**après** une autorisation distincte
et écrite par bloc (exception #286, comme G2). Ce document ne vaut jamais autorisation.
Convention : `<SHA_COMPLET>` = commit de 40 caractères publié dans #447/#448 (jamais une branche) ;
`<H_AUDIT>`, `<H_BUNDLE>`, `<H_MANIFESTE>` = empreintes SHA-256 publiées au même endroit.
Les blocs **entièrement renseignés** (commit et empreintes) sont publiés avec chaque HEAD ; le dépôt ne peut pas
contenir l'empreinte du commit qui le contient.

## Bloc 0 — relevé complémentaire, lecture seule (`lab01/ops/lab01_audit.sh`)
Erreurs, refus et codes de retour imprimés ; sortie tronquée signalée ; erreur de journal = INDÉTERMINÉ, jamais « 0 » ;
aucun `systemctl cat`, aucun `Environment`/`ExecStart` : seules des propriétés nommées sont lues. Le code retour du
script dit seulement qu'il s'est exécuté, pas que chaque sonde a réussi.

**0a — sans privilège.** Écritures : un dossier temporaire privé unique (`mktemp -d`, 0700) contenant le clone et le
rapport ; fichiers temporaires 0600 du script, supprimés à chaque étape. Réseau : un `git fetch`. Observations du système :
lecture seule. Le bloc refuse de continuer si le commit ou l'empreinte de `lab01_audit.sh` diffère.
```bash
(
  set -uo pipefail; umask 077
  SHA=<SHA_COMPLET>; EMPREINTE=<H_AUDIT>
  W="$(mktemp -d "${TMPDIR:-/tmp}/lab01-audit.XXXXXXXX")" || exit 10
  git init -q "$W/src" && cd "$W/src" || exit 11
  git fetch -q --depth 1 https://github.com/3a7i3/crypto-ia-terminal.git "$SHA" || exit 12
  git checkout -q --detach FETCH_HEAD || exit 13
  [ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "COMMIT INATTENDU"; exit 14; }
  [ "$(sha256sum lab01/ops/lab01_audit.sh | cut -d' ' -f1)" = "$EMPREINTE" ] || { echo "EMPREINTE INATTENDUE"; exit 15; }
  bash lab01/ops/lab01_audit.sh user 2>&1 | tee "$W/audit-user.txt"
  rc=${PIPESTATUS[0]}; echo "code retour du script : $rc ; rapport : $W/audit-user.txt"; exit "$rc"
)
echo "code retour du bloc : $?"
```
**0b — privilégié, séparé** (règles réseau et propriétaires de ports) : staging **distinct** de celui de l'installateur
(`/root/lab01-audit-staging/<commit>`), un seul fichier copié (`lab01_audit.sh`), copie vérifiée côté root avant exécution ;
aucune copie d'installateur, aucun compte, montage, `mkfs`, unité ni service LAB. Ce bloc reste **non autorisé** ; sa procédure
complète figure dans le fichier publié avec le HEAD. L'inventaire du pare-feu et des propriétaires de ports ne retarde pas l'étape A.

## Bloc OOM — événements OOM sur 14 jours (`lab01/ops/lab01_oom_probe.sh`, lecture seule)
N'affiche pas le journal complet (compteur, plus ancienne entrée lisible, 20 lignes au plus). États distincts :
`ACCÈS_REFUSÉ`, `RÉTENTION_INSUFFISANTE`, `AUCUNE_CORRESPONDANCE`, `ÉVÉNEMENTS`, `ERREUR` ; dernière ligne `ÉTAT_OOM=…`.
Il imprime aussi le compteur noyau `oom_kill` depuis le démarrage (lisible sans privilège). Il ne modifie ni groupe ni droit.
Il se lance depuis un clone épinglé et vérifié (même préambule que le bloc 0a, avec l'empreinte de `lab01_oom_probe.sh`), avec un compte
autorisé par l'opérateur à lire le journal :
```bash
bash lab01/ops/lab01_oom_probe.sh 2>&1 | tee "$W/oom.txt"; echo "code retour : ${PIPESTATUS[0]} (ne dit rien du résultat : lire ÉTAT_OOM)"
```

## Bloc 1 — construire et publier les empreintes (sans droits spéciaux, commit épinglé)
Dans le clone du bloc 0a (déjà positionné sur `<SHA_COMPLET>`) :
```bash
python3.11 -m lab01 verify                          # reproductibilité des événements, sans réseau
python3.11 -m lab01.ops.make_bundle /tmp/lab01-out  # bundle_sha256, installer_manifest_sha256, commit, COMMIT, request.json
```
Comparer les valeurs imprimées à celles publiées. Différent = ne pas continuer. `request.json` est une demande candidate
(données, `not_an_authorization: true`), pas une autorisation.

## Bloc 2 — staging root protégé, puis vérification et préconditions (sudo, après autorisation)
Le code d'installation est copié dans un répertoire à root (0700) nommé d'après le commit, puis **revérifié depuis ce répertoire** :
```bash
set -eu; SHA=<SHA_COMPLET>; STAGE=/root/lab01-staging/$SHA; SRC=<clone>/lab01/ops; OUT=/tmp/lab01-out
sudo install -d -m 0700 -o root -g root "$STAGE" "$STAGE/systemd"
(cd "$SRC" && sudo install -m 0755 -o root -g root lab01_ops.sh lab01_host_tests.sh lab01_oom_probe.sh lab01_audit.sh "$STAGE/")
(cd "$SRC" && sudo install -m 0644 -o root -g root host_isolation_tests.py hostprobe.py unit_props.py "$STAGE/")
sudo install -m 0644 -o root -g root "$SRC"/systemd/* "$STAGE/systemd/"
sudo install -m 0644 -o root -g root "$OUT/INSTALLER.sha256" "$OUT/COMMIT" "$OUT/lab01-bundle.tar.gz" "$STAGE/"
sudo bash "$STAGE/lab01_ops.sh" verify-staging --commit "$SHA" --manifest-sha256 <H_MANIFESTE>  # attendu : « staging vérifié »
sudo bash "$STAGE/lab01_ops.sh" preflight      --commit "$SHA" --manifest-sha256 <H_MANIFESTE>  # lecture seule : PASS / FAIL / INDÉTERMINÉ
```
`preflight` ne modifie rien. Un `FAIL` arrête l'installation avant toute écriture ; un `INDÉTERMINÉ` est à lire par l'opérateur.

## Bloc 3 — plan puis installation (sudo, après autorisation ; l'environnement de l'appelant n'est pas transmis)
```bash
sudo bash "$STAGE/lab01_ops.sh" plan                      # n'écrit rien
sudo bash "$STAGE/lab01_ops.sh" apply --auth "<identifiant de l'autorisation>" --commit "$SHA" \
     --bundle "$STAGE/lab01-bundle.tar.gz" --bundle-sha256 <H_BUNDLE> --manifest-sha256 <H_MANIFESTE>
sudo sh -c 'umask 027; head -c 32 /dev/urandom | base64 > /srv/lab01/token; chown root:lab01 /srv/lab01/token; chmod 0640 /srv/lab01/token'
sudo bash "$STAGE/lab01_ops.sh" verify
```
`apply` rejoue les préconditions, puis exécute sept étapes (utilisateur, dossiers, image, unités, montage, données, release), chacune atomique
et reprenable, journalisées dans `/var/lib/lab01/install.journal`. Rien n'est activé ni démarré hormis le montage du volume.

**Échec partiel** : l'état reste inerte. Relever l'état réel puis choisir :
```bash
sudo bash "$STAGE/lab01_ops.sh" status                    # FAIT / PARTIEL / ABSENT par étape + dernières lignes du journal
sudo bash "$STAGE/lab01_ops.sh" apply … (mêmes arguments)  # reprise : les étapes faites sont constatées, les autres reprises
sudo bash "$STAGE/lab01_ops.sh" remove --auth "<id>"      # ou retrait qui conserve les preuves (bloc 5)
```

## Bloc 4 — isolation effective, exécution, export, API
```bash
systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp   # avant
sudo bash "$STAGE/lab01_host_tests.sh" 2>&1 | tee /tmp/lab01-isolation.txt; echo "code : ${PIPESTATUS[0]}"
#   0 tout OK · 1 au moins un KO · 4 INDÉTERMINÉ sans KO · 5 abandon (LAB non installé / contrôle d'exécution) · 3 pas root
sudo bash "$STAGE/lab01_host_tests.sh" --functional                        # (autorisation à part) vraies commandes sous le bac à sable
```
Les `KO` et `INDÉTERMINÉ` sont à rapporter tels quels ; aucun n'est une réussite. Les services LAB ne se lancent qu'ensuite et à la main :
```bash
sudo systemctl start lab01-run.service && sudo systemctl start lab01-export.service
journalctl -u lab01-run.service -u lab01-export.service --no-pager | tail -12
sudo systemctl start lab01-api.service
# Jeton : jamais dans les arguments d'un processus. Il est écrit dans un fichier d'en-tête 0600 lu par curl (-H @fichier).
H="$(mktemp)"; chmod 600 "$H"
sudo sh -c 'printf "Authorization: Bearer "; cat /srv/lab01/token' > "$H"
curl -s -H @"$H" -o /tmp/lab01-list.json -w 'http=%{http_code}\n' http://127.0.0.1:18090/lab/experiments
wc -c /tmp/lab01-list.json; head -c 700 /tmp/lab01-list.json; echo " [affichage limité à 700 octets]"
shred -u "$H"
curl -s -o /dev/null -w 'sans jeton : http=%{http_code} (attendu 401)\n' http://127.0.0.1:18090/lab/experiments
systemctl show lab01.slice -p MemoryCurrent -p MemoryMax -p CPUQuotaPerSecUSec -p TasksCurrent
df -h /srv/lab01/data
systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp   # après : identique
```
Contrôle côté observateur (connecteur, compte `chatgpt-ro`, lecture seule) : `cat /srv/lab01/data/reports/EXPORT.json` doit réussir ;
`ls /srv/lab01/data/runs` et `cat /srv/lab01/token` doivent être **refusés**.

## Bloc 5 — arrêt et retrait (conserve les preuves et les expériences)
```bash
sudo systemctl stop lab01-api.service
sudo bash "$STAGE/lab01_ops.sh" remove --auth "<identifiant de l'autorisation>"
sudo bash "$STAGE/lab01_ops.sh" verify          # unités absentes, volume démonté
```
`remove` écrit d'abord `/var/lib/lab01/evidence/<horodatage>/` (archive des expériences et rapports, unités, journal, état, empreinte de l'image)
avec un `MANIFEST.sha256` **vérifié** ; si cela échoue, **rien n'est retiré** (code 7). Puis : arrêts, démontage, unités retirées.
Conservés : l'image `/var/lib/lab01/lab01.img`, les preuves, le journal, `/srv/lab01`, l'utilisateur `lab01`. Pas de purge : `--purge` est
refusé par le script ; une suppression des données est une décision séparée.

Exposition de l'interface : l'API écoute **127.0.0.1:18090 seulement** et refuse de démarrer sans jeton valide.
Toute exposition distante (tunnel SSH, `tailscale serve`) est un changement réseau à autoriser séparément.
