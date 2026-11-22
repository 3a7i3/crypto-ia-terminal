# Procédure d'installation pilote — Repository Cartographer (préparée, NON exécutée)

Statut : **à relire, non exécutée**. Chaque étape demande l'autorisation explicite de Mathieu ; les
commandes `sudo` sont exécutées par lui. Configuration justifiée dans
[`CARTOGRAPHER_INSTALL_REVIEW.md`](CARTOGRAPHER_INSTALL_REVIEW.md) (constats VPS du 2026-11-22).
Aucun timer, aucune campagne ; le registre reste `NOT_WIRED`. Un contrôle en échec → étape 8.

Notations : `S=<SHA_RETENU>` (HEAD de #599 contenant ce document) ; `API_OLD=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4` ;
`API_NEW=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c1ecc3b4` ;
`WEB_NEW=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-${S:0:8}` ; `CK=/srv/cat-obs/checkout/$S`.
`URL=http://127.0.0.1:8090/api/operator/v1/agent-invocations/repository-cartographer`.

## 1. Préconditions et SHA (lecture seule)

```
mkdir -p ~/cat-obs-pilot && cd ~/cat-obs-pilot              # traces locales, jamais publiées
systemctl show crypto-operator-api -p MainPID -p WorkingDirectory > api.before   # attendu : API_OLD
systemctl show crypto-operator-web -p MainPID -p BindReadOnlyPaths > web.before   # attendu : dist 597
readlink /run/cat/current > paper.before                    # session PAPER à préserver
routes() { (cd "$1" && env -i HOME=/nonexistent $API_OLD/.venv/bin/python -B -c 'from observability.operator_api.app import app;print("\n".join(sorted(r.path for r in app.routes if r.path.startswith("/api"))))'); }
routes $API_OLD > routes.before        # /openapi.json est désactivé (openapi_url=None) : liste tirée du code servi
for p in $(cat routes.before | grep -v "{"); do echo "$p $(curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8090$p)"; done > codes.before
git -C $API_OLD rev-parse HEAD; git -C $API_OLD status --porcelain | wc -l   # 85376c5e… ; 0
```

Clone de travail (sous `lecanada26`, hors service) et contrôles obligatoires :

```
git clone https://github.com/3a7i3/crypto-ia-terminal ~/cat-obs-pilot/src && cd ~/cat-obs-pilot/src
git checkout --detach $S && git rev-parse HEAD                          # = S
git diff --stat 57b4ee005fa4e1ec34edb9bc73747949b2d602e9 $S -- . ':!docs/agents/observation'   # vide
git cat-file -e 857404f8ebfbcf9df4a3f36052ab5357ea9b8d7b^{commit} && git cat-file -e e387318eeaed81d4e6dc90228d46943a65a5b73c^{commit}
sha256sum docs/agents/observation/pilot/api-85376c5e-agent-invocation.patch   # 6a73ea3bdb1431e70b7234a451a79b1746c1e524db4c054d82659c78417c41fc
# Tests (venv de l'API, qui a pytest) : AUCUN saut accepté pour les deux tests pilote.
$API_OLD/.venv/bin/python -m pytest -q -p no:cacheprovider tests/agent_bench -rs
# Runner sous l'interpréteur de l'hôte : exécution réelle hors service, rapports jetables.
d=$(mktemp -d) && /usr/bin/python3.10 -m agent_bench.observation.executor \
  --mission docs/agents/observation/examples/cartographer_zone_mission.json --checkout $PWD --reports $d/r \
  --runner-id obs-repo-cartographer-ro-01 --code-sha $S --analysed-sha e387318eeaed81d4e6dc90228d46943a65a5b73c
# attendu : PUBLISHED, COMPLETED, PARTIAL, content_sha256 67bdcc05ec67e54013991028275d78ff4727c299fe2f9b6762c2b3da35a3fa4e
rm -rf $d
```

Attendu : 136 passés, 1 sauté (golden historique, motif `app.py`). Les deux tests pilote **passent**.

## 2. Accès minimaux

```
sudo groupadd --system cat-obs-read                          # aucun membre
sudo install -d -o cat-obs-ro -g cat-obs-read -m 2750 /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks
sudo chgrp cat-obs-read /srv/cat-obs/reports && sudo chmod 0710 /srv/cat-obs/reports
stat -c '%a %U:%G %n' /srv/cat-obs/reports /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks
# attendu : 710 cat-obs-ro:cat-obs-read ; 2750 … ; 2750 …
```

Le compte `lecanada26` n'est pas modifié ; le groupe n'est donné qu'à l'unité API (étape 3).

## 3. Installation des composants

**Checkout runner** (immuable) :

```
sudo git clone ~/cat-obs-pilot/src $CK && sudo git -C $CK checkout --detach $S
sudo git -C $CK remote remove origin
sudo chown -R root:root $CK && sudo find $CK -type d -exec chmod 0555 {} + && sudo find $CK -type f -exec chmod 0444 {} +
sudo -u cat-obs-ro env -i PATH=/usr/bin:/bin HOME=/nonexistent GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$CK git -C $CK rev-parse HEAD   # = S
```

**Release API** (85376c5e + correctif minimal, venv réutilisé) :

```
git clone --no-hardlinks $API_OLD $API_NEW && git -C $API_NEW checkout --detach 85376c5e7725c9fa45f8d05fb0051f25a127aba4
git -C $API_NEW apply --index ~/cat-obs-pilot/src/docs/agents/observation/pilot/api-85376c5e-agent-invocation.patch
test "$(git -C $API_NEW write-tree)" = c1ecc3b436e8a9617004ca0c8f142ec9e7ff7012 && echo ARBRE_OK
chmod -R go-rwx $API_NEW
```

Drop-in API `/etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf`
(trie après `zzzzz-cat-paper-session.conf`) :

```
[Service]
WorkingDirectory=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c1ecc3b4
ExecStart=
ExecStart=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python -B -m uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --no-access-log
BindReadOnlyPaths=
BindReadOnlyPaths=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c1ecc3b4 /home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4 /home/lecanada26/crypto-install/python/cpython-3.11.17-linux-x86_64-gnu /home/lecanada26/crypto-install/presentation
SupplementaryGroups=cat-obs-read
Environment=AGENT_INVOCATION_REPORTS_PATH=/srv/cat-obs/reports
```

L'`ExecStartPre` de session PAPER reste inchangé : il s'exécute dans le nouveau répertoire de travail,
dont les modules `financial_institute`, `paper_trading`, `observability` sont ceux de `85376c5e`
(seuls 7 fichiers ajoutés/modifiés), et ne crée pas de session tant que `/run/cat/current` existe.

```
sudo systemctl daemon-reload && sudo systemctl restart crypto-operator-api
systemctl is-active crypto-operator-api; readlink /run/cat/current | diff - ~/cat-obs-pilot/paper.before && echo PAPER_INCHANGE
```

**Release frontend** (build avec drapeau, même base que la release servie) :

```
cd ~/cat-obs-pilot/src/frontend && npm ci && VITE_CARTOGRAPHER_INVOCATION=1 npm run build
(cd dist && find . -type f | sort | xargs sha256sum | sha256sum)   # attendu 2d59c533e7e3a28bb9b73ef9f3eddb19b05085e4098cf3c1121ba4e0c4a4c61a
grep -l agent-invocations dist/assets/*.js                          # 1 fichier
sudo install -d -o root -g root -m 0755 $WEB_NEW && sudo cp -a dist $WEB_NEW/ && sudo chown -R root:root $WEB_NEW
```

Si le manifeste diffère (version de node), comparer la liste des fichiers et vérifier que seuls
`index.html` et les bundles JS/CSS changent par rapport au `dist` servi ; sinon arrêter.
Drop-in web `/etc/systemd/system/crypto-operator-web.service.d/zzzzzzzzzzzzzzzzzzz-agent-invocation-599.conf` :

```
[Service]
BindReadOnlyPaths=
BindReadOnlyPaths=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-<S8>/dist:/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/dist
```

(redémarrage web à l'étape 6 seulement, après le contrôle du lecteur).

## 4. Contrôle du lecteur dans le contexte réel de l'API (N3)

```
curl -s $URL | python3 -m json.tool
```

Attendu : `connection ABSENT` (« aucune invocation consignée »), `activity INDETERMINE`, `display.light
GRAY`, `read_only true`, aucun chemin dans la réponse. `ACCESS_DENIED` ou `UNREADABLE` → étape 8.
Cible inconnue : `curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8090/api/operator/v1/agent-invocations/x` → 404.

## 5. Une invocation manuelle isolée

Lancer **une** fois la commande `systemd-run` de la revue (§4). Attendu : code 0, ligne `PUBLISHED`,
`COMPLETED`, `PARTIAL`, `content_sha256 67bdcc05…`. Puis :

```
sudo stat -c '%a %U:%G %n' /srv/cat-obs/reports/runs/* /srv/cat-obs/reports/runs/*/* /srv/cat-obs/reports/locks/*
# attendu : dossiers 2750, fichiers 640, groupe cat-obs-read
```

Option « vert réel » (au mieux, non bloquante) : dans une seconde session, `while :; do curl -s $URL | grep -o '"light": *"[A-Z]*"'; sleep 0.2; done`
pendant l'invocation. Ne jamais créer de faux verrou pour l'obtenir.

## 6. Rapport → API → application

```
curl -s $URL | python3 -m json.tool
```

Attendu : `AVAILABLE`, `TERMINE`, `last_result PARTIAL`, `display RED « Inactif · fin normale »`,
`activity_reason` contenant « aucun processus ne détient le verrou » (preuve que `/proc/locks` est lu
dans le service ; « /proc/locks illisible » → étape 8). Puis :

```
sudo systemctl daemon-reload && sudo systemctl restart crypto-operator-web
```

Sur mobile (vue Système) : carte « preuve d'invocation » rouge « Inactif · fin normale », profil du
registre gris (`NOT_WIRED`). Captures conservées localement.

## 7. Non-régression

```
routes $API_NEW > routes.after
diff routes.before routes.after      # seule ligne ajoutée : /api/operator/v1/agent-invocations/{agent_id}
for p in $(cat routes.before | grep -v "{"); do echo "$p $(curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8090$p)"; done > codes.after
diff codes.before codes.after        # aucun écart
readlink /run/cat/current | diff - paper.before && echo PAPER_INCHANGE
systemctl is-active crypto-operator-api crypto-operator-web cat-or-live-api cat-or-live-web cat-or-live-collector
```

Vues web : Accueil, Marché, Finance, Système chargées sans erreur ; aucun timer cartographe
(`systemctl list-timers | grep -i cat-obs` vide).

## 8. Retour arrière (si un contrôle échoue)

```
sudo rm /etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf
sudo rm -f /etc/systemd/system/crypto-operator-web.service.d/zzzzzzzzzzzzzzzzzzz-agent-invocation-599.conf
sudo systemctl daemon-reload && sudo systemctl restart crypto-operator-api crypto-operator-web
systemctl show crypto-operator-api -p WorkingDirectory      # = API_OLD
readlink /run/cat/current | diff - ~/cat-obs-pilot/paper.before && echo PAPER_INCHANGE
# Accès ajoutés retirés ; rapports conservés tels quels :
sudo chgrp -R cat-obs-ro /srv/cat-obs/reports && sudo chmod 0750 /srv/cat-obs/reports
sudo chmod g-s /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks
sudo groupdel cat-obs-read
```

- **Conservés** : tout `/srv/cat-obs/reports/` (enveloppes, verrou), les releases `API_NEW` et `WEB_NEW`
  (inertes, non servies), le checkout `$CK` (inerte) et `52db9887…`. Aucun `rm -rf`.
- Relancer l'étape 7 pour confirmer le retour à l'état initial.
