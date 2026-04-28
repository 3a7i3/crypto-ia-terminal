# ============================================================
#  Restauration des fichiers Python tronqués / corrompus
#  ----------------------------------------------------------
#  Pour chaque fichier identifié comme cassé (ast.parse échoue) :
#  - Cherche la version la plus récente dans Git (toutes branches)
#  - Vérifie qu'elle compile
#  - Restaure via `git checkout <sha> -- <fichier>`
#  - Sinon, logge le fichier comme irrécupérable
#
#  Usage : .\restore_broken_files.ps1
# ============================================================

param(
    [switch]$DryRun  # affiche ce qu'il ferait sans rien modifier
)

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host "[FAIL] Python venv introuvable a $Python" -ForegroundColor Red
    exit 1
}

$LogFile = Join-Path $Root ("logs\restore_broken_files_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Log {
    param([string]$Msg, [string]$Color = 'White')
    Write-Host $Msg -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $Msg
}

Log "============================================================" Cyan
Log "  Restauration des fichiers Python tronqués" Cyan
Log "  Démarrage : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" Cyan
Log "  Mode : $(if ($DryRun) { 'DRY-RUN (aucune modification)' } else { 'NORMAL (modifie les fichiers)' })" Cyan
Log "  Log : $LogFile" Cyan
Log "============================================================" Cyan

# ============================================================
# ETAPE 1 : Détection des fichiers cassés
# ============================================================
Log ""
Log "[ETAPE 1] Détection des fichiers Python cassés..." Yellow

$DetectScript = @"
import os, ast
broken = []
for root, dirs, files in os.walk('.'):
    if any(x in root for x in ('_old','archives','.git','.venv','__pycache__')): continue
    for f in files:
        if not f.endswith('.py'): continue
        p = os.path.join(root, f).replace('\\', '/')
        if p.startswith('./'): p = p[2:]
        try:
            with open(p, encoding='utf-8') as fh: ast.parse(fh.read(), p)
        except Exception:
            broken.append(p)
for f in broken: print(f)
"@

$broken = & $Python -c $DetectScript
$brokenList = @($broken)
Log "  Trouvés : $($brokenList.Count) fichiers cassés" White

if ($brokenList.Count -eq 0) {
    Log "[OK] Aucun fichier cassé. Rien à restaurer." Green
    exit 0
}

# ============================================================
# ETAPE 2 : Pour chaque fichier cassé, trouver et restaurer
# ============================================================
Log ""
Log "[ETAPE 2] Recherche de versions saines dans Git..." Yellow

$restored = @()
$failed = @()
$counter = 0

foreach ($file in $brokenList) {
    $counter++
    $shortFile = if ($file.Length -gt 60) { "..." + $file.Substring($file.Length - 60) } else { $file }
    Write-Progress -Activity "Restauration" -Status $shortFile -PercentComplete (($counter / $brokenList.Count) * 100)

    # Récupérer les SHA candidats (top 10 commits sur toutes branches)
    $shas = & git log --all --pretty=format:'%H' -- $file 2>$null | Select-Object -First 10

    if (-not $shas) {
        $failed += @{ File = $file; Reason = 'jamais commité dans Git' }
        Log "  [FAIL] $shortFile -> jamais commité" Red
        continue
    }

    # Pour chaque SHA, tester si la version compile
    $bestSha = $null
    $bestSize = 0
    foreach ($sha in $shas) {
        try {
            $content = & git show "${sha}:${file}" 2>$null
            if (-not $content) { continue }
            # Test compile via Python
            $tempFile = [System.IO.Path]::GetTempFileName() + ".py"
            $content | Out-File -FilePath $tempFile -Encoding utf8 -NoNewline
            $compileResult = & $Python -m py_compile $tempFile 2>&1
            $compileOk = ($LASTEXITCODE -eq 0)
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            if ($compileOk) {
                $size = ($content | Measure-Object -Line).Lines
                if ($size -gt $bestSize) {
                    $bestSize = $size
                    $bestSha = $sha
                }
                # Si on trouve une bonne version, on prend la plus récente (1ère trouvée)
                break
            }
        } catch {}
    }

    if ($bestSha) {
        $shortSha = $bestSha.Substring(0, 7)
        if ($DryRun) {
            Log "  [DRY-RUN] $shortFile <- $shortSha ($bestSize lines)" DarkGray
        } else {
            & git checkout $bestSha -- $file 2>$null
            if ($LASTEXITCODE -eq 0) {
                # Vérifier que le fichier compile maintenant
                $verify = & $Python -m py_compile $file 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Log "  [OK] $shortFile <- $shortSha ($bestSize lines)" Green
                    $restored += @{ File = $file; Sha = $shortSha; Lines = $bestSize }
                } else {
                    Log "  [WARN] $shortFile checkout fait mais ne compile pas: $verify" Yellow
                    $failed += @{ File = $file; Reason = "checkout OK mais compile KO" }
                }
            } else {
                Log "  [FAIL] $shortFile checkout impossible" Red
                $failed += @{ File = $file; Reason = 'git checkout failed' }
            }
        }
    } else {
        Log "  [FAIL] $shortFile -> aucune version git compile" Red
        $failed += @{ File = $file; Reason = 'aucune version git compile' }
    }
}

Write-Progress -Activity "Restauration" -Completed

# ============================================================
# ETAPE 3 : Bilan
# ============================================================
Log ""
Log "============================================================" Cyan
Log "  BILAN" Cyan
Log "============================================================" Cyan
Log "  Fichiers cassés au départ : $($brokenList.Count)" White
Log "  Restaurés avec succès     : $($restored.Count)" Green
Log "  Échecs (perdus)           : $($failed.Count)" Red
Log ""

if ($failed.Count -gt 0) {
    Log "=== Fichiers irrécupérables ===" Yellow
    foreach ($f in $failed) {
        Log "  $($f.File) - $($f.Reason)" Yellow
    }
    Log ""
    Log "Ces fichiers sont à recréer manuellement, ou supprimer s'ils ne servent plus." Yellow
}

# Re-vérification finale
Log ""
Log "[ETAPE 4] Re-vérification après restauration..." Yellow
$finalBroken = & $Python -c $DetectScript
$finalCount = @($finalBroken).Count
if ($finalCount -eq 0) {
    Log "[SUCCES] Tous les fichiers Python compilent !" Green
} else {
    Log "[INFO] Reste $finalCount fichiers cassés (= les irrécupérables)" Yellow
}

Log ""
Log "Log complet : $LogFile"
Log "Date fin : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
exit 0
