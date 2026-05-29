import os
import sys


def main():
    # Génère un rapport de couverture HTML pour le dossier supervision/
    print("[INFO] Génération du rapport de couverture de tests (HTML)...")
    rc = os.system("pytest --cov=supervision --cov-report=html")
    if rc == 0:
        print(
            "[OK] Rapport HTML généré dans le dossier htmlcov/ (ouvrir htmlcov/index.html)"
        )
    else:
        print("[ERREUR] La génération du rapport de couverture a échoué.")
        sys.exit(1)


if __name__ == "__main__":
    main()
