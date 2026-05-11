"""
Script d'automatisation complet pour pipeline d'analyse évolutive.
Lance les simulations, génère les rapports, exécute les analyses avancées, envoie une notification et exporte les résultats.
"""

import os
import shutil
import subprocess
import sys
from ftplib import FTP

import automl_tuning
import clustering
import export_latex_md
import pareto_front
import sensitivity_analysis
import timeline_animation

# 1. Lancer les simulations (adapter le script si besoin)
print("[AUTO] Lancement des simulations...")
subprocess.run([sys.executable, "run_multi_simulations.py"])  # Génère sim_summaries/

# 2. Générer les rapports principaux
print("[AUTO] Génération du rapport PDF...")
subprocess.run([sys.executable, "generate_report.py"])
print("[AUTO] Génération du rapport HTML...")
subprocess.run([sys.executable, "generate_html_report.py"])
print("[AUTO] Génération du rapport Excel...")
subprocess.run([sys.executable, "export_excel_report.py"])

# 3. Analyses avancées
print("[AUTO] Analyse de sensibilité...")
sensitivity_analysis.plot_sensitivity(
    sim_csv_dir="sim_summaries", output_file="sensitivity_plot.png"
)
print("[AUTO] Front de Pareto...")
pareto_front.plot_pareto(sim_csv_dir="sim_summaries", output_file="pareto_front.png")
print("[AUTO] Clustering...")
clustering.plot_clustering(
    sim_csv_dir="sim_summaries", output_file="clustering_plot.png"
)
print("[AUTO] Animation timeline...")
timeline_animation.animate_evolution(
    sim_csv_dir="sim_summaries", output_file="timeline_animation.mp4"
)
print("[AUTO] AutoML grid search...")
automl_tuning.automl_grid_search(
    sim_csv_dir="sim_summaries", output_file="automl_results.csv"
)
print("[AUTO] Export LaTeX/Markdown...")
export_latex_md.export_latex_md(
    sim_csv_dir="sim_summaries", latex_file="results.tex", md_file="results.md"
)

# 4. Notification email (adapter les paramètres)
try:
    import notifications

    notifications.send_email(
        subject="Simulation Evolution terminée",
        body="Tous les rapports et analyses avancées sont prêts.",
        to_email="destinataire@mail.com",
        smtp_server="smtp.server.com",
        smtp_port=465,
        smtp_user="user",
        smtp_pass="password",
    )
    print("[AUTO] Notification email envoyée.")
except Exception as e:
    print(f"[AUTO] Notification email échouée : {e}")

# 5. Export cloud local (adapter le chemin)
cloud_dir = "C:/Users/WINDOWS/OneDrive/SimuExports"
os.makedirs(cloud_dir, exist_ok=True)
for f in [
    "rapport_simulations.pdf",
    "rapport_simulation.html",
    "rapport_simulations.xlsx",
    "sensitivity_plot.png",
    "pareto_front.png",
    "clustering_plot.png",
    "timeline_animation.mp4",
    "automl_results.csv",
    "results.tex",
    "results.md",
]:
    if os.path.exists(f):
        shutil.copy(f, os.path.join(cloud_dir, f))
        print(f"[AUTO] Exporté dans {cloud_dir} : {f}")

# 6. Export cloud distant (S3, Dropbox, Azure, Google Drive, FTP)
try:
    # S3
    import boto3

    s3_bucket = "mon-bucket-simu"  # À personnaliser
    aws_access_key = "AWS_ACCESS_KEY"  # À personnaliser
    aws_secret_key = "AWS_SECRET_KEY"  # À personnaliser
    session = boto3.Session(
        aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key
    )
    s3 = session.client("s3")
    for f in [
        "rapport_simulations.pdf",
        "rapport_simulation.html",
        "rapport_simulations.xlsx",
        "sensitivity_plot.png",
        "pareto_front.png",
        "clustering_plot.png",
        "timeline_animation.mp4",
        "automl_results.csv",
        "results.tex",
        "results.md",
    ]:
        if os.path.exists(f):
            s3.upload_file(f, s3_bucket, f)
            print(f"[AUTO] Exporté sur S3 : {f}")
except Exception as e:
    print(f"[AUTO] Export S3 échoué : {e}")

try:
    # Dropbox
    import dropbox

    dropbox_token = "DROPBOX_TOKEN"  # À personnaliser
    dbx = dropbox.Dropbox(dropbox_token)
    for f in [
        "rapport_simulations.pdf",
        "rapport_simulation.html",
        "rapport_simulations.xlsx",
        "sensitivity_plot.png",
        "pareto_front.png",
        "clustering_plot.png",
        "timeline_animation.mp4",
        "automl_results.csv",
        "results.tex",
        "results.md",
    ]:
        if os.path.exists(f):
            with open(f, "rb") as file_data:
                dbx.files_upload(
                    file_data.read(), f"/{f}", mode=dropbox.files.WriteMode.overwrite
                )
            print(f"[AUTO] Exporté sur Dropbox : {f}")
except Exception as e:
    print(f"[AUTO] Export Dropbox échoué : {e}")

try:
    # Azure Blob
    from azure.storage.blob import BlobServiceClient

    azure_conn_str = "AZURE_CONN_STR"  # À personnaliser
    azure_container = "simu-exports"
    blob_service_client = BlobServiceClient.from_connection_string(azure_conn_str)
    container_client = blob_service_client.get_container_client(azure_container)
    container_client.create_container()
    for f in [
        "rapport_simulations.pdf",
        "rapport_simulation.html",
        "rapport_simulations.xlsx",
        "sensitivity_plot.png",
        "pareto_front.png",
        "clustering_plot.png",
        "timeline_animation.mp4",
        "automl_results.csv",
        "results.tex",
        "results.md",
    ]:
        if os.path.exists(f):
            with open(f, "rb") as data:
                container_client.upload_blob(f, data, overwrite=True)
            print(f"[AUTO] Exporté sur Azure Blob : {f}")
except Exception as e:
    print(f"[AUTO] Export Azure Blob échoué : {e}")

try:
    # Google Drive
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive

    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)
    for f in [
        "rapport_simulations.pdf",
        "rapport_simulation.html",
        "rapport_simulations.xlsx",
        "sensitivity_plot.png",
        "pareto_front.png",
        "clustering_plot.png",
        "timeline_animation.mp4",
        "automl_results.csv",
        "results.tex",
        "results.md",
    ]:
        if os.path.exists(f):
            gfile = drive.CreateFile({"title": f})
            gfile.SetContentFile(f)
            gfile.Upload()
            print(f"[AUTO] Exporté sur Google Drive : {f}")
except Exception as e:
    print(f"[AUTO] Export Google Drive échoué : {e}")

try:
    # FTP
    ftp_host = "ftp.monsite.com"  # À personnaliser
    ftp_user = "user"  # À personnaliser
    ftp_pass = "password"  # À personnaliser
    ftp = FTP(ftp_host)
    ftp.login(ftp_user, ftp_pass)
    for f in [
        "rapport_simulations.pdf",
        "rapport_simulation.html",
        "rapport_simulations.xlsx",
        "sensitivity_plot.png",
        "pareto_front.png",
        "clustering_plot.png",
        "timeline_animation.mp4",
        "automl_results.csv",
        "results.tex",
        "results.md",
    ]:
        if os.path.exists(f):
            with open(f, "rb") as file_data:
                ftp.storbinary(f"STOR {f}", file_data)
            print(f"[AUTO] Exporté sur FTP : {f}")
    ftp.quit()
except Exception as e:
    print(f"[AUTO] Export FTP échoué : {e}")

print("[AUTO] Pipeline complet terminé.")
