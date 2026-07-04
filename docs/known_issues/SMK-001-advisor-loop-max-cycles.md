# Ticket SMK-001 — `max_cycles=1` non respecté dans `advisor_loop.main()`

**Statut :** ouvert, non investigué en profondeur (mis de côté volontairement — voir § Contexte)
**Découvert :** 2026-07-03, pendant le sprint data-safety (contamination `regret_analysis.jsonl` /
`black_box.jsonl` / `paper_trades.jsonl`)
**Sévérité :** inconnue — reproductible sur un test de fumée, aucun lien démontré avec un incident
en production

---

## Symptôme

```
tests/test_advisor_loop_smoke.py::test_main_opens_real_position_path_and_updates_tracker
tests/test_advisor_loop_smoke.py::test_main_opens_position_when_paper_execution_is_used
```

Les deux tests appellent :

```python
advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)
assert len(added_positions) == 1
```

et échouent avec :

```
AssertionError: assert 21 == 1
 where 21 = len([namespace(order_id='demo-order-1', ...), ...])
```

`analyze_symbol()` (mocké dans le test) est donc appelé 21 fois au lieu d'une seule, alors qu'un
seul symbole est passé et que `max_cycles=1`.

## Reproductibilité

- **Reproductible en isolation** : les deux tests échouent même exécutés seuls
  (`pytest tests/test_advisor_loop_smoke.py::test_main_opens_real_position_path_and_updates_tracker
  tests/test_advisor_loop_smoke.py::test_main_opens_position_when_paper_execution_is_used`),
  ce qui écarte une pollution d'état entre tests (ordre d'exécution, thread résiduel d'un test
  précédent).
- **Aucun rapport démontré avec la contamination de `databases/*.jsonl`** : le fixture
  `_isolate_paper_recorder` (conftest.py) redirige systématiquement `PaperTradeRecorder` vers un
  fichier temporaire vide pour chaque test — le contenu réel de `databases/paper_trades.jsonl`
  (nettoyé ou non) est donc structurellement invisible à ces deux tests.

## Hypothèses déjà éliminées

| Hypothèse | Verdict | Preuve |
|---|---|---|
| Pollution d'ordre entre tests (thread `RegretScheduler` laissé actif par un test précédent) | ❌ Écartée | Échec reproduit même en exécutant les 2 tests seuls |
| `ColdStartManager` / cycles "shadow warmup" avant `LIVE_READY` | ❌ Écartée | `ColdStartManager` n'est référencé nulle part dans `core/advisor_loop.py` |
| Boucle d'attente des futures de préchauffage (`cycle == 1`, ~ligne 4516-4547) | ❌ Écartée | Plafonnée à ~6 itérations (deadline 12s), n'appelle jamais `analyze_symbol` |
| Boucle sur plusieurs symboles | ❌ Écartée | Un seul appel à `analyze_symbol()` dans tout le fichier (ligne 4869), dans `for sym in symbols_ordered` — un seul symbole passé au test |

## Ce qu'il reste à instrumenter

Le compteur de cycle lui-même doit être tracé :

- Où et comment `cycle` est incrémenté dans la boucle principale de `main()`.
- Le point exact de vérification `if max_cycles is not None and cycle >= max_cycles:` (ligne ~6636)
  — pourquoi n'est-il atteint qu'après 21 itérations effectives de la boucle interne au lieu d'une ?
- Toutes les branches `continue` / `break` / `return` de la boucle principale qui pourraient
  permettre au corps de la boucle (dont l'appel à `analyze_symbol`) de s'exécuter plusieurs fois
  par valeur de `cycle`, ou empêcher l'incrément de `cycle` de progresser normalement.
- Vérifier si un mécanisme de retry (P10-F emergency check, safe mode, gouvernance) ré-exécute la
  boucle interne sans passer par l'incrément normal du cycle.

## Contexte — pourquoi ce n'est pas traité immédiatement

Décision prise le 2026-07-03 : le rapport coût/valeur ne justifie pas d'interrompre le sprint
data-safety en cours. `core/advisor_loop.py::main()` fait ~6700 lignes ; la plongée nécessaire
dépasse le périmètre de ce sprint et n'a aucun lien démontré avec la fiabilité des données
scientifiques (`databases/*.jsonl`), qui est l'objet du sprint en cours. Reprendre ce ticket une
fois le sprint data-safety terminé (nettoyage `gate_rejections.csv`, `trade_log.sqlite`, correction
des chemins codés en dur de `advisor_loop.py`).
