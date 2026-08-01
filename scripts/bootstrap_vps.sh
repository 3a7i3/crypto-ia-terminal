#!/usr/bin/env bash
# =============================================================================
# bootstrap_vps.sh — Reconstruit une machine de production depuis zéro.
#
# Ce script ne DÉPLACE pas une machine : il la RECONSTRUIT. Il est écrit à
# partir d'un inventaire réel de crypto-advisor-2 (2026-07-31), pas d'un
# souvenir. Chaque valeur en dur ci-dessous a été mesurée.
#
# Il couvre les couches 1 à 3 (infra, runtime, projet). Les couches 4
# (données) et 5 (secrets) NE PEUVENT PAS être automatisées et sont guidées
# à la fin : les données se copient depuis l'ancienne machine, les secrets se
# re-saisissent à la main.
#
# Usage :
#   bash bootstrap_vps.sh --check          # diagnostic seul, ne modifie rien
#   bash bootstrap_vps.sh --confirm        # exécute
#   bash bootstrap_vps.sh --confirm --skip-apt   # si les paquets sont déjà là
#
# Sans --confirm : affiche l'usage et sort. Aucune exécution implicite,
# même règle que deploy_vps.sh.
# =============================================================================

set -uo pipefail

# ── Constantes MESURÉES sur la production (ne pas deviner) ───────────────────
readonly PROJECT_USER="mathieu"
readonly PROJECT_ROOT="/home/mathieu/crypto_ai_terminal"
readonly PYTHON_BIN="/usr/bin/python3.11"
readonly PYTHON_VERSION_ATTENDUE="3.11.15"
readonly VENV="${PROJECT_ROOT}/.venv"
readonly FROZEN="requirements-vps-frozen-20260718.txt"
readonly FROZEN_SHA256="63b63633e128eb614894e3486d7a44db5db10e2d956b2cd005a5d05fc3e8fd56"
readonly FROZEN_NB_PAQUETS=92
readonly PIP_VERSION="26.1.2"
readonly SETUPTOOLS_VERSION="79.0.1"
readonly CCXT_VERSION_ATTENDUE="4.5.52"
readonly REPO_URL="https://github.com/3a7i3/crypto-ia-terminal.git"

ROUGE=$'\033[31m'; VERT=$'\033[32m'; JAUNE=$'\033[33m'; RAZ=$'\033[0m'
ERREURS=0

log()  { printf '  %s\n' "$*"; }
ok()   { printf '  %sOK%s   %s\n' "$VERT" "$RAZ" "$*"; }
warn() { printf '  %sATTN%s %s\n' "$JAUNE" "$RAZ" "$*"; }
ko()   { printf '  %sKO%s   %s\n' "$ROUGE" "$RAZ" "$*"; ERREURS=$((ERREURS + 1)); }
titre() { printf '\n%s\n  %s\n%s\n' "$(printf '=%.0s' {1..70})" "$*" "$(printf '=%.0s' {1..70})"; }

MODE=""
SKIP_APT=0
for arg in "$@"; do
    case "$arg" in
        --check)    MODE="check" ;;
        --confirm)  MODE="run" ;;
        --skip-apt) SKIP_APT=1 ;;
        *) echo "Argument inconnu : $arg"; exit 2 ;;
    esac
done

if [[ -z "$MODE" ]]; then
    sed -n '3,22p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi

run() {
    # Exécute, ou affiche seulement en mode --check.
    if [[ "$MODE" == "check" ]]; then
        log "[check] $*"
        return 0
    fi
    "$@"
}

# =============================================================================
titre "COUCHE 0 — Prérequis de la machine cible"
# =============================================================================

if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    log "Distribution : ${PRETTY_NAME:-inconnue}"
    if [[ "${VERSION_CODENAME:-}" != "jammy" ]]; then
        ko "Attendu Ubuntu 22.04 (jammy), trouvé '${VERSION_CODENAME:-?}'."
        log "     Le PPA deadsnakes utilisé plus bas est épinglé sur jammy."
        log "     Sur une autre base, python3.11 doit venir d'ailleurs (pyenv,"
        log "     deadsnakes noble, image docker) et le build de Python change."
    else
        ok "Ubuntu 22.04 jammy"
    fi
fi

ARCH="$(dpkg --print-architecture 2>/dev/null || echo '?')"
if [[ "$ARCH" != "amd64" ]]; then
    ko "Architecture '$ARCH' : la production est amd64."
    log "     Toute la pile est installée depuis des wheels x86_64. Sur arm64,"
    log "     plusieurs paquets n'ont pas de wheel et devront compiler."
else
    ok "Architecture amd64"
fi

if [[ "$(id -un)" != "$PROJECT_USER" ]]; then
    warn "Exécuté en tant que '$(id -un)', la production tourne en '$PROJECT_USER'."
    log "     Le chemin ${PROJECT_ROOT} est structurant : les unités systemd"
    log "     lancent le venv par chemin ABSOLU, sans activation. Changer"
    log "     d'utilisateur oblige à réécrire les 5 unités."
fi

FREE_GB="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
if [[ -n "$FREE_GB" && "$FREE_GB" -lt 12 ]]; then
    ko "Espace libre ${FREE_GB} Go : insuffisant (venv 1,1 Go + données ~5 Go)."
else
    ok "Espace libre ${FREE_GB:-?} Go"
fi

# =============================================================================
titre "COUCHE 1 — Infrastructure"
# =============================================================================

if [[ "$SKIP_APT" -eq 0 ]]; then
    log "Paquets système…"
    run sudo apt-get update -qq
    run sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        git curl gzip build-essential software-properties-common ca-certificates

    # python3.11 NE VIENT PAS des dépôts jammy : ceux-ci ne proposent qu'une
    # release candidate (3.11.0~rc1). Sans ce PPA, on installe silencieusement
    # une RC avec 15 versions de patch de retard.
    if ! ls /etc/apt/sources.list.d/ 2>/dev/null | grep -qi deadsnakes; then
        log "Ajout du PPA deadsnakes (obligatoire pour un vrai 3.11)…"
        run sudo add-apt-repository -y ppa:deadsnakes/ppa
        run sudo apt-get update -qq
    else
        ok "PPA deadsnakes déjà présent"
    fi
    run sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        python3.11 python3.11-venv python3.11-dev
else
    log "--skip-apt : installation des paquets ignorée"
fi

if [[ "$MODE" == "run" ]]; then
    VER="$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')"
    if [[ "$VER" != "$PYTHON_VERSION_ATTENDUE" ]]; then
        warn "python3.11 = $VER, production = $PYTHON_VERSION_ATTENDUE"
        log "     Écart de patch toléré ; un écart de mineure ne l'est pas."
    else
        ok "python3.11 = $VER"
    fi
fi

run sudo timedatectl set-timezone Etc/UTC
ok "Fuseau horaire : Etc/UTC (la production est en UTC, tous les timers aussi)"

# =============================================================================
titre "COUCHE 3 — Projet (avant le venv : le frozen doit exister)"
# =============================================================================

if [[ -d "${PROJECT_ROOT}/.git" ]]; then
    ok "Dépôt déjà présent dans ${PROJECT_ROOT}"
else
    log "Clonage du dépôt…"
    run git clone "$REPO_URL" "$PROJECT_ROOT"
fi

# AVERTISSEMENT STRUCTURANT — voir le runbook de migration.
warn "Le dépôt cloné n'est PAS la production."
log "     Sur crypto-advisor-2, git HEAD était à 5d1955e alors qu'une"
log "     vingtaine de fichiers y avaient été déployés par scp depuis"
log "     (deploy_vps.sh copie des fichiers, il ne pousse pas de commit)."
log "     Un clone seul produit donc une machine DIFFÉRENTE de la production."
log "     -> Après ce script, déployer explicitement le commit voulu, ou"
log "        rsync le code depuis l'ancienne machine, puis comparer."

cd "$PROJECT_ROOT" || { ko "Impossible d'entrer dans ${PROJECT_ROOT}"; exit 1; }

if [[ -f "$FROZEN" ]]; then
    SHA="$(sha256sum "$FROZEN" | awk '{print $1}')"
    if [[ "$SHA" == "$FROZEN_SHA256" ]]; then
        ok "${FROZEN} conforme (sha256 vérifié)"
    else
        ko "${FROZEN} : sha256 inattendu."
        log "     attendu $FROZEN_SHA256"
        log "     obtenu  $SHA"
        log "     Le runtime reconstruit ne sera pas celui de la production."
    fi
else
    ko "${FROZEN} introuvable — impossible de reconstruire le runtime."
fi

# =============================================================================
titre "COUCHE 2 — Runtime Python"
# =============================================================================

# Le venv se RECRÉE, il ne se copie JAMAIS : .venv/bin/python est un symlink
# vers /usr/bin/python3.11, et tous les scripts de .venv/bin portent le chemin
# absolu en shebang. Un rsync du venv donne une machine cassée.
if [[ -x "${VENV}/bin/python" ]]; then
    ok "venv déjà présent"
else
    log "Création du venv (commande exacte relevée dans pyvenv.cfg)…"
    run "$PYTHON_BIN" -m venv "$VENV"
fi

# pip freeze n'écrit ni pip ni setuptools : sans cette étape, le venv démarre
# avec le pip d'ensurepip (bien plus ancien), dont le résolveur diffère.
log "Alignement de l'outillage pip sur la production…"
run "${VENV}/bin/python" -m pip install -q --upgrade \
    "pip==${PIP_VERSION}" "setuptools==${SETUPTOOLS_VERSION}"
log "  (le paquet 'wheel' est volontairement ABSENT en production)"

log "Installation des ${FROZEN_NB_PAQUETS} paquets gelés…"
log "  requirements.txt et requirements-vps.txt ne décrivent PAS la production"
log "  (bornes >=, dérive garantie). Le frozen est la seule source valide."
run "${VENV}/bin/pip" install -q -r "$FROZEN"

if [[ "$MODE" == "run" ]]; then
    NB="$("${VENV}/bin/pip" freeze | wc -l)"
    [[ "$NB" -eq "$FROZEN_NB_PAQUETS" ]] \
        && ok "pip freeze = ${NB} paquets" \
        || ko "pip freeze = ${NB} paquets, attendu ${FROZEN_NB_PAQUETS}"

    if diff <("${VENV}/bin/pip" freeze | sort) <(sort "$FROZEN") >/dev/null 2>&1; then
        ok "venv strictement conforme au frozen"
    else
        ko "venv divergent du frozen :"
        diff <("${VENV}/bin/pip" freeze | sort) <(sort "$FROZEN") | head -10
    fi

    CCXT="$("${VENV}/bin/python" -c 'import ccxt; print(ccxt.__version__)' 2>/dev/null)"
    [[ "$CCXT" == "$CCXT_VERSION_ATTENDUE" ]] \
        && ok "ccxt ${CCXT}" \
        || ko "ccxt ${CCXT:-absent}, attendu ${CCXT_VERSION_ATTENDUE}"

    "${VENV}/bin/python" -c \
        "import sys; assert 'dist-packages' not in ' '.join(sys.path)" 2>/dev/null \
        && ok "venv étanche (aucune fuite du site-packages système)" \
        || ko "fuite du site-packages système — venv créé avec --system-site-packages ?"
fi

# =============================================================================
titre "COUCHE 1bis — Unités systemd"
# =============================================================================

log "5 unités attendues : crypto-advisor, crypto-watchdog (services longs),"
log "crypto-market-observer / radar / horizons (oneshot + timers)."

UNITS_SRC="${PROJECT_ROOT}/scripts/systemd"
if [[ -d "$UNITS_SRC" ]]; then
    for f in "$UNITS_SRC"/*.service "$UNITS_SRC"/*.timer; do
        [[ -e "$f" ]] || continue
        run sudo cp "$f" /etc/systemd/system/
        log "  déployé : $(basename "$f")"
    done
    run sudo systemctl daemon-reload
    ok "Unités copiées et daemon-reload effectué"
    warn "Les unités ne sont PAS démarrées par ce script."
    log "     Rien ne doit tourner avant que les données et le .env soient en"
    log "     place : un moteur qui démarre sans son état écrirait par-dessus."
else
    ko "${UNITS_SRC} introuvable — les unités systemd ne sont pas dans le dépôt."
    log "     Les récupérer depuis l'ancienne machine (systemctl cat <unité>)."
fi

run mkdir -p "${PROJECT_ROOT}/databases" "${PROJECT_ROOT}/logs" \
             "${PROJECT_ROOT}/cache" "${PROJECT_ROOT}/runtime"

# =============================================================================
titre "COUCHES 4 et 5 — NON automatisables"
# =============================================================================

cat <<'GUIDE'
  Ces deux couches ne peuvent pas être scriptées sans compromettre la
  sécurité ou l'intégrité des données. Procédure, dans cet ordre :

  COUCHE 4 — DONNÉES (~5 Go, le patrimoine du projet)

    Arrêter d'abord le moteur sur l'ANCIENNE machine, sinon les .jsonl
    sont copiés en cours d'écriture et la dernière ligne est tronquée :
      sudo systemctl stop crypto-advisor crypto-watchdog

    IRREMPLAÇABLE (à copier absolument) :
      databases/paper_trades.jsonl        le dataset scientifique
      databases/regret/                   63 Mo  source canonique du regret
      databases/rejections/              390 Mo  refus du moteur
      databases/observation/             367 Mo  pouls marché
      databases/shadow_execution/         32 Mo
      databases/runtime_config.json       PARAMÈTRES DE RISQUE LIVE
      databases/integrity_audit.jsonl

    RÉGÉNÉRABLE (à laisser derrière, ~4 Go) :
      databases/decision_packets_*.jsonl  télémétrie de cycle
      databases/black_box.jsonl           chiffré, corrompu à 97 % depuis mai
      databases/cycle_data*.jsonl
      logs/                        1,1 Go
      cache/                       2 Mo

    Commande type, depuis la nouvelle machine :
      rsync -avz --progress \
        ancienne:/home/mathieu/crypto_ai_terminal/databases/paper_trades.jsonl \
        ancienne:/home/mathieu/crypto_ai_terminal/databases/runtime_config.json \
        /home/mathieu/crypto_ai_terminal/databases/
      rsync -avz ancienne:.../databases/{regret,rejections,observation}/ ...

    runtime_config.json est petit mais critique — contenu de production :
      EXEC_MAX_ORDER_USD 50 | SIGNAL_MIN_SCORE 70 | EO_DD_VETO 0.1
      EO_DD_RECOVERY 0.04 | EXCHANGE_HEARTBEAT_S 15
      _config_version CFG-20260714-0003

  COUCHE 5 — SECRETS (180 variables, dont ~10 secrets)

    NE PAS copier le .env en bloc : c'est l'occasion de faire le ménage.

    À RE-SAISIR à la main (jamais dans un script, jamais dans git) :
      MEXC_API_KEY / MEXC_API_SECRET
      BINANCE_API_KEY / BINANCE_API_SECRET
      TELEGRAM_BOT_TOKEN | INTEL_BOT_TOKEN | P10_PORTFOLIO_BOT_TOKEN
      REAL_ACCOUNT_BOT_TOKEN | PAPER_ARENA_TG_TOKEN
      EMAIL_SMTP_PASS

    Les ~170 autres variables sont de la configuration non secrète et se
    copient telles quelles depuis l'ancien .env.

    DÉFAUT À CORRIGER pendant la migration : WALLET_PAPER_CAPITAL et
    PB_MIN_POSITION_USD apparaissent DEUX FOIS dans le .env de production.
    La dernière occurrence gagne, silencieusement. Dédoublonner.

  ÉTAPE MANUELLE HORS MACHINE — la plus facile à oublier :

    >>> AJOUTER LA NOUVELLE IP PUBLIQUE À LA WHITELIST MEXC <<<

    Les clés sont whitelistées sur l'IP de l'ancienne machine. Tant que
    ce n'est pas fait, TOUTE lecture de compte échouera — y compris
    l'Observatory. Cela se fait dans l'interface MEXC, rien ne peut
    l'automatiser.

  ENSUITE SEULEMENT :
    bash scripts/compare_vps.sh ancienne nouvelle   # vérifier la fidélité
    sudo systemctl enable --now crypto-advisor crypto-watchdog
    sudo systemctl enable --now crypto-market-{observer,radar,horizons}.timer
GUIDE

# =============================================================================
titre "BILAN"
# =============================================================================

if [[ "$MODE" == "check" ]]; then
    log "Mode --check : aucune modification effectuée."
fi

if [[ "$ERREURS" -eq 0 ]]; then
    printf '\n  %sAucune anomalie bloquante.%s\n\n' "$VERT" "$RAZ"
    exit 0
else
    printf '\n  %s%d anomalie(s) — ne pas démarrer les services en l'\''état.%s\n\n' \
        "$ROUGE" "$ERREURS" "$RAZ"
    exit 1
fi
