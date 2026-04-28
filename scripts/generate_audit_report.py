import datetime
import os
import re
from pathlib import Path

# Patterns for dashboard frameworks (étendu)
FRAMEWORKS = {
    "Streamlit": [r"import streamlit"],
    "Panel": [r"import panel", r"panel\.serve"],
    "Dash": [r"import dash"],
    "FastAPI": [r"import fastapi"],
    "Gradio": [r"import gradio", r"gr.Interface"],
    "Voila": [r"voila\.app"],
    "Flask": [r"import flask", r"Flask\("],
    "Jupyter": [r"get_ipython\(\)", r"IPython"],
}

DEFAULT_PORTS = {
    "Streamlit": "8501",
    "Panel": "5010",
    "Dash": "8050",
    "FastAPI": "8080",
    "Gradio": "7860",
    "Voila": "8866",
    "Flask": "5000",
    "Jupyter": "8888",
}


root = Path(__file__).parent.parent
py_files = list(root.rglob("*.py"))


# --- Notification helpers ---
def notify_change(message, summary=None):
    # Personnalisation du préfixe de notification
    prefix = os.environ.get("DASHBOARD_AUDIT_NOTIFY_PREFIX", "")
    if prefix:
        message = f"{prefix} {message}"
    if summary:
        message = f"{message}\nRésumé : {summary}"
    # Log notification
    log_path = root / "DASHBOARDS_AUDIT_NOTIFICATIONS.log"
    with open(log_path, "a", encoding="utf-8") as logf:
        logf.write(
            f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}\n"
        )
    # Slack notification (if webhook configured)
    slack_webhook = os.environ.get("DASHBOARD_AUDIT_SLACK_WEBHOOK")
    if slack_webhook:
        try:
            import requests

            requests.post(slack_webhook, json={"text": message})
        except Exception as e:
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(f"[ERROR] Slack notification failed: {e}\n")


def is_excluded_from_tests(content):
    return (
        "pytest.skip" in content
        or 'if __name__ != "__main__" and ("pytest" in sys.modules' in content
    )


def has_launch_script(pyfile):
    script_name = f"launch_{pyfile.stem}.bat"
    script_path = root / script_name
    if script_path.exists():
        return script_name
    # Try to find a .bat with similar name
    for bat in root.glob("launch_*.bat"):
        if pyfile.stem in bat.stem:
            return bat.name
    return ""


def has_doc_entry(rel_path):
    readme = root / "DASHBOARDS_README.md"
    if not readme.exists():
        return False
    content = readme.read_text(encoding="utf-8", errors="ignore")
    return str(rel_path) in content


entries = []
for pyfile in py_files:
    rel_path = pyfile.relative_to(root)
    content = pyfile.read_text(encoding="utf-8", errors="ignore")
    for fw, patterns in FRAMEWORKS.items():
        if any(re.search(p, content) for p in patterns):
            script = has_launch_script(pyfile)
            port = DEFAULT_PORTS.get(fw, "")
            desc = ""
            docstring = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if docstring:
                desc = docstring.group(1).split("\n")[0].strip()
            elif "#" in content:
                desc = content.split("#")[1].split("\n")[0].strip()
            excluded = is_excluded_from_tests(content)
            doc = has_doc_entry(rel_path)
            entries.append(
                {
                    "file": str(rel_path),
                    "framework": fw,
                    "launch_script": script,
                    "port": port,
                    "desc": desc,
                    "excluded": excluded,
                    "doc": doc,
                }
            )
            break

# Audit report
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
report = f"""# Rapport d'audit des Dashboards/Applications\n\nDernière génération : {now}\n\n| Fichier | Framework | Script de lancement | Port | Exclu des tests | Documenté | Description |\n|---------|-----------|---------------------|------|-----------------|------------|-------------|\n"""
for e in entries:
    report += f"| {e['file']} | {e['framework']} | {e['launch_script']} | {e['port']} | {'✅' if e['excluded'] else '❌'} | {'✅' if e['doc'] else '❌'} | {e['desc']} |\n"


# --- Detect changes ---
audit_path = root / "DASHBOARDS_AUDIT_REPORT.md"
old_report = audit_path.read_text(encoding="utf-8") if audit_path.exists() else ""
audit_path.write_text(report, encoding="utf-8")


# Résumé synthétique pour notification
def audit_summary(entries):
    total = len(entries)
    by_fw = {}
    for e in entries:
        by_fw[e["framework"]] = by_fw.get(e["framework"], 0) + 1
    fw_str = ", ".join(f"{fw}: {n}" for fw, n in sorted(by_fw.items()))
    return f"Total apps: {total} | {fw_str}"


strict_mode = os.environ.get("DASHBOARD_AUDIT_STRICT", "").lower() in (
    "1",
    "true",
    "yes",
)

if old_report != report:
    summary = audit_summary(entries)
    notify_change(
        "[AUDIT] Changement détecté dans la liste des dashboards/applications. Rapport mis à jour.",
        summary=summary,
    )
    print(f"Changements détectés : notification envoyée.\n{summary}")
    if strict_mode:
        print("[CI] Mode strict activé : échec car l’audit a changé.")
        exit(1)
else:
    print("Aucun changement détecté dans l’audit.")
