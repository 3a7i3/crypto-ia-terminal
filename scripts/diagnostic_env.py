#!/usr/bin/env python3
"""
Diagnostic complet de l'environnement Python pour crypto-ai-terminal.
Vérifie : version Python, pip, modules requis, versions, permissions d'écriture, et configuration système de base.
Usage : python diagnostic_env.py
"""
import os
import platform
import subprocess
import sys
from pathlib import Path

import pkg_resources


def print_header(title):
    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)


def check_python_version():
    print_header("Version de Python")
    print(sys.version)
    if sys.version_info < (3, 10):
        print("[ERREUR] Python >= 3.10 requis.")
    else:
        print("[OK] Version compatible.")


def check_pip():
    print_header("Vérification de pip")
    try:
        import pip

        print(f"pip version: {pip.__version__}")
    except ImportError:
        print("[ERREUR] pip n'est pas installé.")


def check_requirements(requirements_file="requirements.txt"):
    print_header("Vérification des dépendances Python")
    if not os.path.exists(requirements_file):
        print(f"[WARN] Fichier {requirements_file} introuvable.")
        return
    with open(requirements_file) as f:
        required = [
            line.strip() for line in f if line.strip() and not line.startswith("#")
        ]
    installed = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
    for req in required:
        pkg_name = (
            req.split("==")[0].lower() if "==" in req else req.split(">=")[0].lower()
        )
        if pkg_name not in installed:
            print(f"[ERREUR] {pkg_name} non installé.")
        else:
            print(f"[OK] {pkg_name} {installed[pkg_name]}")


def check_write_permissions():
    print_header("Vérification des permissions d'écriture")
    test_file = Path("env_write_test.txt")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        test_file.unlink()
        print("[OK] Permissions d'écriture dans le dossier courant.")
    except Exception as e:
        print(f"[ERREUR] Impossible d'écrire dans le dossier courant : {e}")


def check_platform():
    print_header("Informations système")
    print(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"Machine: {platform.machine()} | Processeur: {platform.processor()}")
    print(f"Python: {platform.python_version()} | Exécutable: {sys.executable}")


def check_env_vars():
    print_header("Variables d'environnement clés")
    for var in ["PYTHONPATH", "PATH", "VIRTUAL_ENV"]:
        print(f"{var}: {os.environ.get(var, '[non défini]')}")


def check_git():
    print_header("Vérification de git")
    try:
        out = subprocess.check_output(["git", "--version"], stderr=subprocess.STDOUT)
        print(out.decode().strip())
    except Exception:
        print("[ERREUR] git n'est pas installé ou non accessible.")


def main():
    check_platform()
    check_python_version()
    check_pip()
    check_requirements()
    check_write_permissions()
    check_env_vars()
    check_git()
    print("\nDiagnostic terminé.")


if __name__ == "__main__":
    main()
