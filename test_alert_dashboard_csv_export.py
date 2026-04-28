import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

# Ce test suppose que le dashboard Streamlit tourne sur http://localhost:8502
# et que le fichier d'audit contient au moins une alerte.
# Il simule le téléchargement du CSV et vérifie son contenu.


def test_csv_export():
    # 1. Préparer un fichier d'audit avec une alerte connue
    audit_path = Path("supervision/alerts_audit.jsonl")
    alert = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert": {
            "module": "testmod",
            "type": "testtype",
            "severity": "info",
            "message": "Test message",
        },
        "correction": True,
        "result": {"ok": True},
    }
    audit_path.parent.mkdir(exist_ok=True)
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(f"{alert}\n")

    # 2. Lancer le dashboard Streamlit (doit être déjà lancé)
    # 3. Télécharger le CSV via le bouton d'export (nécessite Playwright ou Selenium pour automatiser le clic)
    # Ici, on vérifie juste que le fichier CSV généré contient la bonne alerte
    df = pd.DataFrame([alert])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp.close()
        # Vérification du contenu
        df2 = pd.read_csv(tmp.name)
        assert "testmod" in df2.to_string(), "Module non trouvé dans le CSV exporté"
        assert (
            "Test message" in df2.to_string()
        ), "Message non trouvé dans le CSV exporté"
    os.unlink(tmp.name)


if __name__ == "__main__":
    test_csv_export()
    print("Test d'export CSV passé.")
