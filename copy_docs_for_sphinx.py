# Copie automatique des fichiers Markdown pour Sphinx
import os
import shutil

DOCS = "docs"
ROOT = "."
FILES = [
    "README.md",
    "DOCUMENTATION_AUTOMATIQUE.md",
    "QUICK_START_V91.md",
    "DEMARRAGE_RAPIDE_FR.md",
    "DOCUMENTATION_INDEX.md",
    "CONFIG_REFERENCE_V91.md",
    "VALIDATION_CHECKLIST.md",
    "PROJECT_COMPLETION_SUMMARY.md",
    "ROADMAP_V9_V10_V11.md",
]

for fname in FILES:
    src = os.path.join(ROOT, fname)
    dst = os.path.join(DOCS, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        print(f"Copié: {src} -> {dst}")
    else:
        print(f"Non trouvé: {src}")
