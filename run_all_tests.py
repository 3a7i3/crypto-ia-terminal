import os
import shutil
import subprocess
import sys


def clean_pycache(root):
    """Supprime tous les dossiers __pycache__ et fichiers .pyc/.pyo sous root."""
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
        for f in filenames:
            if f.endswith(".pyc") or f.endswith(".pyo"):
                try:
                    os.remove(os.path.join(dirpath, f))
                except Exception:
                    pass


def run_pytest(test_dir, python_bin, env, report_lines):
    """Lance pytest sur test_dir, collecte stdout dans report_lines, retourne le returncode."""
    print(f"[INFO] Pytest sur {test_dir} ...")
    result = subprocess.run(
        [python_bin, "-m", "pytest", test_dir, "-v", "--tb=short"],
        capture_output=True,
        text=True,
        env=env,
    )
    print(result.stdout)
    report_lines.append(f"\n--- Résultats pour {test_dir} ---\n")
    report_lines.append(result.stdout)
    if result.returncode != 0:
        print(f"[ERREUR] Pytest a échoué pour {test_dir}")
    else:
        print(f"[OK] Pytest réussi pour {test_dir}")
    return result.returncode


def resolve_python(project_root):
    """
    Retourne le bon interpréteur Python :
      1. .venv Windows  (.venv/Scripts/python.exe)
      2. .venv Linux/Mac (.venv/bin/python)
      3. sys.executable  (fallback : Python courant)
    """
    candidates = [
        os.path.join(project_root, ".venv", "Scripts", "python.exe"),
        os.path.join(project_root, ".venv", "bin", "python"),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"[INFO] Environnement virtuel trouvé : {path}")
            return path

    print("[WARN] Aucun .venv trouvé — utilisation de l'interpréteur courant.")
    print(
        "[AIDE] Pour créer le venv : exécutez install_all.ps1 (Windows) ou install_all.sh (Linux/Mac)."
    )
    return sys.executable


def check_and_install_modules(python_bin, modules):
    """Vérifie et installe les modules manquants."""
    missing = []
    for mod in modules:
        code = f"try:\n import {mod}\nexcept ImportError:\n print('{mod}')"
        out = subprocess.run([python_bin, "-c", code], capture_output=True, text=True)
        if mod in out.stdout:
            missing.append(mod)

    if missing:
        print(f"[INFO] Installation automatique des modules manquants : {missing}")
        subprocess.run([python_bin, "-m", "pip", "install"] + missing, check=True)
    else:
        print("[OK] Tous les modules critiques sont présents.")


def main():
    """Orchestration complète des tests : nettoyage → modules → pytest → unittest → rapport → notification."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    report_lines = []
    global_rc = 0
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        project_root
        + os.pathsep
        + os.path.join(project_root, "quant-ai-system")
        + os.pathsep
        + os.path.join(project_root, "quant_hedge_ai")
    )

    python_bin = resolve_python(project_root)

    # ── Nettoyage des caches ─────────────────────────────────────────
    print("[INFO] Nettoyage des caches Python...")
    clean_pycache(project_root)

    # ── Modules critiques ────────────────────────────────────────────
    print("[INFO] Vérification des modules critiques...")
    check_and_install_modules(python_bin, ["plotly", "dotenv", "selenium"])

    # ── 1. Tests quant-ai-system/tests ───────────────────────────────
    quant_ai_tests = os.path.join(project_root, "quant-ai-system", "tests")
    if os.path.exists(quant_ai_tests):
        rc = run_pytest(quant_ai_tests, python_bin, env, report_lines)
        if rc != 0:
            global_rc = rc
    else:
        print(f"[WARN] Dossier introuvable : {quant_ai_tests}")

    # ── 2. Tests quant-ai-system/quant_ai_tests (dossier alternatif) ─
    quant_ai_system_dir = os.path.join(project_root, "quant-ai-system")
    quant_ai_tests_alt = os.path.join(quant_ai_system_dir, "quant_ai_tests")
    if os.path.exists(quant_ai_tests_alt):
        print("[INFO] Lancement des tests quant-ai-system/quant_ai_tests...")
        result = subprocess.run(
            [python_bin, "-m", "pytest", "quant_ai_tests", "-v", "--tb=short"],
            cwd=quant_ai_system_dir,
            capture_output=True,
            text=True,
            env=env,
        )
        print(result.stdout)
        report_lines.append("\n--- Résultats pour quant-ai-system/quant_ai_tests ---\n")
        report_lines.append(result.stdout)
        if result.returncode != 0:
            global_rc = result.returncode
    else:
        print("[WARN] Dossier quant-ai-system/quant_ai_tests introuvable — ignoré.")

    # ── 3. Tests quant_hedge_ai (V9.1) ───────────────────────────────
    v91_tests = os.path.join(project_root, "quant_hedge_ai", "tests")
    if os.path.exists(v91_tests):
        rc = run_pytest(v91_tests, python_bin, env, report_lines)
        if rc != 0:
            global_rc = rc
    else:
        print(
            "[WARN] Dossier quant_hedge_ai/tests introuvable — créez-le pour tester V9.1."
        )

    # ── 4. Tests racine globaux ──────────────────────────────────────
    root_tests = os.path.join(project_root, "tests")
    if os.path.exists(root_tests):
        rc = run_pytest(root_tests, python_bin, env, report_lines)
        if rc != 0:
            global_rc = rc
    else:
        print("[WARN] Dossier tests/ racine introuvable — ignoré.")

    # ── 5. Unittest discover (optionnel) ─────────────────────────────
    print("[INFO] Lancement unittest discover...")
    unittest_result = subprocess.run(
        [python_bin, "-m", "unittest", "discover"],
        capture_output=True,
        text=True,
        env=env,
    )
    print(unittest_result.stdout)
    report_lines.append("\n--- Résultats unittest discover ---\n")
    report_lines.append(unittest_result.stdout)
    if unittest_result.returncode != 0:
        print("[ERREUR] Unittest a échoué.")
        global_rc = unittest_result.returncode
    else:
        print("[OK] Unittest réussi.")

    # ── Rapport global ───────────────────────────────────────────────
    report_path = os.path.join(project_root, "all_tests_report.md")
    summary = f"\n\n---\n**Résultat global : {'SUCCÈS' if global_rc == 0 else 'ÉCHEC'}** (code {global_rc})\n"
    report_lines.append(summary)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"[INFO] Rapport écrit dans {report_path}")
    print(summary)

    # ── Notification automatique ─────────────────────────────────────
    try:
        notify_script = os.path.join(project_root, "notify_test_status.py")
        if os.path.exists(notify_script):
            print("[INFO] Notification automatique via notify_test_status.py ...")
            subprocess.run([python_bin, notify_script, str(global_rc)], check=False)
    except Exception as e:
        print(f"[WARN] Notification automatique échouée : {e}")

    sys.exit(global_rc)


if __name__ == "__main__":
    main()
