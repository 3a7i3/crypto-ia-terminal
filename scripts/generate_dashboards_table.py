import os
import re
from pathlib import Path

# Patterns for dashboard frameworks
FRAMEWORKS = {
    "Streamlit": [r"import streamlit"],
    "Panel": [r"import panel", r"panel\.serve"],
    "Dash": [r"import dash"],
    "FastAPI": [r"import fastapi"],
}

# Default ports for each framework
DEFAULT_PORTS = {
    "Streamlit": "8501",
    "Panel": "5010",
    "Dash": "8050",
    "FastAPI": "8080",
}

# Find all .py files recursively
root = Path(__file__).parent.parent
py_files = list(root.rglob("*.py"))

entries = []
for pyfile in py_files:
    rel_path = pyfile.relative_to(root)
    content = pyfile.read_text(encoding="utf-8", errors="ignore")
    for fw, patterns in FRAMEWORKS.items():
        if any(re.search(p, content) for p in patterns):
            # Find .bat launch script
            script_name = f"launch_{pyfile.stem}.bat"
            script_path = root / script_name
            if not script_path.exists():
                # Try to find a .bat with similar name
                for bat in root.glob("launch_*.bat"):
                    if pyfile.stem in bat.stem:
                        script_name = bat.name
                        break
            port = DEFAULT_PORTS.get(fw, "")
            # Description: first docstring or comment
            desc = ""
            docstring = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if docstring:
                desc = docstring.group(1).split("\n")[0].strip()
            elif "#" in content:
                desc = content.split("#")[1].split("\n")[0].strip()
            entries.append((str(rel_path), fw, script_name, port, desc))
            break

# Add FastAPI special cases (APIs)
for pyfile in py_files:
    rel_path = pyfile.relative_to(root)
    if "FastAPI" in open(pyfile, encoding="utf-8", errors="ignore").read():
        if not any(str(rel_path) == e[0] for e in entries):
            script_name = f"launch_{pyfile.stem}.bat"
            port = DEFAULT_PORTS["FastAPI"]
            entries.append((str(rel_path), "FastAPI", script_name, port, "API FastAPI"))

# Sort by framework then name
entries.sort(key=lambda x: (x[1], x[0]))

# Write table
table = "| Dashboard / App | Framework | Script de lancement | Port par défaut | Description rapide |\n"
table += "|-----------------|-----------|---------------------|-----------------|--------------------|\n"
for e in entries:
    table += f"| {e[0]} | {e[1]} | {e[2]} | {e[3]} | {e[4]} |\n"

readme = root / "DASHBOARDS_README.md"
content = readme.read_text(encoding="utf-8", errors="ignore")
start = content.find("| Dashboard / App")
if start != -1:
    end = content.find("---", start)
    if end == -1:
        end = len(content)
    new_content = content[:start] + table + "\n" + content[end:]
    readme.write_text(new_content, encoding="utf-8")
    print("DASHBOARDS_README.md mis à jour.")
else:
    print(table)
