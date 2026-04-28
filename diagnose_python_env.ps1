# diagnose_python_env.ps1
# Diagnostic automatique de l'environnement Python et .venv pour crypto_ai_terminal

Write-Host "[INFO] Diagnostic de l'environnement Python..."

# 1. Vérifier la présence de python.exe dans .venv
$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "[OK] .venv\Scripts\python.exe trouvé."
    & $venvPython --version
} else {
    Write-Host "[ERREUR] .venv\Scripts\python.exe introuvable. Recréez l'environnement avec install_all.ps1."
}

# 2. Vérifier la version de Python globale
python --version

# 3. Vérifier le PATH
Write-Host "[INFO] PATH actuel :"
$env:PATH -split ';' | ForEach-Object { Write-Host $_ }

# 4. Vérifier l'activation de .venv

Write-Host "[INFO] Test import des modules critiques dans .venv..."
if (Test-Path $venvPython) {
    $mods = @('plotly', 'dotenv', 'selenium')
    foreach ($m in $mods) {
        $result = & $venvPython -c "try:\n import $m\n print('$m OK')\nexcept ImportError:\n print('$m MISSING')" 2>&1
        Write-Host $result
        if ($result -like '*MISSING*') {
            Write-Host "[AIDE] Exécutez install_all.ps1 pour installer les dépendances manquantes."
        }
    }
} else {
    Write-Host "[WARN] Impossible de tester les modules sans .venv."
    Write-Host "[AIDE] Exécutez install_all.ps1 pour créer l'environnement virtuel."
}

# 5. Conseils
Write-Host "[INFO] Si des erreurs persistent :"
Write-Host "- Vérifiez que .venv est bien activé (./.venv/Scripts/Activate.ps1)"
Write-Host "- Vérifiez que python.exe pointe sur .venv (where python)"
Write-Host "- Réinstallez les dépendances avec install_all.ps1"
Write-Host "- Si besoin, redémarrez VS Code ou le terminal."
