"""Lecture des unités LAB : source unique des propriétés appliquées par les tests hôte.

Les tests d'isolation n'écrivent pas la moindre restriction à la main : ils relisent les fichiers
d'unité prévus et les appliquent tels quels à une unité transitoire. Une directive ajoutée,
retirée ou modifiée dans un fichier change donc le test, et une directive sans sonde ni
exemption déclarée fait échouer `coverage_gaps`.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT_DIR = HERE / "systemd"
UNITS = ("lab01-run", "lab01-export", "lab01-api")
# Directives de [Service] qui décrivent le lancement, pas le bac à sable.
LAUNCH_ONLY = {"Type", "ExecStart", "Restart", "Slice"}

# Directive -> sonde (nom dans host_isolation_tests.PROBES) ou exemption motivée.
# `probe:<nom>` = effet vérifié depuis l'intérieur du processus ; `readback:<nom>` = valeur
# effective relue (limites, cgroup...) ; `exempt:<raison>` = NON sondée, dit explicitement.
COVERAGE: dict[str, str] = {
    "User": "readback:ids",
    "Group": "readback:ids",
    "WorkingDirectory": "readback:ids",
    "Environment": "readback:env",
    "TimeoutStartSec": "exempt:délai de supervision, pas une restriction d'accès",
    "TimeoutStopSec": "exempt:délai de supervision, pas une restriction d'accès",
    "PrivateNetwork": "probe:netdev",
    "IPAddressDeny": "probe:ipdeny",
    "IPAddressAllow": "probe:ipdeny",
    "RestrictAddressFamilies": "probe:af",
    "ProtectSystem": "probe:write_ro",
    "ProtectHome": "probe:inaccessible",
    "PrivateTmp": "probe:tmp",
    "PrivateDevices": "probe:dev",
    "ReadWritePaths": "probe:write_rw",
    "ReadOnlyPaths": "probe:write_ro",
    "InaccessiblePaths": "probe:inaccessible",
    "NoNewPrivileges": "probe:nonewprivs",
    "CapabilityBoundingSet": "probe:caps",
    "AmbientCapabilities": "probe:caps",
    "LockPersonality": "probe:lockpers",
    "MemoryDenyWriteExecute": "probe:mdwe",
    "RestrictNamespaces": "probe:userns",
    "RestrictRealtime": "exempt:non attribuable : refus aussi par l'absence de privilèges et par le filtre syscall",
    "RestrictSUIDSGID": "probe:suid",
    "ProtectKernelTunables": "probe:procsys",
    "ProtectKernelModules": "probe:modules",
    "ProtectControlGroups": "probe:cgroupfs",
    "ProtectClock": "exempt:non attribuable sans modifier l'horloge de l'hôte (jamais fait)",
    "SystemCallFilter": "probe:syscall",
    "UMask": "readback:umask",
    "LimitNOFILE": "readback:limits",
    "LimitNPROC": "readback:limits",
    "LimitCORE": "readback:limits",
    "LimitFSIZE": "readback:limits",
    "RequiresMountsFor": "exempt:dépendance de montage vérifiée par le démarrage réel de l'unité",
}


def parse_unit(path: Path) -> dict[str, list[tuple[str, str]]]:
    sections: dict[str, list[tuple[str, str]]] = {}
    cur = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1]
            sections.setdefault(cur, [])
            continue
        if cur is None or "=" not in line:
            raise ValueError(f"{path.name}: ligne illisible: {line!r}")
        key, _, value = line.partition("=")
        sections[cur].append((key.strip(), value.strip()))
    return sections


def sandbox_props(unit: str, unit_dir: Path = UNIT_DIR) -> list[tuple[str, str]]:
    """Propriétés à appliquer à l'unité transitoire, dans l'ordre du fichier."""
    sec = parse_unit(unit_dir / f"{unit}.service")
    props = [(k, v) for k, v in sec.get("Service", []) if k not in LAUNCH_ONLY]
    props += [(k, v) for k, v in sec.get("Unit", []) if k == "RequiresMountsFor"]
    return props


def exec_start(unit: str, unit_dir: Path = UNIT_DIR) -> str:
    for k, v in parse_unit(unit_dir / f"{unit}.service")["Service"]:
        if k == "ExecStart":
            return v
    raise ValueError(f"{unit}: pas d'ExecStart")


def slice_limits(unit_dir: Path = UNIT_DIR) -> dict[str, str]:
    return dict(parse_unit(unit_dir / "lab01.slice").get("Slice", []))


def coverage_gaps(unit_dir: Path = UNIT_DIR) -> list[str]:
    """Directives présentes dans une unité mais ni sondées ni exemptées : dérive à corriger."""
    gaps = set()
    for u in UNITS:
        for key, _ in sandbox_props(u, unit_dir):
            if key not in COVERAGE:
                gaps.add(f"{u}: {key}")
    return sorted(gaps)


def without(props: list[tuple[str, str]], keys: set[str]) -> list[tuple[str, str]]:
    """Même propriétés moins un groupe de directives : sert d'essai témoin."""
    return [(k, v) for k, v in props if k not in keys]
