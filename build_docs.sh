# Script bash pour générer la documentation Sphinx automatiquement
# Usage : ./build_docs.sh

VENV_PATH=".venv/bin"
SPHINX_BUILD="$VENV_PATH/sphinx-build"
DOCS_DIR="docs"
BUILD_DIR="$DOCS_DIR/_build/html"

if [ ! -x "$SPHINX_BUILD" ]; then
  echo "sphinx-build non trouvé dans .venv. Installez-le avec 'pip install sphinx sphinx_rtd_theme' dans le venv."
  exit 1
fi

if [ ! -d "$DOCS_DIR" ]; then
  echo "Le dossier $DOCS_DIR n'existe pas. Initialisez-le avec 'sphinx-quickstart' d'abord."
  exit 1
fi

$SPHINX_BUILD -b html $DOCS_DIR $BUILD_DIR

if [ $? -eq 0 ]; then
  echo "Documentation générée dans $BUILD_DIR."
else
  echo "Erreur lors de la génération de la documentation."
  exit 1
fi
