# Cybertechnique — Setup overlay visuel (Custom CSS and JS Loader)
# Lance ce script UNE FOIS pour configurer le watermark dans VS Code.

Write-Host ""
Write-Host "=== CYBERTECHNIQUE OVERLAY SETUP ===" -ForegroundColor Cyan
Write-Host ""

# 1. Installer Custom CSS and JS Loader
Write-Host "[1/3] Installation Custom CSS and JS Loader..." -ForegroundColor Yellow
code --install-extension be5invis.vscode-custom-css
if ($LASTEXITCODE -eq 0) {
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "      Echec ou deja installe (normal)" -ForegroundColor Gray
}

# 2. Reinstaller notre extension (v1.2 avec temp file)
Write-Host "[2/3] Reinstallation extension Cybertechnique v1.2..." -ForegroundColor Yellow
& "$PSScriptRoot\install.ps1"

# 3. Injecter les chemins dans les settings utilisateur VS Code
Write-Host "[3/3] Configuration vscode_custom_css.imports..." -ForegroundColor Yellow

$settingsPath = "$env:APPDATA\Code\User\settings.json"

if (-not (Test-Path $settingsPath)) {
    Write-Host "      settings.json introuvable: $settingsPath" -ForegroundColor Red
    Write-Host "      Ajoute manuellement dans tes settings VS Code (Ctrl+,):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host '      "vscode_custom_css.imports": [' -ForegroundColor White
    Write-Host "          `"file:///C:/Users/WINDOWS/crypto_ai_terminal/.vscode/cybertechnique/themes/overlay.js`"," -ForegroundColor White
    Write-Host "          `"file:///C:/Users/WINDOWS/crypto_ai_terminal/.vscode/cybertechnique/themes/overlay.css`"" -ForegroundColor White
    Write-Host '      ]' -ForegroundColor White
    exit 1
}

try {
    $raw      = Get-Content $settingsPath -Raw -Encoding UTF8
    $settings = $raw | ConvertFrom-Json -AsHashtable

    $jsPath  = "file:///C:/Users/WINDOWS/crypto_ai_terminal/.vscode/cybertechnique/themes/overlay.js"
    $cssPath = "file:///C:/Users/WINDOWS/crypto_ai_terminal/.vscode/cybertechnique/themes/overlay.css"

    if (-not $settings.ContainsKey('vscode_custom_css.imports')) {
        $settings['vscode_custom_css.imports'] = @()
    }

    $imports = [System.Collections.Generic.List[string]]($settings['vscode_custom_css.imports'])
    if ($imports -notcontains $jsPath)  { $imports.Add($jsPath) }
    if ($imports -notcontains $cssPath) { $imports.Add($cssPath) }
    $settings['vscode_custom_css.imports'] = $imports.ToArray()

    $settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath -Encoding UTF8
    Write-Host "      OK - settings.json mis a jour" -ForegroundColor Green
} catch {
    Write-Host "      Erreur lecture settings.json: $_" -ForegroundColor Red
    Write-Host "      Ajoute manuellement la cle vscode_custom_css.imports" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== ETAPES FINALES ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Redemarrer VS Code" -ForegroundColor White
Write-Host "  2. Ctrl+Shift+P -> 'Enable Custom CSS and JS'" -ForegroundColor White
Write-Host "  3. Cliquer 'Restart' quand VS Code le demande" -ForegroundColor White
Write-Host ""
Write-Host "Le watermark apparaitra 5 secondes apres le demarrage." -ForegroundColor Gray
Write-Host ""
