import os

# Liste des panels et chemins associés
PANELS = [
    ("🛡️ Supervision & Auto-Heal", "dashboard/alert_dashboard.py"),
    ("🩺 BotDoctor Dashboard", "supervision/botdoctor_dashboard.py"),
    ("🌐 Evolution Multi-Monde", "evolution_dashboard.py"),
    ("🌐 3D Evolution Viewer", "evolution_3d_view.py"),
    ("📊 Quant V16 Panel", "crypto_quant_v16/ui/quant_dashboard.py"),
    ("📈 Quant Terminal V12", "quant_hedge_ai/dashboard/quant_terminal_v12.py"),
    ("🧠 R&D Feedback Dashboard", "ai_autonomous_loop/feedback_dashboard.py"),
]

print("--- Orchestration automatique des panels internes ---")
for label, path in PANELS:
    abs_path = os.path.abspath(path)
    print(f"[TEST] {label} → {abs_path}")
    # Test d'ouverture du fichier (simulateur d'intégration)
    if os.path.exists(abs_path):
        print(f"[OK] Fichier trouvé : {abs_path}")
    else:
        print(f"[ERREUR] Fichier introuvable : {abs_path}")
print("--- Orchestration terminée ---")
