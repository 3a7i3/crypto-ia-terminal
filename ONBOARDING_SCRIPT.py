# =============================================
"""
Module ONBOARDING_SCRIPT.py
--------------------------
Dashboard Streamlit pour l'onboarding utilisateur et la collecte de feedback.

Fonctionnalités :
- Saisie et sauvegarde sécurisée du feedback utilisateur (CSV local)
- Envoi optionnel du feedback par email (SMTP)
- Statistiques et visualisation des retours
- Sécurité : validation anti-injection, contrôle strict des chemins, logs d'erreur

Exemple d'utilisation :
>>> feedback = {"timestamp": "2026-03-22T12:00:00", "user": "Alice", "note": 5, "comment": "Super!"}
>>> save_feedback_local(feedback)
"""
import csv
import datetime
import os
import pathlib
import random

import pandas as pd
# 📚 Documentation enrichie et guides d’utilisation
#
# Pour une prise en main rapide, une documentation professionnelle et des exemples d’utilisation prêts à copier, consultez :
#   - README_CONSOLIDATED.md — Guide d’installation, configuration, lancement rapide, FAQ, bonnes pratiques
#   - DASHBOARD_USAGE_TEMPLATES.md — Exemples d’utilisation pour chaque dashboard (Panel/Streamlit)
#   - ACTION_PLAN_CHECKLIST.md — Plan d’action détaillé pour finaliser et maintenir le système
#
# Conseil : Commencez par le README_CONSOLIDATED.md pour une vue d’ensemble, puis utilisez les templates et le plan d’action pour accélérer votre onboarding ou vos évolutions.
#
# ---
# English quick orientation:
# =============================================
# =============================================
import streamlit as st


# === Fonctions utilitaires ===
def save_feedback_local(feedback, csv_path="onboarding_feedback.csv", allow_temp=False):
    """
    Sauvegarde le feedback localement dans un fichier CSV sécurisé.

    Args:
        feedback (dict): Dictionnaire avec les clés 'timestamp', 'user', 'note', 'comment'.
        csv_path (str): Chemin du fichier CSV (par défaut onboarding_feedback.csv).
        allow_temp (bool): Usage test uniquement, autorise les chemins temporaires système.

    Sécurité :
        - Refuse tout chemin hors du dossier courant (ou /tmp pour les tests).
        - Refuse tout champ contenant une virgule ou un retour à la ligne (anti-injection CSV).
        - Logge toute erreur critique dans onboarding_feedback.log.

    Raises:
        ValueError: Si le chemin ou un champ est invalide.
        Exception: Si une erreur d'écriture survient.
    """
    import logging

    log_path = os.path.join(
        os.path.dirname(csv_path) or os.getcwd(), "onboarding_feedback.log"
    )
    logging.basicConfig(
        filename=log_path,
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        base_dir = os.path.abspath(os.getcwd())
        abs_path = os.path.abspath(csv_path)
        temp_dirs = [os.path.abspath(x) for x in [os.getenv("TEMP", "/tmp"), "/tmp"]]
        is_temp = any(abs_path.startswith(tmp) for tmp in temp_dirs)
        if not (abs_path.startswith(base_dir) or (allow_temp and is_temp)):
            raise ValueError("Chemin de fichier non autorisé.")

        # Validation anti-injection sur les champs feedback
        for k, v in feedback.items():
            if isinstance(v, str) and ("\n" in v or "\r" in v or "," in v):
                raise ValueError(f"Caractère interdit dans le champ {k}.")

        file_exists = os.path.isfile(csv_path)
        with open(csv_path, mode="a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(
                csvfile, fieldnames=["timestamp", "user", "note", "comment"]
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(feedback)
    except Exception as e:
        logging.error(f"Erreur critique lors de la sauvegarde du feedback: {e}")
        raise


def send_feedback_email(
    feedback, smtp_server, smtp_port, smtp_user, smtp_password, to_email
):
    """
    Envoie le feedback par email via SMTP.
    Args:
        feedback (dict): Dictionnaire feedback utilisateur.
        smtp_server (str): Adresse du serveur SMTP.
        smtp_port (int): Port SMTP.
        smtp_user (str): Identifiant SMTP.
        smtp_password (str): Mot de passe SMTP.
        to_email (str): Destinataire.
    Raises:
        Exception: Si l'envoi échoue.
    """
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(f"Feedback reçu :\n{feedback}")
    msg["Subject"] = "Nouveau feedback onboarding"
    msg["From"] = smtp_user
    msg["To"] = to_email
    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())


def sidebar_onboarding():
    """
    Affiche la barre latérale d'onboarding avec liens rapides.
    """
    st.sidebar.title("🚀 Menu d'onboarding")
    st.sidebar.markdown(
        """
    **Navigation rapide :**
    - [📖 Guide d'installation](README_CONSOLIDATED.md)
    - [🧩 Exemples d'usage](DASHBOARD_USAGE_TEMPLATES.md)
    - [✅ Plan d'action](ACTION_PLAN_CHECKLIST.md)
    """
    )


def tutoriel_onboarding():
    """
    Affiche le tutoriel d'onboarding utilisateur.
    """
    st.markdown(
        """
    ### Tutoriel d'onboarding
    1. **Lisez le guide d'installation** pour comprendre l'écosystème.
    2. **Lancez un dashboard d'exemple** (Panel ou Streamlit).
    3. **Testez une fonctionnalité clé** (filtrage, export, alertes).
    4. **Donnez votre feedback** ci-dessous pour améliorer l'expérience !
    5. Consultez la barre latérale pour accéder rapidement aux ressources.
    """
    )


def feedback_stats(csv_path="onboarding_feedback.csv"):
    """
    Affiche les statistiques de feedback à partir du CSV local.
    Args:
        csv_path (str): Chemin du fichier CSV de feedback.
    """
    if not os.path.isfile(csv_path):
        st.info("Aucun feedback enregistré pour l'instant.")
        return
    df = pd.read_csv(csv_path)
    st.write("**Statistiques de feedback :**")
    st.bar_chart(df["note"].value_counts().sort_index())
    st.write(df.tail(5))


# === Bloc principal Streamlit ===
def main():
    """
    Point d'entrée principal du dashboard Streamlit d'onboarding.
    """
    st.set_page_config(page_title="Onboarding & Feedback", layout="centered")
    sidebar_onboarding()
    st.title("👋 Bienvenue dans l'onboarding utilisateur")
    tutoriel_onboarding()

    st.markdown("---")
    st.header("📝 Donnez votre feedback !")
    user = st.text_input("Votre nom ou pseudo (optionnel)")
    note = st.slider(
        "Note d'expérience",
        1,
        5,
        3,
        help="1 = Mauvaise expérience, 5 = Excellente expérience",
    )
    comment = st.text_area(
        "Commentaire ou suggestion",
        "",
        help="Soyez précis pour nous aider à nous améliorer.",
    )
    send_email = st.checkbox("Envoyer aussi ce feedback par email (optionnel)")

    if st.button("Envoyer le feedback"):
        feedback = {
            "timestamp": datetime.datetime.now().isoformat(),
            "user": user,
            "note": note,
            "comment": comment,
        }
        try:
            save_feedback_local(feedback)
            st.success(
                "✅ Merci pour votre feedback ! Il sera utilisé pour améliorer l'onboarding."
            )
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde du feedback : {e}")
        if send_email:
            with st.expander("Paramètres email avancés"):
                smtp_server = st.text_input("SMTP server", "smtp.example.com")
                smtp_port = st.number_input("SMTP port", 465)
                smtp_user = st.text_input("SMTP user")
                smtp_password = st.text_input("SMTP password", type="password")
                to_email = st.text_input("Destinataire", "admin@example.com")
                if st.button("Confirmer l'envoi email"):
                    try:
                        send_feedback_email(
                            feedback,
                            smtp_server,
                            int(smtp_port),
                            smtp_user,
                            smtp_password,
                            to_email,
                        )
                        st.success("📧 Feedback envoyé par email !")
                    except Exception as e:
                        st.error(f"Erreur d'envoi email : {e}")

    st.markdown("---")
    feedback_stats()


if __name__ == "__main__":
    main()
