// Cybertechnique Certification Layer — VS Code Extension v1.2.0
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const os = require('os');

let statusBarItem;
let decorationTypes = {};
let levels = {};
let modules = {};

const TEMP_FILE = path.join(
    process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'),
    'cybertechnique',
    'current_level.json'
);

function writeLevelTemp(levelName) {
    try {
        fs.mkdirSync(path.dirname(TEMP_FILE), { recursive: true });
        fs.writeFileSync(TEMP_FILE, JSON.stringify({ level: levelName || null }));
    } catch (e) {
        // silencieux
    }
}

function loadRegistry(workspacePath) {
    const p = path.join(workspacePath, '.vscode', 'cybertechnique', 'registry', 'module_levels.json');
    try {
        const registry = JSON.parse(fs.readFileSync(p, 'utf8'));
        levels = registry.levels || {};
        modules = {};
        for (const [mod, lvl] of Object.entries(registry.modules || {})) {
            modules[mod.replace(/\\/g, '/')] = lvl;
        }
        console.log(`[Cybertechnique] ${Object.keys(modules).length} modules chargés`);
    } catch (e) {
        console.error('[Cybertechnique] Erreur registre:', e.message);
    }
}

function getLevel(filePath, workspacePath) {
    const rel = path.relative(workspacePath, filePath).replace(/\\/g, '/');
    return modules[rel] || null;
}

function buildDecorationTypes() {
    for (const dt of Object.values(decorationTypes)) dt.dispose();
    decorationTypes = {};

    for (const [name, cfg] of Object.entries(levels)) {
        // Barre colorée dans le scrollbar
        decorationTypes[name + '_ruler'] = vscode.window.createTextEditorDecorationType({
            overviewRulerColor: cfg.rulerColor,
            overviewRulerLane: vscode.OverviewRulerLane.Right,
        });
        // Badge discret après la première ligne
        decorationTypes[name + '_badge'] = vscode.window.createTextEditorDecorationType({
            after: {
                contentText: `   ${cfg.label}`,
                color: cfg.accentColor + 'A0',
                margin: '0 0 0 24px',
                fontStyle: 'italic',
                fontWeight: '500',
            }
        });
    }
}

function applyDecorations(editor, levelName) {
    for (const dt of Object.values(decorationTypes)) {
        editor.setDecorations(dt, []);
    }
    if (!levelName || !levels[levelName]) return;

    const doc = editor.document;
    const lastLine = doc.lineAt(doc.lineCount - 1);

    editor.setDecorations(decorationTypes[levelName + '_ruler'], [
        new vscode.Range(0, 0, doc.lineCount - 1, lastLine.text.length)
    ]);
    editor.setDecorations(decorationTypes[levelName + '_badge'], [
        doc.lineAt(0).range
    ]);
}

function updateStatusBar(levelName) {
    if (!levelName || !levels[levelName]) {
        statusBarItem.hide();
        return;
    }
    const cfg = levels[levelName];
    statusBarItem.text = cfg.label;
    statusBarItem.backgroundColor =
        levelName === 'NUCLEAR'   ? new vscode.ThemeColor('statusBarItem.errorBackground') :
        levelName === 'IMMUTABLE' ? new vscode.ThemeColor('statusBarItem.warningBackground') :
        undefined;
    statusBarItem.color =
        levelName === 'LIVE_CORE'  ? '#00CCDD' :
        levelName === 'CERTIFIED'  ? '#27AE60' :
        levelName === 'SEALED'     ? '#A060CC' :
        levelName === 'CRITICAL'   ? '#FF5533' :
        undefined;
    statusBarItem.tooltip = `CYBERTECHNIQUE — ${levelName}  |  mutation: ${cfg.mutation_policy}`;
    statusBarItem.show();
}

function handleEditor(editor) {
    if (!editor || editor.document.uri.scheme !== 'file') {
        statusBarItem.hide();
        writeLevelTemp(null);
        return;
    }
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) return;

    const workspacePath = folders[0].uri.fsPath;
    const levelName = getLevel(editor.document.uri.fsPath, workspacePath);

    writeLevelTemp(levelName);   // communique le niveau à overlay.js
    applyDecorations(editor, levelName);
    updateStatusBar(levelName);

    if (levelName && levels[levelName]?.warn_on_open) {
        vscode.window.showWarningMessage(
            `CYBERTECHNIQUE — ${levels[levelName].warn_message}`,
            'Compris'
        );
    }
}

function activate(context) {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1000);
    context.subscriptions.push(statusBarItem);

    const folders = vscode.workspace.workspaceFolders;
    if (folders?.length > 0) loadRegistry(folders[0].uri.fsPath);
    buildDecorationTypes();

    const watcher = vscode.workspace.createFileSystemWatcher(
        '**/.vscode/cybertechnique/registry/module_levels.json'
    );
    watcher.onDidChange(() => {
        if (folders?.length > 0) loadRegistry(folders[0].uri.fsPath);
        buildDecorationTypes();
        if (vscode.window.activeTextEditor) handleEditor(vscode.window.activeTextEditor);
    });
    context.subscriptions.push(watcher);

    context.subscriptions.push(
        vscode.commands.registerCommand('cybertechnique.reloadRegistry', () => {
            if (folders?.length > 0) loadRegistry(folders[0].uri.fsPath);
            buildDecorationTypes();
            if (vscode.window.activeTextEditor) handleEditor(vscode.window.activeTextEditor);
            vscode.window.showInformationMessage('[Cybertechnique] Registre rechargé.');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('cybertechnique.showLevel', () => {
            if (!vscode.window.activeTextEditor) return;
            const wp = folders?.[0]?.uri?.fsPath || '';
            const lvl = getLevel(vscode.window.activeTextEditor.document.uri.fsPath, wp);
            const msg = lvl
                ? `${levels[lvl].label} — ${lvl} | mutation: ${levels[lvl].mutation_policy}`
                : 'NORMAL — aucune classification';
            vscode.window.showInformationMessage(`CYBERTECHNIQUE: ${msg}`);
        })
    );

    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(handleEditor)
    );

    handleEditor(vscode.window.activeTextEditor);
    console.log('[Cybertechnique] v1.2 activé.');
}

function deactivate() {
    for (const dt of Object.values(decorationTypes)) dt.dispose();
    writeLevelTemp(null);
}

module.exports = { activate, deactivate };
