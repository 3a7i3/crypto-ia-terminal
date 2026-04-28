# Configuration centralisée : strategy_factory_config.ini

Ce module permet de centraliser la configuration des simulations évolutives et des visualisations.

## Utilisation

- Placez le fichier `strategy_factory_config.ini` à la racine du projet ou à côté de vos scripts.
- Les paramètres suivants sont lus automatiquement :

```
[visualization]
show_plots = true  # Affiche les graphiques (true) ou exporte sans affichage (false)

[simulation]
pop_size = 100     # Taille de la population
n_gen = 100        # Nombre de générations
migration_freq = 5 # Fréquence de migration
migration_rate = 0.1 # Taux de migration
```

- Vous pouvez forcer le mode batch/headless (sans affichage graphique) avec l’option CLI :

```
python run_strategy_factory.py --no-gui
```

L’argument CLI a priorité sur la configuration du fichier.

## Avantages
- Facile à modifier sans toucher au code.
- Compatible avec l’automatisation et les environnements serveurs.
- Peut être partagé entre plusieurs modules pour une cohérence globale.

## Extension à d’autres modules
Pour bénéficier de cette configuration centralisée dans d’autres scripts, il suffit d’ajouter :

```python
import configparser
config = configparser.ConfigParser()
config.read('strategy_factory_config.ini')
# Exemple d’utilisation :
POP_SIZE = config.getint('simulation', 'pop_size', fallback=100)
```

Vous pouvez factoriser ce chargement dans un utilitaire commun (ex : config_utils.py) pour éviter la duplication.

## Modules et frameworks compatibles (automatisés)

La configuration centralisée est désormais automatiquement intégrée dans :
- run_strategy_factory.py (simulation principale)
- visualize_strategy_ecosystem.py
- visualize_strategy_ecosystem_all_gens.py
- results/visualize_population.py
- results/visualize_equity_curves.py
- data_engine/plot_regimes.py
- evolution_dashboard.py (Streamlit)
- evolution_3d_view.py (Streamlit)

Pour tous ces modules, le paramètre `[visualization] show_plots` contrôle l’affichage ou le mode headless/batch de tous les graphiques (matplotlib, plotly, Streamlit, etc.).

Pour ajouter la centralisation à d’autres scripts, copiez simplement le bloc suivant en début de fichier :

```python
import configparser
config = configparser.ConfigParser()
config.read('strategy_factory_config.ini')
SHOW_PLOTS = config.getboolean('visualization', 'show_plots', fallback=True)
```

Et remplacez tous les `plt.show()` par :

```python
if SHOW_PLOTS:
    plt.show()
else:
    plt.close()
```

Cela garantit un contrôle global, reproductible et automatisé de l’affichage dans tout l’écosystème quantitatif.
