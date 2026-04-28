# Sphinx configuration for Crypto AI Terminal

# Instructions :
# 1. Place this file as docs/conf.py
# 2. Run `sphinx-quickstart` in the docs/ folder if not already done
# 3. Run `make html` or `sphinx-build -b html . _build/html` in docs/

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "Crypto AI Terminal"
copyright = "2026, Crypto AI Terminal"
author = "Crypto AI Team"
release = "9.1"

extensions = [
    "myst_parser",
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
]

autosummary_generate = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_logo = "../assets/logo_ai_quant.png"
html_theme_options = {
    "light_logo": "../assets/logo_ai_quant.png",
    "dark_logo": "../assets/logo_ai_quant.png",
    "sidebar_hide_name": True,
    "navigation_with_keys": True,
    "source_repository": "https://github.com/<OWNER>/<REPO>/",
    "source_branch": "main",
    "source_directory": "docs/",
}
html_static_path = ["_static"]
html_favicon = "_static/favicon.ico"


def setup(app):
    app.add_css_file("custom.css")


# -- Options for autodoc ---------------------------------------------------
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "private-members": False,
    "show-inheritance": True,
}

# -- Napoleon settings (for Google/NumPy docstrings) -----------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True

# -- MyST settings (Markdown support) --------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "html_admonition",
    "html_image",
    "replacements",
    "smartquotes",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3
