# ❓ FAQ – Evolutionary Ecosystem & Dashboard

**Q: I have no data in the dashboard?**
- A: Rerun `python orchestrate_ecosystem.py` to generate the required files.

**Q: I get a Streamlit or Optuna error?**
- A: Make sure all packages are installed in the venv:
  ```powershell
  pip install -r requirements.txt
  ```

**Q: Port 8501 is already in use?**
- A: Add `--server.port 8502` to the Streamlit command.

**Q: How do I export results?**
- A: Use the export buttons in the dashboard (CSV, JSON, Optuna).

**Q: How do I optimize other parameters?**
- A: Select them in the advanced AutoML section of the 3D dashboard.

**Q: Where are the archives?**
- A: All results are copied to the `archives/` folder at each run.

**Q: Can I use these data in Excel or Python?**
- A: Yes, all exports are compatible (CSV, JSON).


**Q: How do I get personalized help?**
- A: See the documentation, FAQ, or open an issue. For any question or information, contact: ia.strategy.support@gmail.com

---
