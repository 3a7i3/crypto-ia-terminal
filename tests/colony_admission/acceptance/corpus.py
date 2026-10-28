"""Acceptance-corpus traceability for the 3A/3B/3C case matrices, LAB_TEST only.

A matrix specifies cases; it is never an execution result. The registry records,
per case, whether it is implemented, by which tests, through which entry point
and fixture. Only one pytest run, through ``report_plugin``, derives
PASS/FAIL/NOT_EXECUTED for a tree; nothing in this module or the registry does.

Usage (no IO at import):
    python -m tests.colony_admission.acceptance.corpus plan [REPORT.json]
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / 'docs' / 'colony_admission'
REGISTRY = DOCS / 'acceptance' / 'CORPUS_REGISTRY_V0.json'
PLAN = DOCS / 'acceptance' / 'CORPUS_COVERAGE_PLAN_V0.md'

# Matrix namespace -> (file, matrix status that this corpus never rewrites).
MATRICES = {
    '3A': ('P4_3A_PHYSICAL_EVIDENCE_CASES_V0.json', 'SPECIFICATION_ONLY_NOT_EXECUTED'),
    '3B': ('P4_3B_ATTESTATIONS_AND_ANCESTRY_CASES_V0.json', 'SPECIFICATION_ONLY_NOT_EXECUTED'),
    '3C': ('P4_3C_POPULATION_AND_CEILINGS_CASES_V0.json', 'SPECIFICATION_ONLY_NOT_EXECUTED'),
    'EXT': ('P4_EXTERNAL_EVIDENCE_CASES_V0.json', 'CONTRACT_FOR_REVIEW_NOT_EXECUTABLE'),
}
# Supplementary regressions (values left untested by #518) are not matrix cases.
NAMESPACES = tuple(MATRICES) + ('REG',)
# Static implementation states. Execution states exist only in a run report.
IMPLEMENTATION = frozenset({'NON_IMPLEMENTED', 'IMPLEMENTED', 'BLOCKED', 'CONTRACT_NOT_EXECUTABLE'})
EXECUTION = ('NON_IMPLEMENTED', 'NOT_EXECUTED', 'PASS', 'FAIL', 'BLOCKED', 'CONTRACT_NOT_EXECUTABLE')


def case(*ids):
    """Declare that a test function exercises these namespaced matrix cases."""
    for x in ids:
        ns, sep, local = x.partition(':')
        if ns not in NAMESPACES or not sep or not local:
            raise ValueError('invalid acceptance case id: ' + x)

    def mark(fn):
        fn.acceptance_cases = tuple(getattr(fn, 'acceptance_cases', ())) + ids
        return fn
    return mark


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix(ns):
    return json.loads((DOCS / MATRICES[ns][0]).read_text(encoding='utf-8'))


def matrix_cases():
    """Namespaced id -> matrix case, in matrix order."""
    return {ns + ':' + c['id']: c for ns in MATRICES for c in matrix(ns)['cases']}


def registry():
    return json.loads(REGISTRY.read_text(encoding='utf-8'))


def test_function(node):
    """Resolve 'tests/...py::name' to its function, without running it."""
    import importlib
    path, _, name = node.partition('::')
    module = importlib.import_module(path[:-3].replace('/', '.'))
    return getattr(module, name)


def derive(reg, outcomes):
    """Case execution states from one run.

    ``outcomes`` maps a collected test function node (parametrisation removed)
    to the list of its items' outcomes ('passed', 'failed', 'skipped', 'xfailed',
    'xpassed', 'error'). A case passes only if every registered function ran,
    every item passed and nothing was skipped. A strict xfail demonstrates a
    documented defect, so it is reported FAIL, never PASS.
    """
    states = {}
    for cid, entry in list(reg['cases'].items()) + list(reg['regressions'].items()):
        impl = entry['implementation']
        if impl != 'IMPLEMENTED':
            states[cid] = impl
            continue
        runs = [outcomes.get(t) for t in entry['tests']]
        if any(not r for r in runs):
            states[cid] = 'NOT_EXECUTED'
            continue
        flat = [x for r in runs for x in r]
        if any(x in ('failed', 'error', 'xfailed', 'xpassed') for x in flat):
            states[cid] = 'FAIL'
        elif all(x == 'passed' for x in flat):
            states[cid] = 'PASS'
        else:
            states[cid] = 'NOT_EXECUTED'
    return states


def _cell(text):
    return ' '.join(str(text).split()).replace('|', '\\|')


def _expected(c):
    if 'then' in c:
        return ' / '.join(c['then'])
    if 'expect' in c:
        x = c['expect']
        parts = [x.get('status', '')]
        if x.get('required_blockers'):
            parts.append('blockers ⊇ ' + ', '.join(x['required_blockers']))
        parts += x.get('facts', [])
        return ' ; '.join(p for p in parts if p)
    return c.get('expected', '')


def _norm(ns, c):
    sections = c.get('contract_sections') or ([c['section']] if 'section' in c else [])
    p1 = c.get('p1_scenarios') or c.get('p1_refs') or []
    doc = matrix(ns)['contract'] if ns != 'EXT' else 'P4_EXTERNAL_EVIDENCE_FORMATS_V0.md'
    return doc + ' §' + ','.join(sections) + (' ; P1 ' + ','.join(p1) if p1 else '')


def _defaults(ns):
    m = matrix(ns)
    if 'fixture_defaults' in m:
        return ' '.join(m['fixture_defaults'])
    return m.get('defaults', {}).get('unspecified_preconditions', '')


def _tests(e):
    text = ', '.join(t.split('::')[-1] for t in e.get('tests', []))
    if e.get('name_tag_candidates'):
        text += (' ; ' if text else '') + 'candidats par commentaire, non vérifiés : ' + ', '.join(
            t.split('::')[-1] for t in e['name_tag_candidates'])
    if e.get('divergence'):
        text += ' ; divergence : ' + e['divergence']
    return text


def render_plan(report=None):
    reg = registry()
    cases = matrix_cases()
    states = report['cases'] if report else None
    lines = ['# Plan de couverture du corpus d\'acceptation 3A/3B/3C (V0)', '',
             ('Généré par `python -m tests.colony_admission.acceptance.corpus plan` depuis les matrices '
              'et `CORPUS_REGISTRY_V0.json`. Ce plan n\'est pas une preuve d\'exécution : une ligne '
              'IMPLEMENTED n\'est PASS que dans un rapport de run daté sur un arbre exact.'), '']
    lines += ['Règles :', ''] + ['- ' + r for r in reg['rules']] + ['']
    lines += ['Rôle des preuves externes : ' + reg['external_evidence_role'], '']
    if report:
        lines += ['Rapport : ' + _cell(report.get('run', {})), '']
    lines += ['| Matrice | Cas | ' + ' | '.join(EXECUTION if report else sorted(IMPLEMENTATION)) + ' |',
              '|---|---|' + '---|' * len(EXECUTION if report else IMPLEMENTATION)]
    for ns in MATRICES:
        ids = [k for k in reg['cases'] if k.startswith(ns + ':')]
        values = [states[k] for k in ids] if report else [reg['cases'][k]['implementation'] for k in ids]
        cols = EXECUTION if report else sorted(IMPLEMENTATION)
        lines.append('| ' + ns + ' | ' + str(len(ids)) + ' | ' + ' | '.join(str(values.count(s)) for s in cols) + ' |')
    lines.append('')
    for ns in MATRICES:
        defaults = _defaults(ns)
        lines += ['## ' + ns + ' — ' + MATRICES[ns][0], '', 'Point d\'entrée : `' + reg['entry_points'][ns] + '`.', '']
        if defaults:
            lines += ['Préconditions communes : ' + _cell(defaults), '']
        lines += [
                  '| Cas | Exigence | Préconditions | Assertions attendues | Implémentation | Fixture | Tests | '
                  + ('Exécution |' if report else ''),
                  '|---|---|---|---|---|---|---|' + ('---|' if report else '')]
        for cid, c in cases.items():
            if not cid.startswith(ns + ':'):
                continue
            e = reg['cases'][cid]
            row = [cid, _norm(ns, c), _cell(c.get('given', '')), _cell(_expected(c)), e['implementation'],
                   _cell(e.get('fixture', '')), _cell(_tests(e))]
            if report:
                row.append(states[cid])
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
    lines += ['## Régressions supplémentaires (hors comptes de matrice)', '',
              '| ID | Valeur non testée (dossier #518) | Rattachement | Implémentation | Tests |'
              + (' Exécution |' if report else ''), '|---|---|---|---|---|' + ('---|' if report else '')]
    for rid, r in reg['regressions'].items():
        row = [rid, _cell(r['value']), _cell(r['relation']), r['implementation'],
               _cell(', '.join(t.split('::')[-1] for t in r.get('tests', [])))]
        if report:
            row.append(states[rid])
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv):
    if argv[:1] != ['plan']:
        sys.exit(__doc__)
    report = json.loads(Path(argv[1]).read_text(encoding='utf-8')) if len(argv) > 1 else None
    sys.stdout.write(render_plan(report))


if __name__ == '__main__':
    main(sys.argv[1:])
