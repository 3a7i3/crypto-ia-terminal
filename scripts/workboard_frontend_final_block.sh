#!/bin/bash
# Bloc final frontend 8ff089b (v5) -- a lancer depuis le terminal operateur (mathieu) :
#   sudo bash /root/workboard-8ff089b/final_block.sh prepare    (defaut : copie root + empreintes + releve, N'ACTIVE RIEN)
#   sudo bash /root/workboard-8ff089b/final_block.sh activate   (apres go ecrit ET exception #286 postee : ACTIVE le frontend, web seul)
#   sudo bash /root/workboard-8ff089b/final_block.sh rollback   (retire uniquement le 99-workboard2.conf cree par une tentative enregistree, relance web seul)
# Aucune phase ne touche Advisor, API, current, 90-ux-fr.conf, 99-workboard.conf (activation precedente) ni les releases existantes.
# Convention : [OBLIGATOIRE] = un echec est COMPTE (FAILS, journal, failures.log) et arrete ou fait echouer la phase ;
# [AFFICHAGE] = information seule, jamais utilisee pour decider. Un "|| true" n'apparait que sur un AFFICHAGE ou pour capturer
# une valeur qui est ensuite testee.
# Provenance : avant de lancer le helper, le script ecrit dans le staging root un journal (activation-journal.env) et le contenu
# attendu (dropin-expected.conf). Le rollback ne supprime 99-workboard2.conf que si ce journal l'etablit (voir dropin_is_ours).
# v5 par rapport a v4 : gardes NeedDaemonReload (trois unites, avant et apres chaque daemon-reload), drop-in ecrit de facon
# atomique par le helper (complet ou absent), verification du rollback (WorkingDirectory, HTTP, index servi = index de la release
# precedente, drop-in precedent inchange, NeedDaemonReload=no), chaque echec compte, et preuves conservees si la restauration
# est incomplete (dossier incomplete-restore-*, marqueur INCOMPLETE_RESTORE qui bloque toute nouvelle activation).
set -euo pipefail
umask 077

SRC=/home/chatgpt-ro/workboard-8ff089b
STG=/root/workboard-8ff089b
EVD="$STG/evidence"
JOURNAL="$EVD/activation-journal.env"
EXPECTED="$EVD/dropin-expected.conf"
FAILLOG="$EVD/failures.log"
INCOMPLETE_MARK="$EVD/INCOMPLETE_RESTORE"
ARCH=workboard-frontend-8ff089b.tar.gz
HELPER=activate_workboard_frontend.py
ARCH_SHA=a9a17e8b0a994ccf7aed90c187ec90ce8fedcbaad527db37cb1a052a3f683136
HELPER_SHA=f9bda7dde3f2690cbf3d379cad6e48c0ecd23d525da1845bcf738d8fae7b744d
NEW_SHA=8ff089b26cd15190e8be34c11b75b0b17c471ef6
OLD_SHA=bdca77f9bcf306c17846985faef870844fdd1334
OPS=/opt/crypto-ai-terminal/operator
DROPDIR=/etc/systemd/system/crypto-operator-web.service.d
DROPIN="$DROPDIR/99-workboard2.conf"
DROPTMP="$DROPDIR/.99-workboard2.conf.tmp"
PREV_DROPIN="$DROPDIR/99-workboard.conf"
RELEASE_DIR="$OPS/releases/$NEW_SHA"
SERVER_REL=frontend/scripts/web01_local_frontend_server.mjs
OLD_WD="$OPS/releases/$OLD_SHA/frontend"
NEW_WD="$OPS/releases/$NEW_SHA/frontend"
WEB=crypto-operator-web.service
UNITS="$WEB crypto-advisor.service crypto-operator-api.service"
BASE=http://127.0.0.1:8181
PHASE="${1:-prepare}"
FAILS=0
RESTORE_FAILS=0
IN_RESTORE=0
ACTIVATING=0
POST_HELPER=0
RESTORE_REFUSED=0

ok()   { echo "  [OK]     $*"; }
fail() {  # [OBLIGATOIRE] compte l'echec (global, restauration si IN_RESTORE) et l'ecrit dans failures.log
  FAILS=$((FAILS+1)); [ "$IN_RESTORE" = 1 ] && RESTORE_FAILS=$((RESTORE_FAILS+1))
  echo "  [ECHEC]  $*"
  { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) phase=$PHASE n=$FAILS restauration=$RESTORE_FAILS : $*"; } >> "$FAILLOG" 2>/dev/null || true
}

[ "$(id -u)" = 0 ] || { echo "root requis (sudo)"; exit 2; }
install -d -m 0700 -o root -g root "$STG" "$EVD"
# Verrou : herite par le helper. Si le script parent est tue (SIGKILL) mais que le helper tourne encore, le verrou reste pris
# et toute autre execution (dont le rollback) est refusee tant que le helper n'est pas termine.
exec 9>"$STG/lock"
flock -n 9 || { echo "une autre execution (ou un helper orphelin) est en cours : verrou $STG/lock occupe, arret"; exit 11; }

snapshot() {  # [AFFICHAGE + preuve] $1 = etiquette ; releve complet dans $EVD/$1.txt
  {
    date -u; hostname
    systemctl show $UNITS --property=Id,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp,NeedDaemonReload
    systemctl show $WEB --property=FragmentPath,WorkingDirectory,DropInPaths
    echo "current -> $(readlink "$OPS/current")"
    ls -la --time-style=full-iso "$DROPDIR/"
    sha256sum "$DROPDIR"/*.conf*
    ls -1 "$OPS/releases/"
  } > "$EVD/$1.txt" 2>&1
  cat "$EVD/$1.txt"
}

protected() {  # etat qui ne doit PAS changer (Advisor, API, current, 90-ux-fr.conf et sauvegardes, 99-workboard.conf, releases existantes)
  systemctl show crypto-advisor.service crypto-operator-api.service \
    --property=Id,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp
  echo "current -> $(readlink "$OPS/current")"
  sha256sum "$DROPDIR"/90-ux-fr.conf* "$PREV_DROPIN"
  ls -1 "$OPS/releases/" | grep -v "^$NEW_SHA\$"
}

verify_copies() {  # [OBLIGATOIRE]
  echo "$ARCH_SHA  $STG/$ARCH" | sha256sum -c -
  echo "$HELPER_SHA  $STG/$HELPER" | sha256sum -c -
  [ "$(stat -c '%U:%a' "$STG/$ARCH" "$STG/$HELPER" | sort -u)" = "root:600" ] || { echo "proprietaire/droits inattendus"; exit 3; }
}

run_helper() {  # $@ = options supplementaires du helper ; umask 022 OBLIGATOIRE (sinon releases en 0700 root, illisibles par mathieu)
  ( umask 022; exec python3 -I -B "$STG/$HELPER" --archive "$STG/$ARCH" --sha256 "$ARCH_SHA" "$@" )
}

http_code() {  # affiche le code HTTP, 000 si la connexion echoue ; la valeur est ensuite testee par l'appelant
  curl -s -o /dev/null -m 10 -w '%{http_code}' "$1" || true
}

wait_http_200() {  # [OBLIGATOIRE] jusqu'a 20 s
  local i c
  for i in $(seq 1 20); do
    c=$(http_code "$BASE/direction/travaux")
    [ "$c" = 200 ] && return 0
    sleep 1
  done
  return 1
}

web_wd() { systemctl show "$WEB" --property=WorkingDirectory --value; }

need_reload() {  # [AFFICHAGE d'une valeur ensuite TESTEE] NeedDaemonReload d'une unite ; vide ou illisible => "ILLISIBLE"
  local v
  v=$(systemctl show "$1" --property=NeedDaemonReload --value 2>/dev/null || true)
  echo "${v:-ILLISIBLE}"
}

reload_clean() {  # [OBLIGATOIRE] $1 = contexte. daemon-reload est global : les TROIS unites doivent etre a "no" (tout autre
                  # valeur, y compris vide, est un echec compte) pour ne jamais appliquer le changement d'unite de quelqu'un d'autre.
  local u v bad=0
  for u in $UNITS; do
    v=$(need_reload "$u")
    if [ "$v" = no ]; then ok "NeedDaemonReload=no sur $u ($1)"; else fail "NeedDaemonReload=$v sur $u ($1)"; bad=1; fi
  done
  return "$bad"
}

check_protected_unchanged() {  # [OBLIGATOIRE] $1 = fichier avant, $2 = fichier apres
  if diff "$1" "$2"; then ok "Advisor / API / current / 90-ux-fr.conf / 99-workboard.conf / releases existantes : INCHANGES"
  else fail "difference sur l'etat protege (voir diff ci-dessus)"; fi
}

# ---- provenance de 99-workboard2.conf -------------------------------------------------------------------------------
jget() { [ -f "$JOURNAL" ] || return 0; grep -m1 "^$1=" "$JOURNAL" | cut -d= -f2- || true; }
PRIOR_FAILS=$(jget FAIL_COUNT); PRIOR_FAILS=${PRIOR_FAILS:-0}

write_expected() {  # contenu EXACT que le helper ecrit (verifie apres coup contre le fichier reel)
  printf '[Service]\nWorkingDirectory=%s/frontend\nExecStart=\nExecStart=/usr/bin/env node %s/%s\n' \
    "$RELEASE_DIR" "$RELEASE_DIR" "$SERVER_REL" > "$EXPECTED"
}

journal_write() {  # $1 = etat : STARTED | HELPER_DONE | ACTIVE_VERIFIED | VERIFY_FAILED | RECOVERED | ROLLED_BACK | RESTORE_INCOMPLETE
  [ -f "$EXPECTED" ] || return 0
  local tmp="$JOURNAL.tmp.$$" t0 inode prev
  t0="${T0:-$(jget T0_EPOCH)}"; inode="${DROPIN_INODE-$(jget DROPIN_INODE)}"; prev="${PREV_SHA:-$(jget PREV_DROPIN_SHA256)}"
  {
    echo "STATE=$1"
    echo "T0_EPOCH=$t0"
    echo "DROPIN_INODE=$inode"
    echo "PREV_DROPIN_SHA256=$prev"
    echo "EXPECTED_SHA256=$(sha256sum < "$EXPECTED" | cut -d' ' -f1)"
    echo "NEW_SHA=$NEW_SHA"
    echo "ARCH_SHA=$ARCH_SHA"
    echo "HELPER_SHA=$HELPER_SHA"
    echo "FAIL_COUNT=$((PRIOR_FAILS+FAILS))"
    echo "RESTORE_FAIL_COUNT=$RESTORE_FAILS"
    echo "WRITTEN_BY_PID=$$"
    echo "UPDATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$tmp"
  mv -f -- "$tmp" "$JOURNAL"
}

attempt_recorded() {  # 0 = le journal decrit une tentative en cours, active ou a restaurer
  case "$(jget STATE)" in STARTED|HELPER_DONE|ACTIVE_VERIFIED|VERIFY_FAILED|RESTORE_INCOMPLETE) return 0;; *) return 1;; esac
}

dropin_is_ours() {  # 0 = fichier cree par une tentative enregistree ; 1 = refus (motif sur stdout)
  # Le helper v5 ecrit le drop-in de facon atomique : le fichier est COMPLET ou absent. Un contenu partiel est donc
  # etranger a une tentative et est refuse (aucune tolerance de prefixe).
  local st t0 inode ct bt
  if [ ! -f "$JOURNAL" ] || [ ! -f "$EXPECTED" ]; then echo "aucun journal de provenance dans $EVD"; return 1; fi
  st=$(jget STATE); t0=$(jget T0_EPOCH); inode=$(jget DROPIN_INODE)
  if ! attempt_recorded; then echo "journal en etat '$st' : aucune tentative d'activation en cours ou active"; return 1; fi
  if [ "$(sha256sum < "$EXPECTED" | cut -d' ' -f1)" != "$(jget EXPECTED_SHA256)" ]; then echo "contenu attendu altere depuis le journal"; return 1; fi
  if [ ! -f "$DROPIN" ] || [ -L "$DROPIN" ]; then echo "99-workboard2.conf n'est pas un fichier regulier"; return 1; fi
  if ! cmp -s "$DROPIN" "$EXPECTED"; then echo "contenu different de ce que la tentative a ecrit (fichier partiel, remplace ou preexistant)"; return 1; fi
  if [ -n "$inode" ] && [ "$(stat -c %i "$DROPIN")" != "$inode" ]; then echo "inode different de celui enregistre apres le helper (fichier remplace)"; return 1; fi
  ct=$(stat -c %Z "$DROPIN")
  if [ "$ct" -lt "$t0" ]; then echo "fichier plus ancien que le debut de la tentative (ctime $ct < $t0)"; return 1; fi
  bt=$(stat -c %W "$DROPIN")
  if [ "$bt" != 0 ] && [ "$bt" -lt "$t0" ]; then echo "fichier cree avant le debut de la tentative (birth $bt < $t0)"; return 1; fi
  echo "etat $st ; contenu = contenu complet ecrit par la tentative ; ctime $ct >= debut $t0"
  return 0
}

tmp_is_ours() {  # 0 = fichier temporaire laisse par le helper d'une tentative enregistree (jamais charge par systemd : pas de .conf)
  local t0 size esize
  attempt_recorded && [ -f "$EXPECTED" ] || { echo "aucune tentative enregistree"; return 1; }
  if [ ! -f "$DROPTMP" ] || [ -L "$DROPTMP" ]; then echo "temporaire non regulier"; return 1; fi
  t0=$(jget T0_EPOCH); size=$(stat -c %s "$DROPTMP"); esize=$(stat -c %s "$EXPECTED")
  if [ "$size" -eq 0 ] || [ "$size" -gt "$esize" ] || ! cmp -s -n "$size" "$DROPTMP" "$EXPECTED"; then echo "temporaire vide ou different du contenu ecrit par la tentative"; return 1; fi
  if [ "$(stat -c %Z "$DROPTMP")" -lt "$t0" ]; then echo "temporaire plus ancien que la tentative"; return 1; fi
  return 0
}

served_index_sha() { curl -s -m 10 "$BASE/direction/travaux" | sha256sum | cut -d' ' -f1 || true; }
old_index_sha() { sha256sum < "$OLD_WD/dist/index.html" 2>/dev/null | cut -d' ' -f1 || true; }

verify_restored() {  # [OBLIGATOIRE] etat attendu apres retour arriere ; chaque ecart est COMPTE, aucun n'arrete les autres
  local want got pv
  if [ "$(web_wd)" = "$OLD_WD" ]; then ok "WorkingDirectory = $OLD_SHA"; else fail "WorkingDirectory = $(web_wd) (attendu $OLD_SHA)"; fi
  if wait_http_200; then ok "HTTP 200 sur /direction/travaux"; else fail "pas de HTTP 200 sur /direction/travaux"; fi
  want=$(old_index_sha); got=$(served_index_sha)
  if [ -n "$want" ] && [ "$want" = "$got" ]; then ok "index servi = index de la release $OLD_SHA ($want)"; else fail "index servi ($got) different de celui de la release $OLD_SHA ($want)"; fi
  if [ "$(systemctl is-active "$WEB" || true)" = active ]; then ok "$WEB actif"; else fail "$WEB non actif"; fi
  if [ -e "$DROPIN" ] || [ -L "$DROPIN" ]; then fail "99-workboard2.conf toujours present"; else ok "99-workboard2.conf absent"; fi
  if [ -e "$DROPTMP" ] || [ -L "$DROPTMP" ]; then fail "fichier temporaire du drop-in toujours present"; else ok "aucun fichier temporaire de drop-in"; fi
  pv=$(jget PREV_DROPIN_SHA256)
  if [ -f "$PREV_DROPIN" ] && [ -n "$pv" ] && [ "$(sha256sum < "$PREV_DROPIN" | cut -d' ' -f1)" = "$pv" ]; then
    ok "99-workboard.conf (activation precedente) present et inchange"
  elif [ -f "$PREV_DROPIN" ] && [ ! -f "$JOURNAL" ]; then
    echo "  [AFFICHAGE] 99-workboard.conf present ; aucune empreinte enregistree (aucune tentative n'a ete journalisee)"
  else fail "99-workboard.conf absent, different de l'empreinte enregistree, ou empreinte absente du journal"; fi
  reload_clean "apres retour arriere" || true
}

restore_previous() {  # retire 99-workboard2.conf SEULEMENT si la provenance est etablie ; renvoie 0 si tout est verifie
  local changed=0 loaded_new=0 restarted=0 why
  RESTORE_REFUSED=0; IN_RESTORE=1; RESTORE_FAILS=0
  if [ -e "$DROPTMP" ] || [ -L "$DROPTMP" ]; then
    if why=$(tmp_is_ours); then
      if rm -f -- "$DROPTMP"; then echo "   fichier temporaire du helper retire"; changed=1; else fail "suppression du fichier temporaire"; fi
    else echo "   [REFUS] fichier temporaire NON supprime : $why"; RESTORE_REFUSED=1; fail "fichier temporaire non reconnu : $why"; fi
  fi
  if [ -e "$DROPIN" ] || [ -L "$DROPIN" ]; then
    if why=$(dropin_is_ours); then
      echo "   provenance etablie : $why"
      if rm -f -- "$DROPIN"; then echo "   99-workboard2.conf retire"; changed=1; else fail "suppression de 99-workboard2.conf"; fi
    else
      echo "   [REFUS] 99-workboard2.conf NON supprime : $why"; RESTORE_REFUSED=1; fail "99-workboard2.conf non reconnu : $why"
    fi
  fi
  if [ "$RESTORE_REFUSED" = 0 ]; then
    [ "$(web_wd)" != "$OLD_WD" ] && loaded_new=1
    # Aucun daemon-reload si rien n'a ete retire ni charge (il est global). S'il faut recharger, Advisor et API doivent etre a
    # "no" : un changement d'unite en attente chez eux n'est pas le notre et ne doit pas etre applique par nous.
    if [ "$changed" = 1 ] || [ "$loaded_new" = 1 ]; then
      if [ "$(need_reload crypto-advisor.service)" = no ] && [ "$(need_reload crypto-operator-api.service)" = no ]; then
        echo "   daemon-reload (web charge sur $(web_wd), fichier retire : $changed)"
        systemctl daemon-reload || fail "daemon-reload"
        if [ "$loaded_new" = 1 ]; then
          echo "   restart de $WEB seul (la configuration chargee pointait la nouvelle release)"
          systemctl restart "$WEB" || fail "restart web"
          restarted=1
        fi
      else
        fail "daemon-reload NON lance : rechargement en attente sur Advisor ou API (changement d'unite etranger, non applique)"
      fi
    fi
    # La propriete WorkingDirectory decrit la configuration CHARGEE, pas le processus qui tourne : apres un restart qui a
    # echoue lors d'une tentative precedente, le processus peut encore servir la nouvelle release. On le constate sur ce
    # qui est SERVI, et on ne relance le web (seul) qu'une fois par execution.
    if [ "$restarted" = 0 ] && [ "$(served_index_sha)" != "$(old_index_sha)" ]; then
      echo "   l'index servi n'est pas celui de $OLD_SHA : restart de $WEB seul"
      systemctl restart "$WEB" || fail "restart web (index servi different)"
    fi
    verify_restored
  fi
  IN_RESTORE=0
  [ "$RESTORE_FAILS" = 0 ]
}

preserve_evidence() {  # [PREUVES] restauration incomplete : copie de tout ce qui l'explique, rien n'est supprime ni modifie.
  local d="$EVD/incomplete-restore-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  install -d -m 0700 -o root -g root "$d" || { echo "   [ECHEC] impossible de creer $d"; return 0; }
  {
    date -u; hostname; echo "phase=$PHASE echecs=$FAILS dont_restauration=$RESTORE_FAILS"
    systemctl show $UNITS --property=Id,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp,NeedDaemonReload
    systemctl show "$WEB" --property=FragmentPath,WorkingDirectory,DropInPaths
    echo "current -> $(readlink "$OPS/current")"
    ls -la --time-style=full-iso "$DROPDIR/" "$OPS/releases/"
    sha256sum "$DROPDIR"/*.conf* "$DROPDIR"/.99-workboard2.conf.tmp
  } > "$d/state.txt" 2>&1 || true
  # Copies (cp -p) : le fichier original reste en place ; ce sont les preuves, pas une sauvegarde de restauration.
  cp -p -- "$DROPIN" "$d/99-workboard2.conf.found" 2>/dev/null || true
  cp -p -- "$DROPTMP" "$d/dropin-tmp.found" 2>/dev/null || true
  cp -p -- "$PREV_DROPIN" "$d/99-workboard.conf.found" 2>/dev/null || true
  for f in "$EVD"/*; do   # tous les fichiers du dossier de preuves (hors sous-dossiers), y compris ceux d'une tentative precedente
    [ -f "$f" ] && cp -p -- "$f" "$d/" 2>/dev/null || true
  done
  systemctl status "$WEB" --no-pager -n 50 > "$d/status-web.txt" 2>&1 || true
  journalctl -u "$WEB" -n 200 --no-pager > "$d/journal-web.txt" 2>&1 || true
  ( cd "$d" && sha256sum -- * > SHA256SUMS 2>/dev/null ) || true
  printf '%s\n' "$d" > "$INCOMPLETE_MARK"
  journal_write RESTORE_INCOMPLETE || true
  echo "   PREUVES CONSERVEES : $d (rien n'a ete supprime). Marqueur $INCOMPLETE_MARK : toute nouvelle activation est refusee tant qu'il existe."
}

recover() {  # trap EXIT : ne fait quelque chose que si l'activation a ete interrompue ou a echoue
  local rc=$? hf
  trap - EXIT; trap '' INT TERM HUP   # un second signal ne doit pas interrompre la restauration ni la conservation des preuves
  if [ "$POST_HELPER" = 1 ] && [ "$rc" != 0 ] && [ "$rc" != 9 ]; then
    {
      fail "sortie inattendue (code $rc) apres l'activation : etat active NON annule"
      journal_write VERIFY_FAILED
      echo "!! Sortie inattendue (code $rc) apres l'activation : le frontend est actif et n'a pas ete entierement verifie. Echecs comptes : $FAILS. Decider : sudo bash $STG/final_block.sh rollback"
    } > "$EVD/recover.log" 2>&1 || true
    cat "$EVD/recover.log" 2>/dev/null || true
  fi
  if [ "$ACTIVATING" = 1 ]; then
    # Sortie ecrite d'abord dans un fichier : un terminal perdu (SIGHUP, EIO) ne doit pas interrompre la recuperation.
    {
      echo "!! Activation interrompue ou en echec (code $rc) : recuperation limitee au fichier dont la provenance est etablie"
      fail "activation interrompue ou en echec (code $rc)"
      [ -s "$EVD/helper-activate.err" ] && { echo "   rapport/erreur du helper :"; sed 's/^/   | /' "$EVD/helper-activate.err"; }
      hf=$(grep -o '"failure_count": [0-9]*' "$EVD/helper-activate.err" 2>/dev/null | tail -1 | grep -o '[0-9]*$' || true)
      if [ "${hf:-0}" -gt 0 ]; then
        echo "   [AFFICHAGE] l'etat reel est verifie ci-dessous par le bloc, qui decide de la suite"
        fail "le helper declare ${hf} echec(s) de restauration (voir helper-activate.err)"
      fi
      if restore_previous; then
        journal_write RECOVERED
        echo "   RECUPERATION OK. La release $NEW_SHA eventuelle est conservee pour analyse. Echecs comptes : $FAILS (restauration : $RESTORE_FAILS)."
      else
        echo "   RECUPERATION INCOMPLETE : echecs comptes $FAILS (restauration : $RESTORE_FAILS). Lancer la phase rollback et envoyer $EVD"
        preserve_evidence
        rc=7
      fi
    } > "$EVD/recover.log" 2>&1 || true
    cat "$EVD/recover.log" 2>/dev/null || true   # [AFFICHAGE] best effort : le terminal peut ne plus exister
    [ "$rc" = 0 ] && rc=1
  fi
  exit "$rc"
}

verify_served_assets() {  # [OBLIGATOIRE] hash de chaque asset servi, via le manifeste de la release installee
  python3 -I -B - "$OPS/releases/$NEW_SHA/manifest.json" "$BASE" <<'PY'
import hashlib, json, sys, urllib.request
manifest = json.load(open(sys.argv[1])); base = sys.argv[2]; bad = 0; seen = 0
for name, want in sorted(manifest["files"].items()):
    if not name.startswith("frontend/dist/"):
        continue
    url = base + "/" + name.removeprefix("frontend/dist/"); seen += 1
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            status = response.status; got = hashlib.sha256(response.read()).hexdigest()
    except Exception as exc:
        print("  [ECHEC]  ", url, exc); bad += 1; continue
    if status != 200 or got != want:
        print("  [ECHEC]  ", url, status, got, "attendu", want); bad += 1
    else:
        print("  [OK]     ", url, got[:12])
if seen == 0:
    print("  [ECHEC]   aucun asset dans le manifeste"); bad += 1
sys.exit(1 if bad else 0)
PY
}

has_text() {  # [OBLIGATOIRE] $1 = url, $2 = motif fixe, $3 = description
  local n
  n=$(curl -s -m 10 "$1" | grep -cF -- "$2" || true)
  if [ "${n:-0}" -ge 1 ]; then ok "$3"; else fail "$3 : ABSENT"; fi
}

verify_activation() {  # [OBLIGATOIRE] tout echec incremente FAILS
  local c js css st
  if cmp -s "$DROPIN" "$EXPECTED"; then ok "99-workboard2.conf identique au contenu attendu (journal de provenance coherent)"; else fail "99-workboard2.conf different du contenu attendu"; fi
  c=$(http_code "$BASE/direction/travaux")
  if [ "$c" = 200 ]; then ok "HTTP $c sur /direction/travaux"; else fail "HTTP $c sur /direction/travaux"; fi
  if [ "$(web_wd)" = "$NEW_WD" ]; then ok "WorkingDirectory web = release $NEW_SHA"; else fail "WorkingDirectory web = $(web_wd)"; fi
  st=$(systemctl is-active "$WEB" || true)
  if [ "$st" = active ]; then ok "$WEB actif"; else fail "$WEB : $st"; fi
  reload_clean "apres activation" || true
  if verify_served_assets; then ok "tous les assets servis ont le hash du manifeste"; else fail "asset servi absent ou different du manifeste"; fi
  js=$(curl -s -m 10 "$BASE/direction/travaux" | grep -o 'assets/index-[A-Za-z0-9_-]*\.js' | head -1 || true)   # [AFFICHAGE] nom, teste ensuite
  css=$(curl -s -m 10 "$BASE/direction/travaux" | grep -o 'assets/index-[A-Za-z0-9_-]*\.css' | head -1 || true)
  echo "  [AFFICHAGE] js=$js css=$css"
  if [ -n "$js" ] && [ -n "$css" ]; then ok "assets js et css references par la page"; else fail "js ou css non references par la page"; fi
  has_text "$BASE/$js" 'Tableau des travaux' "texte 'Tableau des travaux' dans le js servi"
  has_text "$BASE/$js" 'GATEWAY-LAB' "entree GATEWAY-LAB dans le js servi"
  has_text "$BASE/$js" 'GITHUB-SYNC' "entree GITHUB-SYNC (registre de 32 missions) dans le js servi"
  has_text "$BASE/$js" 'PUBLISHERS' "entree PUBLISHERS dans le js servi"
  has_text "$BASE/$js" 'Actualiser depuis GitHub' "bouton 'Actualiser depuis GitHub' dans le js servi"
  has_text "$BASE/$css" 'f3f7fc' "couleur de fond #f3f7fc dans le css servi"
  has_text "$BASE/$css" '18324f' "couleur de texte #18324f dans le css servi"
}

case "$PHASE" in
prepare)
  echo "== 1. Copie dans le staging root ($STG) =="
  install -m 0600 -o root -g root -- "$SRC/$ARCH" "$STG/$ARCH"
  install -m 0600 -o root -g root -- "$SRC/$HELPER" "$STG/$HELPER"
  echo "== 2. [OBLIGATOIRE] Empreintes recalculees SUR LES COPIES ROOT =="
  verify_copies
  echo "== 3. Releve frais =="
  snapshot before
  protected > "$EVD/protected-before.txt"
  echo "== 3b. [OBLIGATOIRE] NeedDaemonReload=no sur les trois unites (un daemon-reload ne doit appliquer le changement de personne) =="
  reload_clean "prepare" || { echo "NeedDaemonReload non nul : arret, rien modifie (traiter ce changement d'unite separement)"; exit 4; }
  echo "== 4. [OBLIGATOIRE] Inspection seule du helper (aucune mutation) =="
  run_helper | tee "$EVD/helper-inspect.json"
  grep -q '"disposition": "INSPECT_ONLY_NO_MUTATION"' "$EVD/helper-inspect.json" || { echo "inspection non conforme"; exit 4; }
  echo "PRET. Rien n'est active. Pour activer, apres go ecrit : sudo bash $STG/final_block.sh activate"
  ;;
activate)
  [ -f "$STG/$ARCH" ] && [ -f "$STG/$HELPER" ] || { echo "lancer d'abord la phase prepare"; exit 4; }
  echo "== [OBLIGATOIRE] Reverification des empreintes des copies root =="
  verify_copies
  echo "== [OBLIGATOIRE] Preconditions =="
  if [ -e "$INCOMPLETE_MARK" ]; then echo "restauration incomplete precedente ($(cat "$INCOMPLETE_MARK" 2>/dev/null)) : arret, rien modifie. Examiner les preuves, puis lancer la phase rollback : le marqueur n est retire qu apres un rollback entierement verifie."; exit 8; fi
  if [ -e "$DROPIN" ] || [ -L "$DROPIN" ]; then echo "99-workboard2.conf existe deja : arret, rien modifie"; exit 8; fi
  if [ -e "$DROPTMP" ] || [ -L "$DROPTMP" ]; then echo "fichier temporaire de drop-in existe deja : arret, rien modifie"; exit 8; fi
  if [ -e "$RELEASE_DIR" ]; then echo "release $NEW_SHA deja presente : arret, rien modifie"; exit 8; fi
  if [ "$(web_wd)" != "$OLD_WD" ]; then echo "le web n'est pas sur $OLD_SHA ($(web_wd)) : arret, rien modifie"; exit 8; fi
  if [ ! -f "$PREV_DROPIN" ] || [ -L "$PREV_DROPIN" ]; then echo "99-workboard.conf (activation precedente) absent ou non regulier : arret, rien modifie"; exit 8; fi
  reload_clean "avant activation" || { echo "NeedDaemonReload non nul : arret, rien modifie (un daemon-reload appliquerait un changement d'unite etranger)"; exit 8; }
  ok "99-workboard2.conf et temporaire absents, release absente, web sur $OLD_SHA, 99-workboard.conf present, aucun rechargement en attente"
  snapshot before-activate
  protected > "$EVD/protected-before-activate.txt"
  read -r -p "Go ecrit de Mathieu et exception #286 postee ? Tape ACTIVER pour continuer : " ans
  [ "$ans" = "ACTIVER" ] || { echo "abandon, rien modifie"; exit 5; }
  # Provenance AVANT toute mutation : contenu attendu + journal dans le staging root.
  write_expected
  T0=$(date +%s); DROPIN_INODE=""; PREV_SHA=$(sha256sum < "$PREV_DROPIN" | cut -d' ' -f1)
  journal_write STARTED
  trap recover EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  ACTIVATING=1
  echo "== Activation frontend (web seul) =="
  for f in helper-activate.err helper-activate.json; do [ -f "$EVD/$f" ] && mv -f -- "$EVD/$f" "$EVD/$f.prev-$T0" || true; done   # ne pas ecraser les preuves d'une tentative precedente
  : > "$EVD/helper-activate.err"
  run_helper --activate 2> "$EVD/helper-activate.err" | tee "$EVD/helper-activate.json"
  [ -s "$EVD/helper-activate.err" ] && { echo "  [AFFICHAGE] stderr du helper :"; sed 's/^/   | /' "$EVD/helper-activate.err"; }
  DROPIN_INODE=$(stat -c %i "$DROPIN")
  journal_write HELPER_DONE
  ACTIVATING=0; POST_HELPER=1
  echo "code retour helper : 0"
  snapshot after
  protected > "$EVD/protected-after.txt"
  echo "== [OBLIGATOIRE] Verifications apres activation =="
  check_protected_unchanged "$EVD/protected-before-activate.txt" "$EVD/protected-after.txt"
  verify_activation
  if [ "$FAILS" != 0 ]; then
    journal_write VERIFY_FAILED
    POST_HELPER=0
    echo "VERIFICATION OBLIGATOIRE ECHOUEE ($FAILS echec(s) comptes, voir $FAILLOG). Rien n'a ete annule automatiquement. Decider : sudo bash $STG/final_block.sh rollback"
    exit 9
  fi
  journal_write ACTIVE_VERIFIED
  POST_HELPER=0
  echo "ACTIVE ET VERIFIE (source / serveur local). Preuve navigateur (page tailnet, 32 lignes, filtres, mobile, un relevé GitHub) a faire separement. Staging et preuves conserves dans $STG."
  ;;
rollback)
  if [ ! -e "$DROPIN" ] && [ ! -L "$DROPIN" ] && [ ! -e "$DROPTMP" ] && [ ! -L "$DROPTMP" ] && ! attempt_recorded; then
    echo "99-workboard2.conf absent : rien a retirer. Verification de l'etat servi :"
    IN_RESTORE=1; verify_restored; IN_RESTORE=0
    if [ "$FAILS" != 0 ]; then echo "ETAT NON CONFORME ($FAILS echec(s) comptes)"; preserve_evidence; exit 7; fi
    echo "ETAT CONFORME : web sur $OLD_SHA, rien a retirer."
    exit 0
  fi
  trap '' INT TERM HUP
  snapshot pre-rollback
  protected > "$EVD/protected-pre-rollback.txt"
  echo "== Rollback (provenance verifiee avant toute suppression) =="
  rb=0; restore_previous || rb=$?
  if [ "$RESTORE_REFUSED" = 1 ]; then
    echo "ROLLBACK REFUSE : provenance non etablie, fichier laisse en place (a examiner a la main). Echecs comptes : $FAILS. Preuves : $EVD"
    preserve_evidence
    exit 6
  fi
  snapshot post-rollback
  protected > "$EVD/protected-post-rollback.txt"
  check_protected_unchanged "$EVD/protected-pre-rollback.txt" "$EVD/protected-post-rollback.txt"
  if [ "$rb" != 0 ] || [ "$FAILS" != 0 ]; then
    echo "ROLLBACK INCOMPLET ($FAILS echec(s) comptes dont $RESTORE_FAILS pendant la restauration)"
    preserve_evidence
    exit 7
  fi
  journal_write ROLLED_BACK
  rm -f -- "$INCOMPLETE_MARK"   # seulement apres un rollback entierement verifie
  echo "ROLLBACK OK : web sur $OLD_SHA, tout verifie (0 echec)"
  ;;
*) echo "phase inconnue : prepare | activate | rollback"; exit 1 ;;
esac
