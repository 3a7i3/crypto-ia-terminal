# Tests & Validation (global)
```powershell
cd <repo_root>
python run_all_tests.py
# Consultez le rapport généré : all_tests_report.md
# Consultez l’audit complet : RAPPORT_FINAL_AUDIT.md
```
# Dashboard Usage Templates

Below are ready-to-copy usage templates for each major dashboard in the crypto quant trading system. Replace `<repo_root>` with your actual repository root if needed.

---

## Quant Dashboard (Panel)
```powershell
cd <repo_root>\crypto_quant_v16
panel serve ui\quant_dashboard.py --port 5011 --show
```
![Quant Dashboard](../screenshots/quant_v16_panel.png)

## Alert Dashboard (Panel)
```powershell
cd <repo_root>
launch_alert_dashboard.bat
```
![Supervision & Auto-Heal](../screenshots/supervision_autoheal.png)

## BotDoctor Dashboard (Panel)
```powershell
cd <repo_root>
launch_botdoctor_dashboard.bat
```
![BotDoctor Dashboard](../screenshots/botdoctor_dashboard.png)

## Evolution Dashboard (Panel)
```powershell
cd <repo_root>
launch_evolution_dashboard.bat
```
![Evolution Multi-Monde](../screenshots/evolution_multimonde.png)

## 3D Evolution View (Panel)
```powershell
cd <repo_root>
launch_evolution_3d_view.bat
```
![3D Evolution Viewer](../screenshots/evolution_3d_viewer.png)

## Feedback Dashboard (Panel)
```powershell
cd <repo_root>
launch_feedback_dashboard.bat
```
![Feedback Dashboard](../screenshots/feedback_dashboard.png)

## Quant Terminal (Streamlit)
```powershell
cd <repo_root>
launch_quant_terminal_v12.bat
```
![Quant Terminal V12](../screenshots/quant_terminal_v12.png)

---

## General Tips

## Navigation et UI/UX (2026)

Tous les dashboards disposent d’une sidebar interactive, d’un bouton retour, et d’une structure homogène (titre, aide, actions, exports, navigation). Les actions principales sont accessibles via des boutons standardisés avec icônes.

---

## Adding a New Dashboard
1. Create your dashboard script in the appropriate folder
2. Add a `.bat` launcher (see existing examples)
3. Update the navigation menu logic to include your new dashboard
4. Add a usage template here and in the main README

---
