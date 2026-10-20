"""Byte-for-byte copy of the A1 spec validator of PR #374 (head ``c21e1a83``).

``canonical.py``, ``capabilities.py`` and ``spec.py`` are copied unchanged from
``agent_economy/agent_registry/`` on branch
``claude/agent-econ-a1-source-registry-core-hdx5ep``; their sha256 is pinned in
``PROVENANCE`` and checked by ``tests/colony_lab/test_a1_identity.py``. They are
pure (no I/O). #374 stays parked; this copy registers nothing and is replaced by
an import once A1 lands. Never edit these files: re-copy and re-pin instead.
Check against git with ``git show c21e1a83:agent_economy/agent_registry/<file>``.
"""

PROVENANCE = {
    "source_pr": 374,
    "source_commit": "c21e1a83",
    "files": {
        "canonical.py": {"git_blob": "806fa739e051356a180362f2546b35cb74a8debb",
                         "sha256": "c580c9077e78fbe362c2d0b4c38744044172b8eb9e0ac12860c86b8a566f8c77"},
        "capabilities.py": {"git_blob": "fadca6c8ab07a412e29eb09137eb5ffe06ace9ff",
                            "sha256": "9897ad8368483837ba982e174aa775573ec5f5b6a099ddeca1cbfd9568b12021"},
        "spec.py": {"git_blob": "8897259acbbac5081ddfc64ccebb29e2599386c6",
                    "sha256": "c1844d4c6f85a83bc7b26c1f4ba9dafcad35e50c77d3c8d2ff098e4852f5ec04"},
    },
}
