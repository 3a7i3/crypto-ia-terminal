<#
.SYNOPSIS
    Audit de sauvegarde avant reinitialisation de la machine (Windows).

.DESCRIPTION
    Outil de MESURE uniquement : lecture seule, aucune ecriture dans le depot,
    aucun effet sur une decision de trading (ADR-0007).

    Repond a une seule question : « si je formate ce PC maintenant, qu'est-ce
    que je perds definitivement ? »

    Equivalent Windows de scripts/backup_audit.sh, avec une section
    supplementaire pour les artefacts situes HORS du depot — notamment la cle
    SSH d'acces au VPS, que la version bash ne couvre pas.

.PARAMETER Archive
    Repertoire de destination. Si fourni, copie les artefacts non versionnes
    critiques (depot ET hors depot) vers ce repertoire.

.EXAMPLE
    .\scripts\backup_audit.ps1

.EXAMPLE
    .\scripts\backup_audit.ps1 -Archive E:\sauvegarde
#>

[CmdletBinding()]
param(
    [string]$Archive
)

$ErrorActionPreference = 'Continue'

# Racine du depot = parent du dossier scripts/
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$script:Pertes = 0

function Write-Section { param([string]$T) Write-Host "`n=== $T ===" -ForegroundColor White }
function Write-Ok      { param([string]$M) Write-Host "  [OK]     $M" -ForegroundColor Green }
function Write-Risque  { param([string]$M) Write-Host "  [RISQUE] $M" -ForegroundColor Yellow; $script:Pertes++ }
function Write-Perte   { param([string]$M) Write-Host "  [PERTE]  $M" -ForegroundColor Red;    $script:Pertes++ }

function Format-Taille {
    param([long]$Octets)
    if ($Octets -ge 1GB) { return "{0:N1} Go" -f ($Octets / 1GB) }
    if ($Octets -ge 1MB) { return "{0:N1} Mo" -f ($Octets / 1MB) }
    if ($Octets -ge 1KB) { return "{0:N1} Ko" -f ($Octets / 1KB) }
    return "$Octets o"
}

Write-Host "AUDIT DE SAUVEGARDE — $RepoRoot" -ForegroundColor White
Write-Host ("Date : " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERREUR : git introuvable dans le PATH." -ForegroundColor Red
    exit 2
}

$AArchiver = New-Object System.Collections.Generic.List[string]

# ---------------------------------------------------------------------------
# 1. Travail non commite
# ---------------------------------------------------------------------------
Write-Section "1. Travail non commite"

$Statut = git status --porcelain
if ($Statut) {
    Write-Perte "Modifications non commitees :"
    $Statut | ForEach-Object { Write-Host "           $_" }
} else {
    Write-Ok "Arbre de travail propre."
}

$Stashes = git stash list
if ($Stashes) {
    Write-Perte "$(@($Stashes).Count) stash(es) — invisibles sur GitHub :"
    $Stashes | ForEach-Object { Write-Host "           $_" }
} else {
    Write-Ok "Aucun stash en attente."
}

# ---------------------------------------------------------------------------
# 2. Commits et tags non pousses
# ---------------------------------------------------------------------------
Write-Section "2. Commits et tags non pousses"

git fetch --all --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Risque "fetch impossible (reseau) — resultats ci-dessous potentiellement perimes."
}

$NonPousse = 0
foreach ($Branche in (git for-each-ref --format='%(refname:short)' refs/heads/)) {
    if (-not $Branche) { continue }
    $Upstream = git rev-parse --abbrev-ref "$Branche@{upstream}" 2>$null
    if (-not $Upstream) {
        Write-Perte "Branche '$Branche' n'a AUCUN equivalent distant — jamais poussee."
        $NonPousse++
        continue
    }
    $Ahead = git rev-list --count "$Upstream..$Branche" 2>$null
    if ([int]$Ahead -gt 0) {
        Write-Perte "Branche '$Branche' : $Ahead commit(s) en avance sur $Upstream."
        $NonPousse++
    }
}
if ($NonPousse -eq 0) { Write-Ok "Toutes les branches locales sont poussees." }

$TagsLocaux   = @(git tag -l)
$TagsDistants = @(git ls-remote --tags origin 2>$null |
    ForEach-Object { ($_ -split 'refs/tags/')[-1] -replace '\^\{\}$', '' } |
    Sort-Object -Unique)
$TagsManquants = @($TagsLocaux | Where-Object { $_ -and ($TagsDistants -notcontains $_) })
if ($TagsManquants.Count -gt 0) {
    Write-Perte "Tags locaux absents de GitHub (journal d'audit des deploiements) :"
    $TagsManquants | ForEach-Object { Write-Host "           $_" }
} else {
    Write-Ok "Tous les tags locaux sont sur GitHub."
}

# ---------------------------------------------------------------------------
# 3. Artefacts critiques DANS le depot (exclus par .gitignore)
# ---------------------------------------------------------------------------
Write-Section "3. Artefacts critiques dans le depot (exclus par .gitignore)"

$Critiques = @(
    @{ P = 'databases\paper_trades.jsonl';     D = 'Dataset scientifique — base de N, du CRI et de tous les seuils' }
    @{ P = 'databases\paper_trades_vps.jsonl'; D = 'Miroir local des trades VPS' }
    @{ P = 'databases\regret_analysis.jsonl';  D = 'Analyse de regret — MISSED_WIN / GOOD_REFUSAL' }
    @{ P = '.env';                             D = 'Cles API (Kraken, Gate.io, Binance), tokens Telegram, config VPS' }
    @{ P = '.env.smtp';                        D = 'Credentials SMTP' }
)

foreach ($C in $Critiques) {
    if (Test-Path $C.P) {
        $Item = Get-Item $C.P
        $Detail = Format-Taille $Item.Length
        if ($C.P -like '*.jsonl') {
            $NbLignes = (Get-Content $C.P | Measure-Object).Count
            $Detail += ", $NbLignes lignes"
        }
        Write-Perte "$($C.P) ($Detail) : $($C.D)"
        $AArchiver.Add($C.P)
    } else {
        Write-Ok "$($C.P) absent localement — rien a perdre ici."
    }
}

Write-Section "4. Repertoires ignores presents localement"
foreach ($Rep in @('databases', 'logs', 'data', 'archives', 'cache', 'setup')) {
    if (-not (Test-Path $Rep -PathType Container)) { continue }
    # Ne compter que ce qui n'est PAS suivi par git : le reste est deja sur GitHub.
    $NonSuivis = @(git ls-files --others --directory --no-empty-directory -- $Rep 2>$null)
    $Nb = 0
    foreach ($P in $NonSuivis) {
        if (Test-Path $P -PathType Container) {
            $Nb += @(Get-ChildItem $P -Recurse -File -ErrorAction SilentlyContinue).Count
        } elseif ($P) { $Nb++ }
    }
    if ($Nb -gt 0) {
        $Taille = Format-Taille ((Get-ChildItem $Rep -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum)
        Write-Risque "$Rep\ — $Nb fichier(s) non versionne(s) (repertoire : $Taille)"
        $AArchiver.Add($Rep)
    } else {
        Write-Ok "$Rep\ — tout son contenu est suivi par git."
    }
}

# ---------------------------------------------------------------------------
# 5. Artefacts HORS du depot — invisibles pour la version bash
# ---------------------------------------------------------------------------
Write-Section "5. Artefacts hors du depot"

# Cle SSH d'acces au VPS. scripts/deploy_vps.sh la resout ainsi :
#     VPS_KEY="${VPS_KEY:-$HOME/.ssh/gcp_key}"
# Elle vit donc dans le profil utilisateur, hors du depot. La perdre, c'est
# perdre l'acces au VPS — donc au systeme en production et a la copie vivante
# du dataset.
$CheminSsh = Join-Path $env:USERPROFILE '.ssh'
$CleVps = $null
if (Test-Path (Join-Path $RepoRoot '.env')) {
    $Ligne = Select-String -Path (Join-Path $RepoRoot '.env') -Pattern '^\s*VPS_KEY\s*=' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Ligne) {
        $CleVps = ($Ligne.Line -split '=', 2)[1].Trim().Trim('"').Trim("'")
        $CleVps = $CleVps -replace '^~', $env:USERPROFILE
    }
}
if (-not $CleVps) { $CleVps = Join-Path $CheminSsh 'gcp_key' }

if (Test-Path $CleVps) {
    Write-Perte "$CleVps : cle SSH d'acces au VPS — sans elle, plus d'acces au serveur"
    $AArchiver.Add($CleVps)
} else {
    Write-Risque "$CleVps introuvable — verifiez ou se trouve reellement votre cle VPS."
}

if (Test-Path $CheminSsh) {
    $AutresCles = @(Get-ChildItem $CheminSsh -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -notin @('.pub') -and $_.Name -ne 'known_hosts' })
    if ($AutresCles.Count -gt 0) {
        Write-Perte "$CheminSsh contient $($AutresCles.Count) fichier(s) — cles et config SSH :"
        $AutresCles | ForEach-Object { Write-Host "           $($_.Name)" }
        $AArchiver.Add($CheminSsh)
    }
} else {
    Write-Ok "$CheminSsh absent."
}

# Configuration git globale (identite, aliases, credentials helper)
$GitConfig = Join-Path $env:USERPROFILE '.gitconfig'
if (Test-Path $GitConfig) {
    Write-Risque "$GitConfig : identite et configuration git globale"
    $AArchiver.Add($GitConfig)
}

# ---------------------------------------------------------------------------
# 6. Archivage optionnel
# ---------------------------------------------------------------------------
if ($Archive) {
    Write-Section "6. Archivage vers $Archive"
    if (-not (Test-Path $Archive -PathType Container)) {
        Write-Host "  ERREUR : $Archive n'existe pas." -ForegroundColor Red
        exit 1
    }
    $Horodatage = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $Dest = Join-Path $Archive "crypto_ai_terminal-backup-$Horodatage"
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null

    foreach ($Chemin in ($AArchiver | Sort-Object -Unique)) {
        try {
            if ([System.IO.Path]::IsPathRooted($Chemin)) {
                # Artefact hors depot : ranger sous hors_depot\ pour eviter les collisions
                $Cible = Join-Path $Dest ('hors_depot\' + (Split-Path $Chemin -Leaf))
            } else {
                $Cible = Join-Path $Dest $Chemin
            }
            $DossierCible = Split-Path $Cible -Parent
            if (-not (Test-Path $DossierCible)) {
                New-Item -ItemType Directory -Path $DossierCible -Force | Out-Null
            }
            Copy-Item $Chemin -Destination $Cible -Recurse -Force -ErrorAction Stop
            Write-Ok "copie : $Chemin"
        } catch {
            Write-Host "  [ECHEC]  $Chemin — $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    Write-Host "  Archive : $Dest"
    Write-Host "  Verifiez son contenu AVANT de reinitialiser la machine."
}

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
Write-Section "VERDICT"
if ($script:Pertes -eq 0) {
    Write-Host "  Tout est sur GitHub. Reinitialisation sans perte." -ForegroundColor Green
    exit 0
}
Write-Host "  $($script:Pertes) point(s) de perte potentielle." -ForegroundColor Yellow
Write-Host "  Ne reinitialisez pas avant d'avoir traite chaque ligne [PERTE]."
Write-Host "  Rappel : le VPS detient peut-etre la copie vivante du dataset —"
Write-Host "  verifiez-la avant de considerer une perte locale comme acceptable."
exit 1
