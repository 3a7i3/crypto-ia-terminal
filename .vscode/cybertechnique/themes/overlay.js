// Cybertechnique Certification Layer — DOM Watermark Overlay
// Injecté par "Custom CSS and JS Loader" dans le renderer VS Code.
// Lit le niveau courant depuis un fichier temp écrit par l'extension.

(function () {
    'use strict';

    const path = require('path');
    const fs   = require('fs');
    const os   = require('os');

    const TEMP_FILE = path.join(
        process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'),
        'cybertechnique',
        'current_level.json'
    );

    const LEVELS = {
        NUCLEAR:   { text: 'NUCLEAR',   color: 'rgba(255, 0,   50,  0.042)', size: '92px' },
        IMMUTABLE: { text: 'IMMUTABLE', color: 'rgba(210, 90,  0,   0.038)', size: '78px' },
        LIVE_CORE: { text: 'LIVE CORE', color: 'rgba(0,   170, 190, 0.036)', size: '82px' },
        CRITICAL:  { text: 'CRITICAL',  color: 'rgba(210, 55,  0,   0.036)', size: '88px' },
        SEALED:    { text: 'SEALED',    color: 'rgba(130, 60,  170, 0.036)', size: '92px' },
        CERTIFIED: { text: 'CERTIFIED', color: 'rgba(28,  150, 70,  0.032)', size: '78px' },
    };

    let lastLevel = undefined;

    function readLevel() {
        try {
            return JSON.parse(fs.readFileSync(TEMP_FILE, 'utf8')).level || null;
        } catch (_) {
            return null;
        }
    }

    function removeWatermarks() {
        document.querySelectorAll('.cybertech-watermark').forEach(el => el.remove());
    }

    function getOverflowGuard() {
        const focused = document.querySelector('.monaco-editor.focused .overflow-guard');
        return focused || document.querySelector('.editor-instance .monaco-editor .overflow-guard');
    }

    function injectWatermark(overflowGuard, level) {
        removeWatermarks();
        const cfg = LEVELS[level];
        if (!cfg) return;

        const div = document.createElement('div');
        div.className = 'cybertech-watermark';

        Object.assign(div.style, {
            position:      'absolute',
            top:           '50%',
            left:          '50%',
            transform:     'translate(-50%, -50%) rotate(-8deg)',
            fontSize:      cfg.size,
            fontWeight:    '900',
            fontFamily:    '"Courier New", Consolas, monospace',
            color:         cfg.color,
            letterSpacing: '10px',
            whiteSpace:    'nowrap',
            pointerEvents: 'none',
            userSelect:    'none',
            zIndex:        '9999',
            lineHeight:    '1',
        });

        div.textContent = cfg.text;
        overflowGuard.appendChild(div);
    }

    function update() {
        const level = readLevel();
        if (level === lastLevel) return;
        lastLevel = level;

        const overflow = getOverflowGuard();
        if (!overflow) return;

        if (!level) {
            removeWatermarks();
        } else {
            injectWatermark(overflow, level);
        }
    }

    // Démarre après chargement complet de VS Code
    setTimeout(function poll() {
        update();
        setTimeout(poll, 400);
    }, 5000);

})();
