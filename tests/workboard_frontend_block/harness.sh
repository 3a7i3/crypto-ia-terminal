#!/bin/bash
# Banc d'essai du bloc frontend v5. Conteneur de test (root requis), chemins ISOLES dans un dossier temporaire, faux systemctl,
# faux serveur 127.0.0.1:8181. Jamais le VPS : aucun service reel n'est lu ni modifie, aucun chemin /opt ou /etc reel n'est ecrit.
#   bash harness.sh [archive.tar.gz]      (defaut : l'archive du paquet 8ff089b)
set -u
T=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$T/../.." && pwd)
ARCHIVE="${1:-/mnt/project-files/frontend-release-8ff089b/workboard-frontend-8ff089b.tar.gz}"
[ "$(id -u)" = 0 ] || { echo "root requis (le bloc teste exige root)"; exit 2; }
export SBX; SBX=$(mktemp -d /tmp/wfb-sbx.XXXXXX); R=$SBX/root; LOGS="${LOGS_DIR:-$T/logs}"; mkdir -p "$LOGS" $SBX/{bin,state,knobs,hv} $R
O=$R/opt/crypto-ai-terminal/operator; D=$R/etc/systemd/system/crypto-operator-web.service.d; STG=$R/stg; EVD=$STG/evidence
OLD=bdca77f9bcf306c17846985faef870844fdd1334; NEW=8ff089b26cd15190e8be34c11b75b0b17c471ef6; CUR=7638475dc1a18340c252cb1ce7bfdc143297c601
OLDWD=$O/releases/$OLD/frontend
cp $T/systemctl_stub $SBX/bin/systemctl; cp $T/journalctl_stub $SBX/bin/journalctl; chmod +x $SBX/bin/*
ARCH_SHA=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
mkdir -p $SBX/ext; tar -xzf "$ARCHIVE" -C $SBX/ext
python3 $T/patch_helpers.py $REPO/scripts/activate_workboard_frontend.py $SBX/hv
PASS=0; FAILN=0
check() { if eval "$2"; then echo "   PASS  $1"; PASS=$((PASS+1)); else echo "   FAIL  $1   [$2]"; FAILN=$((FAILN+1)); fi; }
sub() {  # substitution de chemins, appliquee au bloc ET au helper : tout ce qui est ecrit va dans $R
  sed -e "s#/home/chatgpt-ro/workboard-8ff089b#$R/src#g" -e "s#/root/workboard-8ff089b#$STG#g" \
      -e "s#/opt/crypto-ai-terminal#$R/opt/crypto-ai-terminal#g" -e "s#/etc/systemd#$R/etc/systemd#g" "$1"
}
hash90() { sha256sum $D/90-ux-fr.conf* $D/99-workboard.conf | sha256sum | cut -c1-16; }
reset() {
  python3 "$T/drive.py" cleanup; sleep 0.3
  rm -rf $O/releases/$NEW $D $STG $SBX/knobs/* $SBX/systemctl.log $R/src
  mkdir -p $O/releases/$OLD/frontend/dist/assets $O/releases/$CUR $D $R/src $SBX/knobs
  echo "<html>ancienne release bdca77f</html>" > $O/releases/$OLD/frontend/dist/index.html
  ln -sfn $O/releases/$CUR $O/current
  echo "[Service]" > $D/90-ux-fr.conf; echo "# sauvegarde" > $D/90-ux-fr.conf.backup-1
  printf '[Service]\nWorkingDirectory=%s\n' "$OLDWD" > $D/99-workboard.conf   # activation precedente (rapportee)
  : > $SBX/systemctl.log; PATH=$SBX/bin:$PATH systemctl daemon-reload; PATH=$SBX/bin:$PATH systemctl restart crypto-operator-web.service
  H90=$(hash90)
}
mkscript() {  # $1 = variante de helper
  sub "${BLOCK:-$T/../../scripts/workboard_frontend_final_block.sh}" > $SBX/final_block.sh
  sub $SBX/hv/$1.py > $R/src/activate_workboard_frontend.py
  cp "$ARCHIVE" $R/src/workboard-frontend-8ff089b.tar.gz
  local hs; hs=$(sha256sum $R/src/activate_workboard_frontend.py | cut -d' ' -f1)
  sed -i "s/^HELPER_SHA=[0-9a-f]*/HELPER_SHA=$hs/" $SBX/final_block.sh
}
run() {  # $1 = nom, $2 = phase
  local name=$1; shift
  if [ "$1" = activate ]; then echo ACTIVER | PATH=$SBX/bin:$PATH bash $SBX/final_block.sh "$@" > "$LOGS/$name.log" 2>&1
  else PATH=$SBX/bin:$PATH bash $SBX/final_block.sh "$@" > "$LOGS/$name.log" 2>&1 < /dev/null; fi
  RC=$?; echo $RC > "$LOGS/$name.rc"
}
dr() {  # $1 nom, $2 marqueur, $3 action ; fixe PRC
  python3 $T/drive.py $SBX/final_block.sh "$LOGS/$1_activate.log" $2 $3 > "$LOGS/$1.drive" 2>&1; PRC=$(sed -n 's/^rc script = //p' "$LOGS/$1.drive")
}
JF=$EVD/activation-journal.env; EXPF=$EVD/dropin-expected.conf
jstate() { sed -n 's/^STATE=//p' $JF; }
nflog() { wc -l < $EVD/failures.log 2>/dev/null || echo 0; }
nosysmut() { ! grep -E "^systemctl (restart|daemon-reload)" $SBX/systemctl.log; }
noprotected() { ! grep -E "^systemctl (restart|stop|start|reload|daemon-reload|kill).*(advisor|operator-api)" $SBX/systemctl.log; }
state_ok() {  # $1 nom : etat final attendu apres retour arriere reussi
  check "$1: 99-workboard2.conf et temporaire absents" '[ ! -e $D/99-workboard2.conf ] && [ ! -e $D/.99-workboard2.conf.tmp ]'
  check "$1: 90-ux-fr.conf* et 99-workboard.conf inchanges" '[ "$(hash90)" = "$H90" ]'
  check "$1: configuration chargee ET processus sur l'ancienne release" '[ "$(cat $SBX/state/loaded_wd)" = "$OLDWD" ] && [ "$(cat $SBX/state/running_wd)" = "$OLDWD" ]'
  check "$1: current inchange" '[ "$(readlink $O/current)" = "$O/releases/$CUR" ]'
  check "$1: Advisor/API jamais cibles par une action systemctl" 'noprotected'
}
(python3 $T/sandbox_server.py & echo $! > $SBX/srv.pid); sleep 1

echo "### N0 chemin nominal : prepare, activate, rollback"; reset; mkscript orig
run N0_prepare prepare; check "prepare rc=0 et rien d'active" '[ $RC = 0 ] && [ ! -e $D/99-workboard2.conf ] && [ ! -e $O/releases/$NEW ]'
run N0_activate activate
check "activate rc=0, ACTIVE ET VERIFIE" '[ $RC = 0 ] && grep -q "ACTIVE ET VERIFIE" $LOGS/N0_activate.log'
check "aucune ligne [ECHEC], aucun failures.log" '! grep -q "\[ECHEC\]" $LOGS/N0_activate.log && [ ! -s $EVD/failures.log ]'
check "drop-in complet, unique lien, 0644, contenu attendu" 'cmp -s $D/99-workboard2.conf $EXPF && [ "$(stat -c %h:%a $D/99-workboard2.conf)" = 1:644 ]'
check "aucun fichier temporaire de drop-in" '[ ! -e $D/.99-workboard2.conf.tmp ]'
check "les trois unites a NeedDaemonReload=no apres activation" '[ "$(grep -c "NeedDaemonReload=no sur .* (apres activation)" $LOGS/N0_activate.log)" = 3 ]'
check "le web sert la NOUVELLE release (configuration et processus)" '[ "$(cat $SBX/state/loaded_wd)" = "$O/releases/$NEW/frontend" ] && [ "$(cat $SBX/state/running_wd)" = "$(cat $SBX/state/loaded_wd)" ]'
check "99-workboard.conf (activation precedente) intact, 90-ux-fr.conf* intacts" '[ "$(hash90)" = "$H90" ]'
check "journal ACTIVE_VERIFIED, FAIL_COUNT=0" '[ "$(jstate)" = ACTIVE_VERIFIED ] && grep -q "^FAIL_COUNT=0" $JF'
check "aucun marqueur INCOMPLETE_RESTORE" '[ ! -e $EVD/INCOMPLETE_RESTORE ]'
run N0_rollback rollback
check "rollback rc=0 (0 echec)" '[ $RC = 0 ] && grep -q "ROLLBACK OK : web sur .* tout verifie (0 echec)" $LOGS/N0_rollback.log'
check "rollback verifie l'index servi, NeedDaemonReload, le drop-in precedent" 'grep -q "index servi = index de la release" $LOGS/N0_rollback.log && grep -q "apres retour arriere" $LOGS/N0_rollback.log && grep -q "99-workboard.conf (activation precedente) present et inchange" $LOGS/N0_rollback.log'
state_ok N0; check "N0: release neuve conservee, journal ROLLED_BACK" '[ -d $O/releases/$NEW ] && [ "$(jstate)" = ROLLED_BACK ]'
run N0_rollback2 rollback; check "N0: second rollback : rien a retirer, etat verifie (rc 0)" '[ $RC = 0 ] && grep -q "ETAT CONFORME" $LOGS/N0_rollback2.log'

echo; echo "################ G : gardes NeedDaemonReload ################"
for u in web advisor api; do
  echo "### G1-$u rechargement en attente sur $u au prepare"; reset; mkscript orig; touch $SBX/knobs/pending_$u; run G1_$u prepare
  check "G1-$u: prepare arrete (rc 4), echec compte" '[ $RC = 4 ] && grep -q "\[ECHEC\].*NeedDaemonReload=yes sur crypto-" $LOGS/G1_$u.log'
  echo "### G2-$u rechargement en attente sur $u a l'activation (apres un prepare propre)"; rm -f $SBX/knobs/pending_$u; run G2_${u}_prep prepare; touch $SBX/knobs/pending_$u; : > $SBX/systemctl.log; run G2_$u activate
  check "G2-$u: activate refuse (rc 8), rien cree" '[ $RC = 8 ] && [ ! -e $D/99-workboard2.conf ] && [ ! -e $O/releases/$NEW ] && [ ! -e $JF ]'
  check "G2-$u: aucun daemon-reload ni restart (le changement d'autrui n'est pas applique)" 'nosysmut'
done
echo "### G3 valeur illisible (systemctl show en erreur) : traitee comme un echec, pas comme 'no'"; reset; mkscript orig; run G3_prep prepare; touch $SBX/knobs/unreadable_advisor; run G3 activate
check "G3: activate refuse (rc 8), valeur ILLISIBLE comptee" '[ $RC = 8 ] && grep -q "NeedDaemonReload=ILLISIBLE sur crypto-advisor" $LOGS/G3.log && [ ! -e $D/99-workboard2.conf ]'
echo "### G4 le rechargement du web est resté en attente apres activation (configuration non rechargee) : helper et bloc echouent, retour arriere"; reset; mkscript orig; run G4_prep prepare
# Le drapeau persistant ne peut pas etre pose avant l'activation sans declencher la garde d'entree : on le pose via le marqueur du helper.
python3 - <<PY
import re,pathlib
p=pathlib.Path("$SBX/hv/g4.py"); s=pathlib.Path("$SBX/hv/orig.py").read_text()
old='        command("systemctl", "restart", WEB)\n        last_error = None'
assert s.count(old)==1
p.write_text(s.replace(old,'        command("systemctl", "restart", WEB)\n        open("$SBX/knobs/stuck_pending_web","w").close()\n        last_error = None',1))
PY
mkscript g4; run G4_prep2 prepare; : > $SBX/systemctl.log; run G4 activate
check "G4: activation en echec (rc != 0), NEED_DAEMON_RELOAD_AFTER_ACTIVATE" '[ $RC != 0 ] && grep -q "NEED_DAEMON_RELOAD_AFTER_ACTIVATE" $LOGS/G4.log'
check "G4: restauration INCOMPLETE annoncee et comptee (le web reste 'yes' : echec compte)" 'grep -q "RECUPERATION INCOMPLETE" $LOGS/G4.log && grep -q "NeedDaemonReload=yes sur crypto-operator-web.service (apres retour arriere)" $LOGS/G4.log'
check "G4: rc 7" '[ $RC = 7 ]'
check "G4: 99-workboard2.conf retire malgre tout (fichier de la tentative)" '[ ! -e $D/99-workboard2.conf ]'
check "G4: preuves conservees : dossier incomplete-restore-* avec SHA256SUMS et copie du journal" 'ls -d $EVD/incomplete-restore-*/ >/dev/null 2>&1 && ls $EVD/incomplete-restore-*/SHA256SUMS >/dev/null 2>&1 && ls $EVD/incomplete-restore-*/activation-journal.env >/dev/null 2>&1'
check "G4: marqueur INCOMPLETE_RESTORE, journal RESTORE_INCOMPLETE" '[ -e $EVD/INCOMPLETE_RESTORE ] && [ "$(jstate)" = RESTORE_INCOMPLETE ]'
check "G4: failures.log compte chaque echec (>= 1) et le journal porte FAIL_COUNT et RESTORE_FAIL_COUNT" '[ "$(nflog)" -ge 1 ] && grep -q "^FAIL_COUNT=[1-9]" $JF && grep -q "^RESTORE_FAIL_COUNT=[1-9]" $JF'
check "G4: le journal du helper (stderr) est cite dans recover.log" 'grep -q "restore" $EVD/recover.log && grep -q "INCOMPLETE\|\"restore\"" $EVD/recover.log'
echo "### G4b nouvelle activation refusee tant que le marqueur existe"; rm -f $SBX/knobs/stuck_pending_web; run G4b_activate activate
check "G4b: activate refuse (rc 8) a cause de INCOMPLETE_RESTORE, rien modifie" '[ $RC = 8 ] && grep -q "restauration incomplete precedente" $LOGS/G4b_activate.log && [ ! -e $D/99-workboard2.conf ]'
run G4c_rollback rollback
check "G4c: apres correction, rollback verifie tout (rc 0), le marqueur est retire, les preuves restent" '[ $RC = 0 ] && [ ! -e $EVD/INCOMPLETE_RESTORE ] && ls -d $EVD/incomplete-restore-*/ >/dev/null 2>&1'
state_ok G4c

echo "### G5 un rechargement etranger apparait PENDANT l'attente du ACTIVER (apres la garde du bloc) : le helper refuse avant toute mutation, aucun daemon-reload"
reset; mkscript orig; run G5_prep prepare; : > $SBX/systemctl.log
( sleep 3; touch $SBX/knobs/pending_advisor ) & ( sleep 6; echo ACTIVER ) | PATH=$SBX/bin:$PATH bash $SBX/final_block.sh activate > $LOGS/G5.log 2>&1; RC=$?; wait
check "G5: activation refusee (NEED_DAEMON_RELOAD_PENDING cite), rc != 0" '[ $RC != 0 ] && grep -q "NEED_DAEMON_RELOAD_PENDING" $LOGS/G5.log'
check "G5: AUCUN daemon-reload ni restart (le changement d'Advisor n'est pas applique), rien cree" 'nosysmut && [ ! -e $D/99-workboard2.conf ] && [ ! -e $O/releases/$NEW ]'
check "G5: l'echec est compte (journal et failures.log)" '[ "$(nflog)" -ge 1 ] && grep -q "^FAIL_COUNT=[1-9]" $JF'
echo "### G6 un rechargement etranger (Advisor) apparait PENDANT l'activation, apres le reload du helper : la restauration ne l'applique pas, echec compte, preuves"
reset; python3 - <<PY
import pathlib
s=pathlib.Path("$SBX/hv/orig.py").read_text(); old='        command("systemctl", "restart", WEB)\n        last_error = None'
assert s.count(old)==1
pathlib.Path("$SBX/hv/g6.py").write_text(s.replace(old,'        command("systemctl", "restart", WEB)\n        open("$SBX/knobs/pending_advisor","w").close()\n        last_error = None',1))
PY
mkscript g6; run G6_prep prepare; : > $SBX/systemctl.log; run G6 activate
check "G6: echec (NEED_DAEMON_RELOAD_AFTER_ACTIVATE), un seul daemon-reload (celui de l'activation), aucun apres l'apparition du drapeau" '[ $RC != 0 ] && grep -q "NEED_DAEMON_RELOAD_AFTER_ACTIVATE" $LOGS/G6.log && [ "$(grep -c "^systemctl daemon-reload" $SBX/systemctl.log)" = 1 ]'
check "G6: restauration incomplete annoncee (reload non lance), preuves + marqueur" 'grep -q "daemon-reload NON lance" $LOGS/G6.log && grep -q "RECUPERATION INCOMPLETE" $LOGS/G6.log && [ -e $EVD/INCOMPLETE_RESTORE ] && [ $RC = 7 ]'
check "G6: le fichier de la tentative est tout de meme retire ; Advisor/API jamais cibles" '[ ! -e $D/99-workboard2.conf ] && noprotected'

echo; echo "################ A : ecriture atomique du drop-in ################"
echo "### A1 SIGKILL du groupe pendant l'ecriture (fichier temporaire ecrit, pas encore lie)"; reset; mkscript h_stall_tmp; run A1 prepare; dr A1 MARK_TMP_WRITTEN kill_group
check "A1: parent tue (rc -9)" '[ "$PRC" = -9 ]'
check "A1: le drop-in n'existe PAS (jamais de fichier partiel) ; le temporaire (non .conf) existe" '[ ! -e $D/99-workboard2.conf ] && [ -e $D/.99-workboard2.conf.tmp ]'
check "A1: systemd ne voit rien a recharger (le temporaire est ignore)" '[ "$(PATH=$SBX/bin:$PATH systemctl show crypto-operator-web.service --property=NeedDaemonReload --value)" = no ]'
run A1_rollback rollback; check "A1: rollback rc 0, temporaire retire apres provenance" '[ $RC = 0 ] && [ ! -e $D/.99-workboard2.conf.tmp ]'; state_ok A1
echo "### A2 SIGTERM au helper pendant l'ecriture : le helper meurt, le bloc retire le temporaire et recupere"; reset; mkscript h_stall_tmp; run A2 prepare; dr A2 MARK_TMP_WRITTEN term_helper
check "A2: script rc != 0, RECUPERATION OK" '[ "$PRC" != 0 ] && grep -q "RECUPERATION OK" $LOGS/A2_activate.log'; state_ok A2
echo "### A3 fichier PARTIEL au chemin du drop-in (non produit par le helper v5) : refus, preuves conservees"; reset; mkscript orig; run A3 prepare; run A3_act activate; run A3_rb rollback
printf '[Service]\nWork' > $D/99-workboard2.conf; HP=$(sha256sum $D/99-workboard2.conf | cut -c1-16); : > $SBX/systemctl.log
cp $EXPF $EXPF.bak; sed -i 's/^STATE=.*/STATE=VERIFY_FAILED/' $JF; run A3_refus rollback
check "A3: contenu partiel : refus (rc 6), fichier intact, aucun reload/restart" '[ $RC = 6 ] && [ "$(sha256sum $D/99-workboard2.conf | cut -c1-16)" = "$HP" ] && nosysmut'
check "A3: motif 'fichier partiel' et echecs comptes" 'grep -q "fichier partiel, remplace ou preexistant" $LOGS/A3_refus.log && [ "$(nflog)" -ge 1 ]'
check "A3: preuves conservees avec copie du fichier refuse" 'ls $EVD/incomplete-restore-*/99-workboard2.conf.found >/dev/null 2>&1'
rm -f $D/99-workboard2.conf $EVD/INCOMPLETE_RESTORE

echo; echo "################ R : provenance, SIGKILL du parent, signaux ################"
echo "### R1 SIGKILL du script PARENT seul apres creation du drop-in (helper orphelin vivant)"; reset; mkscript h_stall_linked; run R1 prepare; dr R1 MARK_DROPIN_CREATED kill_parent
check "R1: parent tue (rc -9), helper vivant, drop-in COMPLET" '[ "$PRC" = -9 ] && grep -q "helper vivant apres l.action = OUI" $LOGS/R1.drive && cmp -s $D/99-workboard2.conf $EXPF'
check "R1: journal STARTED, aucune recuperation automatique" '[ "$(jstate)" = STARTED ] && [ ! -e $EVD/recover.log ]'
PH=$(sha256sum $D/99-workboard2.conf | cut -c1-16); : > $SBX/systemctl.log; run R1_rb_vivant rollback
check "R1: rollback avec helper orphelin : refuse par le verrou (rc 11), rien execute" '[ $RC = 11 ] && [ "$(sha256sum $D/99-workboard2.conf | cut -c1-16)" = "$PH" ] && nosysmut'
python3 "$T/drive.py" cleanup; sleep 1; run R1_rb rollback
check "R1: rollback apres SIGKILL du helper : rc 0, provenance citee" '[ $RC = 0 ] && grep -q "provenance etablie" $LOGS/R1_rb.log'; state_ok R1
echo "### R2 SIGKILL groupe apres creation du drop-in, avant reload"; reset; mkscript h_stall_linked; run R2 prepare; dr R2 MARK_DROPIN_CREATED kill_group; run R2_rb rollback; check "R2: rollback rc 0" '[ $RC = 0 ]'; state_ok R2
echo "### R3 SIGKILL du parent APRES reload+restart (web sert la nouvelle release), puis rollback"; reset; mkscript h_stall_restart; run R3 prepare; dr R3 MARK_AFTER_RESTART kill_parent
check "R3: le web sert la NOUVELLE release" '[ "$(cat $SBX/state/running_wd)" = "$O/releases/$NEW/frontend" ]'
python3 "$T/drive.py" cleanup; sleep 1; : > $SBX/systemctl.log; run R3_rb rollback
check "R3: rollback rc 0, reload + restart du web seul" '[ $RC = 0 ] && grep -q "^systemctl daemon-reload" $SBX/systemctl.log && grep -q "^systemctl restart crypto-operator-web.service" $SBX/systemctl.log'; state_ok R3
echo "### R4 SIGTERM / SIGHUP groupe / terminal perdu, apres creation du drop-in"
for spec in "R4a term_helper" "R4b hup_group" "R4c pty_loss"; do set -- $spec; reset; mkscript h_stall_linked; run $1 prepare; dr $1 MARK_DROPIN_CREATED $2
  check "$1 ($2): script rc != 0, recuperation OK ecrite dans recover.log" '[ "$PRC" != 0 ] && grep -q "RECUPERATION OK" $EVD/recover.log'; state_ok $1; done
echo "### R4d terminal perdu apres reload+restart"; reset; mkscript h_stall_restart; run R4d prepare; dr R4d MARK_AFTER_RESTART pty_loss
check "R4d: recover.log RECUPERATION OK" 'grep -q "RECUPERATION OK" $EVD/recover.log'; state_ok R4d

echo "### R6 deuxieme tentative apres un ROLLED_BACK : l'inode du journal precedent ne doit pas etre reutilise"
reset; mkscript orig; run R6a prepare; run R6a_act activate; run R6a_rb rollback; check "R6: premiere tentative puis rollback OK" '[ $RC = 0 ]'
mkscript h_stall_linked; rm -rf $O/releases/$NEW; run R6b prepare; dr R6b MARK_DROPIN_CREATED kill_group; run R6b_rb rollback
check "R6: kill apres link de la 2e tentative : rollback rc 0 (provenance etablie malgre l'inode de la 1re)" '[ $RC = 0 ] && grep -q "provenance etablie" $LOGS/R6b_rb.log'; state_ok R6
echo "### R5 provenance refusee : contenu remplace / lien symbolique / sans journal / journal perime / contenu attendu altere / ROLLED_BACK"
reset; mkscript orig; run R5 prepare; run R5_act activate; printf '[Service]\nEnvironment=AUTRE=1\n' > $D/99-workboard2.conf; HP=$(sha256sum $D/99-workboard2.conf | cut -c1-16); : > $SBX/systemctl.log
run R5a rollback; check "R5a: contenu remplace : refus (rc 6), fichier intact, aucun reload/restart" '[ $RC = 6 ] && [ "$(sha256sum $D/99-workboard2.conf | cut -c1-16)" = "$HP" ] && nosysmut'
rm -f $EVD/INCOMPLETE_RESTORE; rm -f $D/99-workboard2.conf; cp $EXPF /tmp/wfb-same; cat /tmp/wfb-same > $D/99-workboard2.conf   # meme contenu, AUTRE inode (apres HELPER_DONE)
sed -i 's/^STATE=.*/STATE=ACTIVE_VERIFIED/' $JF; sed -i 's/^DROPIN_INODE=.*/DROPIN_INODE=1/' $JF; : > $SBX/systemctl.log; run R5b rollback
check "R5b: meme contenu, inode different de celui du journal : refus (rc 6)" '[ $RC = 6 ] && grep -q "inode different" $LOGS/R5b.log && nosysmut'
rm -f $EVD/INCOMPLETE_RESTORE $D/99-workboard2.conf; ln -s /tmp/wfb-same $D/99-workboard2.conf; run R5c rollback
check "R5c: lien symbolique : refus (rc 6), lien intact" '[ $RC == 6 ] && [ -L $D/99-workboard2.conf ]'; rm -f $D/99-workboard2.conf $EVD/INCOMPLETE_RESTORE
cp $EXPF $D/99-workboard2.conf; sed -i "s/^T0_EPOCH=.*/T0_EPOCH=$(( $(date +%s) + 3600 ))/" $JF; sed -i 's/^DROPIN_INODE=.*/DROPIN_INODE=/' $JF; run R5d rollback
check "R5d: journal perime (fichier plus ancien que la tentative) : refus (rc 6)" '[ $RC = 6 ] && grep -q "plus ancien" $LOGS/R5d.log'; rm -f $D/99-workboard2.conf $EVD/INCOMPLETE_RESTORE
reset; mkscript orig; run R5e prepare; run R5e_act activate; echo "# altere" >> $EXPF; : > $SBX/systemctl.log; run R5e rollback
check "R5e: contenu attendu altere apres le journal : refus (rc 6)" '[ $RC = 6 ] && grep -q "altere" $LOGS/R5e.log && [ -e $D/99-workboard2.conf ]'
reset; mkscript orig; run R5f prepare; cp /tmp/wfb-same $D/99-workboard2.conf; run R5f rollback
check "R5f: AUCUN journal, fichier au contenu correct : refus (rc 6), le contenu seul ne prouve rien" '[ $RC = 6 ] && grep -q "aucun journal" $LOGS/R5f.log && [ -e $D/99-workboard2.conf ]'
run R5f_act activate; check "R5f: activate refuse un fichier preexistant (rc 8)" '[ $RC = 8 ]'; rm -f $D/99-workboard2.conf $EVD/INCOMPLETE_RESTORE
reset; mkscript orig; run R5g prepare; run R5g_act activate; run R5g_rb1 rollback; cp /tmp/wfb-same $D/99-workboard2.conf; run R5g_rb2 rollback
check "R5g: apres ROLLED_BACK, un nouveau fichier est refuse (rc 6)" '[ $RC = 6 ] && [ -e $D/99-workboard2.conf ]'; rm -f $D/99-workboard2.conf $EVD/INCOMPLETE_RESTORE

echo; echo "################ F : verification du rollback, echecs comptes, preuves ################"
echo "### F1 le restart echoue pendant le rollback (apres activation reussie)"; reset; mkscript orig; run F1 prepare; run F1_act activate; check "F1: activation nominale" '[ $RC = 0 ]'
touch $SBX/knobs/fail_restart_always; : > $SBX/systemctl.log; run F1_rb rollback
check "F1: rollback INCOMPLET (rc 7), echec 'restart web' compte" '[ $RC = 7 ] && grep -q "ROLLBACK INCOMPLET" $LOGS/F1_rb.log && grep -q "\[ECHEC\].*restart web" $LOGS/F1_rb.log'
check "F1: le fichier de la tentative est retire et la configuration rechargee (le web reste a l'ancienne config mais le processus sert l'ancien index NEW : verifie, compte)" '[ ! -e $D/99-workboard2.conf ] && [ "$(cat $SBX/state/loaded_wd)" = "$OLDWD" ] && grep -q "\[ECHEC\].*index servi" $LOGS/F1_rb.log'
check "F1: echecs comptes dans failures.log (>= 2) et dans le journal" '[ "$(nflog)" -ge 2 ] && grep -q "^RESTORE_FAIL_COUNT=[2-9]" $JF'
check "F1: preuves : dossier, SHA256SUMS, state.txt, status-web.txt, failures.log copie" 'd=$(cat $EVD/INCOMPLETE_RESTORE) && [ -s $d/SHA256SUMS ] && [ -s $d/state.txt ] && [ -e $d/status-web.txt ] && [ -s $d/failures.log ]'
check "F1: les preuves sont dans le staging et aucun fichier d'evidence n'a ete supprime" 'ls $EVD/helper-activate.json $EVD/before.txt $EVD/protected-before.txt >/dev/null 2>&1'
check "F1: Advisor/API jamais cibles" 'noprotected'
echo "### F1b nouveau rollback une fois le restart repare : le web (seul) est relance parce que l'INDEX SERVI n'est pas celui de l'ancienne release"
rm -f $SBX/knobs/fail_restart_always; : > $SBX/systemctl.log; run F1b_rb rollback
check "F1b: rc 0, restart du web constate sur l'index servi" '[ $RC = 0 ] && grep -q "l.index servi n.est pas celui de" $LOGS/F1b_rb.log && grep -q "^systemctl restart crypto-operator-web.service" $SBX/systemctl.log'; state_ok F1b
check "F1b: marqueur retire seulement apres verification complete, preuves conservees" '[ ! -e $EVD/INCOMPLETE_RESTORE ] && ls -d $EVD/incomplete-restore-*/ >/dev/null 2>&1'
echo "### F2 daemon-reload refuse en permanence pendant le rollback"; reset; mkscript orig; run F2 prepare; run F2_act activate; touch $SBX/knobs/fail_reload_always; run F2_rb rollback
check "F2: rollback INCOMPLET (rc 7), echec daemon-reload compte, preuves conservees" '[ $RC = 7 ] && grep -q "\[ECHEC\].*daemon-reload" $LOGS/F2_rb.log && [ -e $EVD/INCOMPLETE_RESTORE ]'
echo "### F3 reload refuse une fois pendant l'activation (helper reel) : le helper restaure, le bloc constate (0 echec)"; reset; mkscript orig; run F3 prepare; touch $SBX/knobs/fail_reload_once; run F3_act activate
check "F3: activation en echec (rc != 0), RECUPERATION OK, 0 echec de RESTAURATION mais l'echec d'activation est compte" '[ $RC != 0 ] && grep -q "RECUPERATION OK" $LOGS/F3_act.log && grep -q "activation interrompue ou en echec" $EVD/failures.log && grep -q "^RESTORE_FAIL_COUNT=0" $JF && grep -q "^FAIL_COUNT=[1-9]" $JF'; state_ok F3
echo "### F4 reload refuse TOUJOURS pendant l'activation : le helper ne peut pas restaurer, il le declare ; le bloc compte et conserve les preuves"; reset; mkscript orig; run F4 prepare; touch $SBX/knobs/fail_reload_always; run F4_act activate
check "F4: le helper declare sa restauration INCOMPLETE (cite dans recover.log, ligne dans failures.log)" 'grep -q "INCOMPLETE" $EVD/helper-activate.err && grep -q "le helper declare [1-9]" $LOGS/F4_act.log && grep -q "le helper declare" $EVD/failures.log'
check "F4: l'etat reel est constate conforme par le bloc (rien n'avait ete charge) : RECUPERATION OK, pas de marqueur" '[ $RC = 1 ] && grep -q "RECUPERATION OK" $LOGS/F4_act.log && [ ! -e $EVD/INCOMPLETE_RESTORE ] && [ ! -e $D/99-workboard2.conf ]'
rm -f $SBX/knobs/fail_reload_always; run F4_rb rollback; check "F4: rollback une fois le reload repare : rc 0" '[ $RC = 0 ]'; state_ok F4

echo; echo "################ V : verifications apres activation ################"
echo "### V1 css servi altere (helper sans controle) : le controle independant du bloc echoue, compte, rien d'annule seul"; reset; mkscript h_noverify; run V1 prepare; touch $SBX/knobs/tamper_css; run V1_act activate
check "V1: rc 9, [ECHEC] sur le css, VERIFICATION OBLIGATOIRE ECHOUEE avec le nombre d'echecs" '[ $RC = 9 ] && grep -q "\[ECHEC\].*css" $LOGS/V1_act.log && grep -qE "VERIFICATION OBLIGATOIRE ECHOUEE \([1-9][0-9]* echec" $LOGS/V1_act.log'
check "V1: pas d'annulation automatique, journal VERIFY_FAILED, failures.log non vide" '[ -e $D/99-workboard2.conf ] && [ "$(jstate)" = VERIFY_FAILED ] && [ "$(nflog)" -ge 1 ]'
rm -f $SBX/knobs/tamper_css; run V1_rb rollback; check "V1: rollback manuel rc 0, tout verifie" '[ $RC = 0 ]'; state_ok V1
echo "### V2 99-workboard.conf (activation precedente) absent : activate refuse"; reset; mkscript orig; run V2 prepare; rm -f $D/99-workboard.conf; run V2_act activate
check "V2: rc 8, rien cree" '[ $RC = 8 ] && [ ! -e $O/releases/$NEW ]'
echo "### V3 fichier temporaire preexistant : activate refuse"; reset; mkscript orig; run V3 prepare; : > $D/.99-workboard2.conf.tmp; run V3_act activate
check "V3: rc 8, temporaire intact, rien cree" '[ $RC = 8 ] && [ -e $D/.99-workboard2.conf.tmp ] && [ ! -e $O/releases/$NEW ]'
echo "### V4 entree non interactive / empreinte alteree"; reset; mkscript orig; run V4 prepare
PATH=$SBX/bin:$PATH bash $SBX/final_block.sh activate > $LOGS/V4_act.log 2>&1 < /dev/null; check "V4: pas de ACTIVER : rc != 0, rien cree" '[ $? != 0 ] && [ ! -e $D/99-workboard2.conf ] && [ ! -e $O/releases/$NEW ]'
reset; mkscript orig; echo tampered >> $R/src/workboard-frontend-8ff089b.tar.gz; run V4b prepare; check "V4b: archive alteree : prepare echoue" '[ $RC != 0 ] && grep -q FAILED $LOGS/V4b.log'

pkill -KILL -f "activate_workboard_frontend.py --archive" 2>/dev/null; kill $(cat $SBX/srv.pid) 2>/dev/null
echo; echo "RESULTAT : $PASS PASS, $FAILN FAIL"
echo "bloc teste : scripts/workboard_frontend_final_block.sh  $(sha256sum "$T/../../scripts/workboard_frontend_final_block.sh" | cut -c1-64)"
echo "helper teste : scripts/activate_workboard_frontend.py  $(sha256sum "$REPO/scripts/activate_workboard_frontend.py" | cut -c1-64)"
rm -rf "$SBX" /tmp/wfb-same
[ "$FAILN" = 0 ]
