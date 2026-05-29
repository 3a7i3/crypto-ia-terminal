import importlib
import json
import logging
import os
import shutil
import sys
from datetime import datetime

# Ce script lance plusieurs runs de run_strategy_factory.py avec des paramètres différents
# Usage : python run_strategy_factory_batch.py batch_configs.json

BATCH_CONFIGS_FILE = sys.argv[1] if len(sys.argv) > 1 else "batch_configs.json"

with open(BATCH_CONFIGS_FILE, "r", encoding="utf-8") as f:
    batch_configs = json.load(f)

for idx, config in enumerate(batch_configs):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = f"results/batch_run_{idx+1}_{timestamp}"
    os.makedirs(batch_dir, exist_ok=True)
    log_file = os.path.join(batch_dir, "batch_run.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    try:
        logging.info(f"[Batch {idx+1}] Lancement avec config : {config}")
        # Écrire la config dans strategy_factory_config.ini
        with open("strategy_factory_config.ini", "w", encoding="utf-8") as fconf:
            fconf.write("[simulation]\n")
            fconf.write(f"pop_size = {config.get('pop_size', 100)}\n")
            fconf.write(f"n_gen = {config.get('n_gen', 100)}\n")
            fconf.write(f"migration_freq = {config.get('migration_freq', 5)}\n")
            fconf.write(f"migration_rate = {config.get('migration_rate', 0.1)}\n")
            fconf.write("\n[visualization]\n")
            fconf.write(f"show_plots = {config.get('show_plots', 'False')}\n")
        # Lancer la simulation principale
        ret = os.system(
            f"python run_strategy_factory.py > {os.path.join(batch_dir, 'run_stdout.log')} 2> {os.path.join(batch_dir, 'run_stderr.log')}"
        )
        if ret != 0:
            logging.error(
                f"[Batch {idx+1}] Erreur lors de l'exécution de run_strategy_factory.py (code {ret})"
            )
        # Archiver les résultats
        for file in os.listdir("results"):
            if file.endswith(".csv") or file.endswith(".json") or file.endswith(".png"):
                shutil.move(
                    os.path.join("results", file), os.path.join(batch_dir, file)
                )
        logging.info(f"[Batch {idx+1}] Résultats archivés dans {batch_dir}")
        # Générer le rapport HTML automatiquement
        ret_html = os.system(f"python generate_html_report.py {batch_dir}")
        if ret_html != 0:
            logging.error(
                f"[Batch {idx+1}] Erreur lors de la génération du rapport HTML (code {ret_html})"
            )
        else:
            logging.info(
                f"[Batch {idx+1}] Rapport HTML généré dans {batch_dir}/rapport_simulation.html"
            )
        # Notification email automatique si variables d'environnement définies
        to_email = os.environ.get("BATCH_NOTIFY_EMAIL")
        smtp_user = os.environ.get("BATCH_NOTIFY_SMTP_USER")
        smtp_pass = os.environ.get("BATCH_NOTIFY_SMTP_PASS")
        provider = os.environ.get("BATCH_NOTIFY_PROVIDER")
        smtp_server = os.environ.get("BATCH_NOTIFY_SMTP_SERVER")
        smtp_port = os.environ.get("BATCH_NOTIFY_SMTP_PORT")
        if all([to_email, smtp_user, smtp_pass, provider]):
            notif_cmd = f"python send_orchestration_notification.py {batch_dir} {to_email} {smtp_user} {smtp_pass} {provider}"
            if smtp_server:
                notif_cmd += f" {smtp_server}"
            if smtp_port:
                notif_cmd += f" {smtp_port}"
            notif_ret = os.system(notif_cmd)
            if notif_ret != 0:
                logging.error(
                    f"[Batch {idx+1}] Erreur lors de l'envoi de la notification email (code {notif_ret})"
                )
        else:
            logging.info(
                "[Batch] Notification email non envoyée (variables d'environnement manquantes)"
            )
    except Exception as e:
        logging.exception(f"[Batch {idx+1}] Exception inattendue : {e}")
print("\n[Batch] Toutes les simulations sont terminées.")
