# Sphinx quickstart config for API doc generation
# Place this in docs/ and run: sphinx-quickstart --quiet --project "Crypto AI Terminal" --author "Team" --sep --makefile --batchfile
# Then: pip install sphinx sphinx_rtd_theme
# To build: cd docs && make html

# In docs/conf.py, add:
# import os
# import sys
# sys.path.insert(0, os.path.abspath('..'))
# extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']
# html_theme = 'sphinx_rtd_theme'

# In docs/index.rst, add:
# .. automodule:: run_strategy_factory
#    :members:
#
# Pour générer la doc API automatiquement à chaque build CI, ajoutez un job :
#
#  - name: Build docs
#    run: |
#      pip install sphinx sphinx_rtd_theme
#      cd docs && make html
