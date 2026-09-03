"""scripts/confidential_files_perms.py — CI-00B (Phase 4).

Utilitaire pur, sans effet réseau ni SSH, qui applique des permissions
0600 (lecture/écriture propriétaire seulement) à une liste de fichiers
sensibles réellement présents sur le disque cible (VPS runtime ou
poste local).

Contexte de l'invariant historique :
`test_no_world_read_access` (tests/root/test_security_permissions.py)
vérifiait autrefois que des fichiers sensibles du dépôt n'étaient pas
world-readable. C'est un test structurellement incorrect : `git
checkout` restaure toujours les fichiers en 0644 et git ne peut
pas transporter de permissions restrictives via le contenu versionné.
Le vrai invariant de sécurité — « les secrets runtime ne doivent
jamais être lisibles par d'autres utilisateurs » — appartient à
l'étape de déploiement/exploitation qui matérialise ces secrets sur
disque, pas au contenu du dépôt.

Cette fonction est la matérialisation testable de cette étape. Elle
n'est PAS câblée dans le transfert SSH de `scripts/deploy_vps.sh`
(hors périmètre CI-00B : « no deployment, no VPS changes ») — elle
fournit le mécanisme, prêt à être invoqué par un opérateur ou un
futur geste de déploiement explicite, sans modifier le comportement
actuel de déploiement.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

# 0600 : lecture/écriture propriétaire uniquement.
SECURE_MODE = stat.S_IRUSR | stat.S_IWUSR


def set_secure_permissions(paths: list[str | Path]) -> list[Path]:
    """Applique le mode 0600 à chaque fichier existant de `paths`.

    Les chemins absents sont silencieusement ignorés (un fichier de
    secrets peut ne pas encore exister dans un environnement donné).
    Retourne la liste des fichiers effectivement modifiés.
    """
    secured: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.exists():
            os.chmod(p, SECURE_MODE)
            secured.append(p)
    return secured


def is_world_readable_or_writable(path: str | Path) -> bool:
    """True si `path` est lisible ou inscriptible par "other" (world)."""
    mode = os.stat(path).st_mode
    return bool(mode & (stat.S_IROTH | stat.S_IWOTH))
