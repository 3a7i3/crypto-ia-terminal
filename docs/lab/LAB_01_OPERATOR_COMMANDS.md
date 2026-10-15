# LAB-01 — commandes opérateur

Aucune de ces commandes n'a été exécutée par un agent. Les blocs 2 à 5 ne sont valables
qu'**après** une autorisation distincte et écrite par bloc (exception #286, comme G2).
Convention : `<SHA_COMPLET>` = le commit de 40 caractères publié dans #447/#448 (jamais une branche),
`<H_BUNDLE>` et `<H_MANIFESTE>` = les empreintes SHA-256 publiées au même endroit.

## Bloc 0 — relevé complémentaire, lecture seule (script versionné `lab01/ops/lab01_audit.sh`)
Les erreurs, refus et codes de retour sont imprimés ; une sortie tronquée le dit ; une erreur de
journal est « INDÉTERMINÉ », jamais « 0 ». Aucun `systemctl cat`, aucun `Environment`/`ExecStart` :
seules des propriétés nommées sont lues.

**0a — sans privilège** (utilisateur `mathieu`, aucune élévation) :
```bash
git clone https://github.com/3a7i3/crypto-ia-terminal.git /tmp/lab01-src && cd /tmp/lab01-src
git checkout --detach <SHA_COMPLET> && test "$(git rev-parse HEAD)" = "<SHA_COMPLET>" && echo commit-ok
bash lab01/ops/lab01_audit.sh user | tee /tmp/lab01-audit-user.txt
```
**0b — privilégié, séparé** (règles réseau et propriétaires de ports ; à lancer depuis le staging protégé du bloc 2, après `verify-staging`) :
```bash
sudo bash /root/lab01-staging/<SHA_COMPLET>/lab01_audit.sh priv | tee /tmp/lab01-audit-priv.txt
```
Si `sudo` exige un mot de passe ou refuse, la sortie l'indique (`[REFUSÉ …]`) : c'est une réponse acceptable, à coller telle quelle.

## Bloc 1 — construire et publier les empreintes (sans droits spéciaux, commit épinglé)
Dans le clone du bloc 0a (déjà positionné sur `<SHA_COMPLET>`) :
```bash
python3.11 -m lab01 verify                          # reproductibilité des événements, sans réseau
python3.11 -m lab01.ops.make_bundle /tmp/lab01-out  # bundle_sha256, installer_manifest_sha256, commit, request.json
```
Comparer les trois valeurs imprimées à celles publiées dans la PR/l'issue. Différent = ne pas continuer.
`request.json` est une demande candidate (données, `not_an_authorization: true`), pas une autorisation.

## Bloc 2 — staging root protégé, puis vérification (sudo, après autorisation)
Le code d'installation est copié dans un répertoire à root (0700) puis **revérifié depuis ce répertoire** :
```bash
set -eu; SHA=<SHA_COMPLET>; STAGE=/root/lab01-staging/$SHA; SRC=/tmp/lab01-src/lab01/ops
sudo install -d -m 0700 -o root -g root "$STAGE" "$STAGE/systemd"
sudo install -m 0755 -o root -g root "$SRC/lab01_ops.sh" "$SRC/lab01_host_tests.sh" "$SRC/lab01_audit.sh" "$STAGE/"
sudo install -m 0644 -o root -g root "$SRC"/systemd/* "$STAGE/systemd/"
sudo install -m 0644 -o root -g root /tmp/lab01-out/INSTALLER.sha256 /tmp/lab01-out/lab01-bundle.tar.gz "$STAGE/"
sudo bash "$STAGE/lab01_ops.sh" verify-staging --manifest-sha256 <H_MANIFESTE>   # attendu : « staging vérifié »
```
## Bloc 3 — plan puis installation (sudo, après autorisation ; l'environnement de l'appelant n'est pas transmis, aucun paramètre par variable)
```bash
sudo bash "$STAGE/lab01_ops.sh" plan                      # n'écrit rien
sudo bash "$STAGE/lab01_ops.sh" apply --auth "<identifiant de l'autorisation>" \
     --bundle "$STAGE/lab01-bundle.tar.gz" --bundle-sha256 <H_BUNDLE> --manifest-sha256 <H_MANIFESTE>
sudo sh -c 'umask 027; head -c 32 /dev/urandom | base64 > /srv/lab01/token; chown root:lab01 /srv/lab01/token; chmod 0640 /srv/lab01/token'
sudo bash "$STAGE/lab01_ops.sh" verify
```
`apply` crée l'utilisateur `lab01`, l'image de 64 Mo, **monte** ce volume, installe les unités ; rien d'autre n'est démarré. Si le montage échoue il s'interrompt : aucun stockage non borné n'est créé.

## Bloc 4 — tests de refus, exécution, export, API
```bash
systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp   # avant
sudo bash "$STAGE/lab01_host_tests.sh"                                     # attendu : exit 0
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

## Bloc 5 — arrêt et retrait (conserve les expériences et preuves)
```bash
sudo systemctl stop lab01-api.service
sudo bash "$STAGE/lab01_ops.sh" remove --auth "<identifiant de l'autorisation>"
sudo bash "$STAGE/lab01_ops.sh" verify                  # unités absentes, volume démonté ; /var/lib/lab01/lab01.img conservé
```
Pas de purge dans le parcours normal : `--purge` est refusé par le script. Une suppression des données est une décision séparée.

Exposition de l'interface : l'API écoute **127.0.0.1:18090 seulement** et refuse de démarrer sans jeton valide.
Toute exposition distante (tunnel SSH, `tailscale serve`) est un changement réseau à autoriser séparément.
