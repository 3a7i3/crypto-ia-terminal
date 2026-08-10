# 🚀 Step-by-step Tutorial – Evolutionary Ecosystem & Dashboard

## 1. Run the evolutionary simulation
```powershell
python orchestrate_ecosystem.py
```
- Generates all required data (CSV, JSON, PNG, archives).

## 2. Open the interactive dashboard
```powershell
.\.venv\Scripts\streamlit run evolution_dashboard.py
```
- Explore worlds, fitness, diversity, survivors.
- Use filters to zoom in on a species, generation, or score.

## 3. Advanced 3D & AutoML visualization
```powershell
.\.venv\Scripts\streamlit run evolution_3d_view.py
```
- Visualize the population in 3D (TP, SL, fitness, species).
- Apply clustering, heatmaps, automatic scoring.
- Launch AutoML to optimize parameters (TP, SL, RSI, MA, etc.).
- Export results (CSV, JSON, Optuna).

## 4. Best practices
- Always rerun the simulation before exploring.
- Use exports for external analysis.
- Test different objectives and parameters in AutoML.

## 5. Quick troubleshooting
- **No data?** Rerun the simulation.
- **Streamlit/Optuna error?** Check packages (`pip install -r requirements.txt`).
- **Port in use?** Add `--server.port 8502` to the Streamlit command.

---

For any questions, see the FAQ or open an issue. You can also write to: ia.strategy.support@gmail.com
