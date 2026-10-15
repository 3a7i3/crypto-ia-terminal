# LAB-01 — commandes opérateur

Aucune de ces commandes n'a été exécutée par un agent. Les blocs 1 à 4 ne sont valables
qu'**après** une autorisation distincte et écrite par bloc (exception #286, comme G2).

## Bloc 0 — relevé complémentaire en lecture seule (utilisateur `mathieu`, sans modification)
Complète l'audit ; aucun secret imprimé (les lignes `Environment*` sont filtrées).
```bash
date -u +%FT%TZ; id
sysctl user.max_user_namespaces kernel.unprivileged_userns_clone 2>&1
ss -ltnp 2>/dev/null | awk '{print $1,$4,$6}' | head -30
systemctl cat crypto-advisor.service | grep -vi -E '^(Environment|EnvironmentFile|PassEnvironment)' | head -40
journalctl -k --since "-14 days" --no-pager 2>/dev/null | grep -ci 'out of memory\|oom-kill'
df -i /; vmstat 5 3
sudo -n nft list ruleset 2>&1 | head -30
```
(`sudo -n` échouera si un mot de passe est requis : c'est une réponse acceptable, notez-la.)

## Bloc 1 — construire et vérifier le paquet (sans droits spéciaux)
Dans un clone temporaire de la branche de la PR (le checkout gelé n'est pas touché) :
```bash
git clone --depth 1 --branch claude/project-thread-c2x3i9 https://github.com/3a7i3/crypto-ia-terminal.git /tmp/lab01-src
cd /tmp/lab01-src && python3.11 -m pytest -q tests/lab01   # si pytest est disponible ; sinon passer
python3.11 -m lab01.ops.make_bundle /tmp/lab01-bundle      # imprime le SHA-256
python3.11 -m lab01 verify                                  # reproductibilité, sans réseau
```
Comparer le SHA-256 imprimé à celui publié dans la PR/issue. Différent = ne pas continuer.

## Bloc 2 — plan puis installation (sudo, après autorisation)
```bash
cd /tmp/lab01-src
bash lab01/ops/lab01_ops.sh plan                            # n'écrit rien
export LAB01_AUTH="<identifiant de l'autorisation>" LAB01_BUNDLE=/tmp/lab01-bundle/lab01-bundle.tar.gz LAB01_BUNDLE_SHA256=<sha publié>
sudo -E bash lab01/ops/lab01_ops.sh apply                   # utilisateur, dossiers, unités ; rien activé/démarré
sudo sh -c 'umask 037; head -c 32 /dev/urandom | base64 > /srv/lab01/token; chown root:lab01 /srv/lab01/token'
bash lab01/ops/lab01_ops.sh verify
```

## Bloc 3 — tests de refus puis exécution
```bash
systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp   # avant
sudo bash lab01/ops/lab01_host_tests.sh                     # attendu : exit 0
sudo systemctl start lab01-run.service && journalctl -u lab01-run.service --no-pager | tail -8
sudo systemctl start lab01-api.service
curl -s -H "Authorization: Bearer $(sudo cat /srv/lab01/token)" http://127.0.0.1:18090/lab/experiments | head -c 700
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18090/lab/experiments   # attendu : 401
systemctl show lab01.slice -p MemoryCurrent -p MemoryMax -p CPUQuotaPerSecUSec
systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp   # après : identique
```

## Bloc 4 — arrêt et retrait
```bash
sudo systemctl stop lab01-api.service
sudo -E bash lab01/ops/lab01_ops.sh remove            # unités retirées, données conservées
sudo -E bash lab01/ops/lab01_ops.sh remove --purge    # + /srv/lab01 et utilisateur
bash lab01/ops/lab01_ops.sh verify                    # attendu : utilisateur et unités absents
```
Exposition de l'interface : l'API écoute **127.0.0.1:18090 seulement**. Toute exposition
distante (tunnel SSH, `tailscale serve`) est un changement réseau à autoriser séparément.
