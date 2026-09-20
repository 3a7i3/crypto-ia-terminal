"""F00-CONFIG-FREEZE-01 — deterministic experiment configuration freeze.

This tool is deliberately separate from the immutable PPL epoch manifest.
It captures the effective, non-secret configuration that can materially alter
the F-00 population and binds it to the exact runtime source SHA.

Operator contract:
- environment files are supplied in the same order as systemd EnvironmentFile=
  directives; later files override earlier files;
- secret-looking keys are never serialized;
- explicit values win over code defaults;
- unset material variables are resolved from production os.getenv()/environ.get
  call-sites when all literal defaults agree;
- ambiguous or non-literal defaults fail closed;
- snapshot creation is O_EXCL / never overwrite;
- validation re-captures the current state and requires exact canonical equality.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SNAPSHOT_SCHEMA = "F00_EXPERIMENT_CONFIG_V1"

MATERIAL_PREFIXES = (
    "SIGNAL_",
    "GATE_",
    "LSE_",
    "REGIME_",
    "PB_",
    "EXEC_",
    "CAE_",
    "CONV_",
    "NTL_",
    "META_",
    "EO_",
    "RG_",
    "CT_",
    "EM_",
    "INV_",
    "SA_",
    "V9_",
    "PM_",
    "MEXC_SIM_",
    "P6_",
    "P8_",
    "P9_",
    "P10_",
    "KELLY_",
    "PAPER_",
    "PPL_",
)

MATERIAL_EXACT = frozenset(
    {
        "MIN_PROFIT_FACTOR",
        "EXCHANGE_ID",
        "EXCHANGE_TESTNET",
        "LIVE_TRADING_CONFIRMED",
    }
)

SECRET_SEGMENTS = frozenset(
    {
        "KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PASSWD",
        "PRIVATE",
        "CREDENTIAL",
        "WEBHOOK",
        "CHAT",
        "SMTP",
        "EMAIL",
    }
)

EXCLUDED_TOP_LEVEL = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "_ARCHIVE_2026",
        "tests",
        "scripts",
        "tools",
        "docs",
        "obsidian_vault",
        "notebooks",
        "S2",
    }
)

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigFreezeError(RuntimeError):
    """Fail-closed configuration-freeze error."""


@dataclass(frozen=True)
class DefaultCandidate:
    value: Any
    path: str
    line: int


def _is_material(key: str) -> bool:
    return key in MATERIAL_EXACT or any(key.startswith(p) for p in MATERIAL_PREFIXES)


def _is_secret_key(key: str) -> bool:
    parts = {part for part in re.split(r"[^A-Za-z0-9]+", key.upper()) if part}
    if parts & SECRET_SEGMENTS:
        return True
    # Common compact forms that do not always split into exact segments.
    upper = key.upper()
    return any(
        marker in upper
        for marker in (
            "API_KEY",
            "API_SECRET",
            "ACCESS_TOKEN",
            "BOT_TOKEN",
            "PRIVATE_KEY",
        )
    )


def _normalise_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigFreezeError(f"environment file is missing: {path}")
    if not path.is_file():
        raise ConfigFreezeError(f"environment path is not a file: {path}")

    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _KEY_RE.fullmatch(key):
            raise ConfigFreezeError(
                f"{path}:{line_number}: unsupported environment key syntax: {key!r}"
            )

        # Material experiment values in the current service configuration are
        # scalar. Refuse multiline/escape-heavy syntax rather than silently
        # mis-parsing systemd EnvironmentFile semantics.
        if "\n" in value or "\r" in value:
            raise ConfigFreezeError(
                f"{path}:{line_number}: multiline environment values are unsupported"
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        values[key] = value
    return values


def _effective_explicit(
    env_files: Iterable[Path], repo_root: Path
) -> tuple[dict[str, str], dict[str, str]]:
    effective: dict[str, str] = {}
    source: dict[str, str] = {}

    for path in env_files:
        for key, value in _parse_env_file(path).items():
            if not _is_material(key) or _is_secret_key(key):
                continue
            effective[key] = value
            source[key] = _normalise_path(path, repo_root)
    return effective, source


def _literal_default(node: ast.AST | None) -> tuple[bool, Any]:
    if node is None:
        return True, None
    try:
        return True, ast.literal_eval(node)
    except (ValueError, TypeError):
        pass

    # Common production pattern: os.getenv("X", str(CONSTANT_LITERAL)).
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"str", "int", "float", "bool"}
        and len(node.args) == 1
        and not node.keywords
    ):
        try:
            value = ast.literal_eval(node.args[0])
        except (ValueError, TypeError):
            return False, None
        try:
            return True, {"str": str, "int": int, "float": float, "bool": bool}[node.func.id](
                value
            )
        except (TypeError, ValueError):
            return False, None

    return False, None


def _iter_python_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*.py")):
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            continue
        if not rel.parts:
            continue
        if rel.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        yield path


def _os_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    os_names = {"os"}
    getenv_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_names.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_names.add(alias.asname or "getenv")
    return os_names, getenv_names


def _is_getenv_call(
    func: ast.AST, os_names: set[str], getenv_names: set[str]
) -> bool:
    if isinstance(func, ast.Name):
        return func.id in getenv_names

    if not isinstance(func, ast.Attribute) or func.attr not in {"getenv", "get"}:
        return False

    # os.getenv(...)
    if func.attr == "getenv" and isinstance(func.value, ast.Name):
        return func.value.id in os_names

    # os.environ.get(...)
    if func.attr == "get" and isinstance(func.value, ast.Attribute):
        env = func.value
        return (
            env.attr == "environ"
            and isinstance(env.value, ast.Name)
            and env.value.id in os_names
        )
    return False


def _discover_defaults(repo_root: Path) -> tuple[
    dict[str, list[DefaultCandidate]], dict[str, list[str]]
]:
    candidates: dict[str, list[DefaultCandidate]] = {}
    unresolved: dict[str, list[str]] = {}

    for path in _iter_python_files(repo_root):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise ConfigFreezeError(f"cannot parse production source {path}: {exc}") from exc

        os_names, getenv_names = _os_aliases(tree)
        rel = _normalise_path(path, repo_root)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_getenv_call(node.func, os_names, getenv_names):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            key = node.args[0].value
            if not isinstance(key, str) or not _is_material(key) or _is_secret_key(key):
                continue

            default_node = node.args[1] if len(node.args) >= 2 else None
            if default_node is None:
                for kw in node.keywords:
                    if kw.arg == "default":
                        default_node = kw.value
                        break

            ok, value = _literal_default(default_node)
            location = f"{rel}:{getattr(node, 'lineno', 0)}"
            if not ok:
                unresolved.setdefault(key, []).append(location)
                continue
            candidates.setdefault(key, []).append(
                DefaultCandidate(
                    value=value,
                    path=rel,
                    line=int(getattr(node, "lineno", 0)),
                )
            )

    return candidates, unresolved


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfigFreezeError(f"git {' '.join(args)} failed: {exc}") from exc
    return result.stdout.strip()


def _require_clean_repo(repo_root: Path) -> str:
    sha = _git(repo_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ConfigFreezeError(f"unexpected git SHA: {sha!r}")
    if _git(repo_root, "status", "--porcelain"):
        raise ConfigFreezeError("repository worktree is not clean")
    return sha


def build_snapshot_payload(
    *,
    repo_root: Path,
    env_files: list[Path],
    paper_epoch_id: str,
) -> dict[str, Any]:
    if not paper_epoch_id:
        raise ConfigFreezeError("paper_epoch_id is required")

    runtime_source_sha = _require_clean_repo(repo_root)
    explicit, explicit_source = _effective_explicit(env_files, repo_root)
    defaults, unresolved_defaults = _discover_defaults(repo_root)

    parameters: dict[str, Any] = {}
    material_keys = sorted(set(explicit) | set(defaults) | set(unresolved_defaults))

    for key in material_keys:
        if _is_secret_key(key):
            raise ConfigFreezeError(f"secret-like key reached snapshot builder: {key}")

        callsites = sorted(
            {
                f"{candidate.path}:{candidate.line}"
                for candidate in defaults.get(key, [])
            }
            | set(unresolved_defaults.get(key, []))
        )

        if key in explicit:
            parameters[key] = {
                "value": explicit[key],
                "provenance": "EXPLICIT_ENVIRONMENT_FILE",
                "source": explicit_source[key],
                "callsites": callsites,
            }
            continue

        if unresolved_defaults.get(key):
            raise ConfigFreezeError(
                f"material variable {key} is unset and has non-literal default(s): "
                + ", ".join(sorted(unresolved_defaults[key]))
            )

        values = [candidate.value for candidate in defaults.get(key, [])]
        canonical_values = {
            _canonical_json_bytes(value).decode("utf-8") for value in values
        }
        if len(canonical_values) != 1:
            detail = ", ".join(
                f"{candidate.path}:{candidate.line}={candidate.value!r}"
                for candidate in defaults.get(key, [])
            )
            raise ConfigFreezeError(
                f"material variable {key} is unset and has conflicting code defaults: {detail}"
            )

        value = values[0]
        parameters[key] = {
            "value": value,
            "provenance": "CODE_DEFAULT",
            "source": "runtime_source_sha",
            "callsites": callsites,
        }

    required = {
        "PAPER_LIFECYCLE_AUTHORITY": "PPL_AUTHORITY",
        "PAPER_TRADING_ENABLED": "true",
        "PB_MAX_POSITIONS": "0",
        "PPL_AUTHORITY_EPOCH_ID": paper_epoch_id,
    }
    for key, expected in required.items():
        record = parameters.get(key)
        if record is None or str(record["value"]).lower() != expected.lower():
            raise ConfigFreezeError(
                f"pre-start invariant {key}={expected!r} is not satisfied"
            )

    env_refs = [_normalise_path(path, repo_root) for path in env_files]

    return {
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "paper_epoch_id": paper_epoch_id,
        "runtime_source_sha": runtime_source_sha,
        "environment_files_in_precedence_order": env_refs,
        "material_parameter_count": len(parameters),
        "parameters": parameters,
    }


def snapshot_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _snapshot_document(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "snapshot_sha256": snapshot_sha256(payload),
    }


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def capture(
    *,
    repo_root: Path,
    env_files: list[Path],
    paper_epoch_id: str,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise ConfigFreezeError(f"snapshot already exists and will not be overwritten: {output}")
    payload = build_snapshot_payload(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
    )
    document = _snapshot_document(payload)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    _write_exclusive(output, encoded)
    return document


def validate(*, repo_root: Path, snapshot_path: Path) -> dict[str, Any]:
    try:
        document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigFreezeError(f"cannot read snapshot {snapshot_path}: {exc}") from exc

    if not isinstance(document, dict):
        raise ConfigFreezeError("snapshot must be a JSON object")
    stored_hash = document.pop("snapshot_sha256", None)
    if not isinstance(stored_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", stored_hash):
        raise ConfigFreezeError("snapshot_sha256 is missing or malformed")

    actual_stored_hash = snapshot_sha256(document)
    if actual_stored_hash != stored_hash:
        raise ConfigFreezeError(
            f"snapshot content hash mismatch: stored={stored_hash} actual={actual_stored_hash}"
        )
    if document.get("snapshot_schema") != SNAPSHOT_SCHEMA:
        raise ConfigFreezeError(
            f"unsupported snapshot schema: {document.get('snapshot_schema')!r}"
        )

    env_refs = document.get("environment_files_in_precedence_order")
    if not isinstance(env_refs, list) or not env_refs:
        raise ConfigFreezeError("snapshot environment file list is missing")
    env_files = [
        Path(item) if Path(item).is_absolute() else repo_root / item
        for item in env_refs
        if isinstance(item, str) and item
    ]
    if len(env_files) != len(env_refs):
        raise ConfigFreezeError("snapshot environment file list is malformed")

    paper_epoch_id = document.get("paper_epoch_id")
    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise ConfigFreezeError("snapshot paper_epoch_id is missing")

    current = build_snapshot_payload(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
    )
    current_hash = snapshot_sha256(current)
    if current != document or current_hash != stored_hash:
        raise ConfigFreezeError(
            "effective experiment configuration differs from frozen snapshot: "
            f"frozen={stored_hash} current={current_hash}"
        )
    return {
        "snapshot_sha256": stored_hash,
        "paper_epoch_id": paper_epoch_id,
        "runtime_source_sha": current["runtime_source_sha"],
        "material_parameter_count": current["material_parameter_count"],
    }


def _default_output(repo_root: Path, epoch: str) -> Path:
    return repo_root / "databases" / "ppl_authority" / f"{epoch}.experiment-config.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="create immutable F00 config snapshot")
    cap.add_argument("--epoch", required=True)
    cap.add_argument(
        "--env-file",
        action="append",
        required=True,
        dest="env_files",
        help="EnvironmentFile in exact precedence order; repeat for each file",
    )
    cap.add_argument("--output", default=None)

    val = sub.add_parser("validate", help="validate current config against snapshot")
    val.add_argument("--snapshot", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.command == "capture":
            env_files = [
                Path(item) if Path(item).is_absolute() else repo_root / item
                for item in args.env_files
            ]
            output = (
                Path(args.output)
                if args.output
                else _default_output(repo_root, args.epoch)
            )
            if not output.is_absolute():
                output = repo_root / output
            doc = capture(
                repo_root=repo_root,
                env_files=env_files,
                paper_epoch_id=args.epoch,
                output=output,
            )
            explicit_count = sum(
                1
                for item in doc["parameters"].values()
                if item["provenance"] == "EXPLICIT_ENVIRONMENT_FILE"
            )
            default_count = doc["material_parameter_count"] - explicit_count
            print(f"SNAPSHOT_PATH={_normalise_path(output, repo_root)}")
            print(f"SNAPSHOT_SHA256={doc['snapshot_sha256']}")
            print(f"RUNTIME_SOURCE_SHA={doc['runtime_source_sha']}")
            print(f"PAPER_EPOCH_ID={doc['paper_epoch_id']}")
            print(f"MATERIAL_PARAMETER_COUNT={doc['material_parameter_count']}")
            print(f"EXPLICIT_PARAMETER_COUNT={explicit_count}")
            print(f"CODE_DEFAULT_PARAMETER_COUNT={default_count}")
            print("F00_EXPERIMENT_CONFIG_CAPTURE=PASS")
            return 0

        result = validate(
            repo_root=repo_root,
            snapshot_path=(
                Path(args.snapshot)
                if Path(args.snapshot).is_absolute()
                else repo_root / args.snapshot
            ),
        )
        print(f"SNAPSHOT_SHA256={result['snapshot_sha256']}")
        print(f"RUNTIME_SOURCE_SHA={result['runtime_source_sha']}")
        print(f"PAPER_EPOCH_ID={result['paper_epoch_id']}")
        print(f"MATERIAL_PARAMETER_COUNT={result['material_parameter_count']}")
        print("F00_EXPERIMENT_CONFIG_VALIDATE=PASS")
        return 0

    except ConfigFreezeError as exc:
        print(f"F00_EXPERIMENT_CONFIG=FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
