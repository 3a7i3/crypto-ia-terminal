"""Détection d'instructions cachées dans les contenus externes (prompt injection).

Un contenu externe qui ressemble à une instruction est **signalé et cité**, jamais
suivi. La détection ne sert qu'à prévenir l'opérateur : même un contenu non
détecté n'a aucun moyen d'agir, car les outils sont choisis uniquement à partir
de l'intention de la demande utilisateur, avant la lecture des sources.
"""

from __future__ import annotations

import re

_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) (instructions|prompts?)"),
    re.compile(r"(?i)ignore (les |toutes les )?instructions"),
    re.compile(r"(?i)\b(system|assistant|developer)\s*:"),
    re.compile(r"(?i)you are now|tu es (maintenant|d[ée]sormais)"),
    re.compile(r"(?i)\b(sudo|systemctl|journalctl|rm\s+-rf|chmod|curl\s+\S+\s*\|)"),
    re.compile(
        r"(?i)\b(restart|red[ée]marre[rz]?|d[ée]ploie[rz]?|deploy|merge|fusionne[rz]?|stop|arr[eê]te[rz]?)\b"
        r"(?! pull request)(?! #?\d).{0,40}\b(advisor|services?|vps|prod\w*|runtime|now|maintenant|imm[ée]diatement)\b"
    ),
    re.compile(r"(?i)(print|affiche|r[ée]v[eè]le|lis|read|send|envoie)\b.{0,30}(token|jeton|secret|\.env|cl[ée]|password)"),
    re.compile(r"(?i)javascript:|data:text/html|<script"),
    re.compile(r"(?i)\[REDACTED\]"),
)


def looks_like_instruction(text: str) -> bool:
    return any(p.search(text) for p in _MARKERS)
