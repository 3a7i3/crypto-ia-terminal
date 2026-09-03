"""CI-00B (Phase 4): invariant réel de permissions sur les secrets runtime.

Remplace `test_no_world_read_access` (tests/root/test_security_permissions.py),
qui testait à tort que des fichiers *versionnés dans git* n'étaient pas
world-readable — un test structurellement impossible à faire passer de
façon fiable, puisque `git checkout` restaure toujours les fichiers en
0644 quel que soit leur contenu. L'invariant de sécurité reste valide,
mais il porte sur l'étape qui matérialise des secrets runtime sur disque
(scripts/confidential_files_perms.py), pas sur le contenu du dépôt.
"""

import stat
import sys

import pytest

from scripts.confidential_files_perms import (
    is_world_readable_or_writable,
    set_secure_permissions,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Permissions Unix non applicables sur Windows"
)


def test_set_secure_permissions_removes_world_and_group_access(tmp_path):
    secret = tmp_path / "runtime_secret.json"
    secret.write_text("{}", encoding="utf-8")
    secret.chmod(0o644)
    assert is_world_readable_or_writable(secret)

    secured = set_secure_permissions([secret])

    assert secured == [secret]
    mode = stat.S_IMODE(secret.stat().st_mode)
    assert mode == 0o600
    assert not is_world_readable_or_writable(secret)


def test_set_secure_permissions_ignores_missing_files(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert set_secure_permissions([missing]) == []


def test_set_secure_permissions_handles_multiple_paths(tmp_path):
    a = tmp_path / "a.secret"
    b = tmp_path / "b.secret"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    a.chmod(0o644)
    b.chmod(0o666)

    secured = set_secure_permissions([a, b])

    assert set(secured) == {a, b}
    assert not is_world_readable_or_writable(a)
    assert not is_world_readable_or_writable(b)
