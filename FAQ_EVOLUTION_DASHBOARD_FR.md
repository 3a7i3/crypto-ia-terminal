# ❓ FAQ – Écosystème évolutif & Dashboard

**Q : Je n’ai pas de données dans le dashboard ?**
- R : Relancez `python orchestrate_ecosystem.py` pour générer les fichiers nécessaires.

**Q : J’ai une erreur Streamlit ou Optuna ?**
- R : Vérifiez que tous les packages sont installés dans le venv :
  ```powershell
  pip install -r requirements.txt
  ```

**Q : Le port 8501 est déjà utilisé ?**
- R : Ajoutez `--server.port 8502` à la commande Streamlit.

**Q : Comment exporter les résultats ?**
- R : Utilisez les boutons d’export dans le dashboard (CSV, JSON, Optuna).

**Q : Comment optimiser d’autres paramètres ?**
- R : Sélectionnez-les dans la section AutoML avancé du dashboard 3D.

**Q : Où trouver les archives ?**
- R : Tous les résultats sont copiés dans le dossier `archives/` à chaque run.

**Q : Peut-on utiliser ces données dans Excel ou Python ?**
- R : Oui, tous les exports sont compatibles (CSV, JSON).


**Q : Comment obtenir de l’aide personnalisée ?**
- R : Consultez la documentation, la FAQ, ou ouvrez une issue. Pour toute question ou information, contactez : ia.strategy.support@gmail.com

---
