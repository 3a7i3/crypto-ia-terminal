"""F00-CONFIG-FREEZE-01 — deterministic experiment configuration freeze.

The immutable PPL epoch manifest describes epoch birth. This tool freezes the
separate effective F-00 experiment configuration that will apply once PAPER
admissions are explicitly opened.

Safety model:
- base EnvironmentFiles are supplied in exact systemd precedence order;
- the current pre-start state must remain PB_MAX_POSITIONS=0;
- capture creates a separate immutable admission overlay containing the future
  operator-selected PB_MAX_POSITIONS value, but does not wire it into systemd;
- snapshot parameters represent the final experiment configuration after that
  overlay is applied;
- secret-looking keys are never serialized;
- unset material variables are resolved from production os.getenv/environ.get
  literal defaults;
- ambiguous or non-literal unset defaults fail closed;
- snapshot and admission overlay are O_EXCL / never overwritten;
- validation re-captures the exact source/config/default surface.
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

ACTIVATION_ALLOWED_KEYS = frozenset({"PB_MAX_POSITIONS"})
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


def _module_literal_constants(tree: ast.AST) -> dict[str, Any]:
    """Resolve only module-level constants whose RHS is a pure Python literal.

    This intentionally does not execute code, follow imports, call functions, or
    evaluate expressions. It is sufficient for patterns such as:

        _DEFAULT = 0.30
        os.getenv("P8_ACTIVE_SHARPE_MIN", str(_DEFAULT))

    Anything more dynamic remains unresolved and fails closed when the
    corresponding environment variable is unset.
    """

    constants: dict[str, Any] = {}
    body = getattr(tree, "body", ())
    for node in body:
        name: str | None = None
        value_node: ast.AST | None = None

        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value_node = node.value

        if not name or value_node is None:
            continue

        try:
            constants[name] = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            continue

    return constants


def _literal_default(
    node: ast.AST | None,
    module_constants: dict[str, Any],
) -> tuple[bool, Any]:
    if node is None:
        return True, None

    try:
        return True, ast.literal_eval(node)
    except (ValueError, TypeError):
        pass

    if isinstance(node, ast.Name) and node.id in module_constants:
        return True, module_constants[node.id]

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"str", "int", "float", "bool"}
        and len(node.args) == 1
        and not node.keywords
    ):
        ok, value = _literal_default(node.args[0], module_constants)
        if not ok:
            return False, None
        try:
            converter = {"str": str, "int": int, "float": float, "bool": bool}[
                node.func.id
            ]
            return True, converter(value)
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

    if func.attr == "getenv" and isinstance(func.value, ast.Name):
        return func.value.id in os_names

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
        module_constants = _module_literal_constants(tree)
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

            ok, value = _literal_default(default_node, module_constants)
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


def _resolve_parameters(
    *,
    explicit: dict[str, str],
    explicit_source: dict[str, str],
    defaults: dict[str, list[DefaultCandidate]],
    unresolved_defaults: dict[str, list[str]],
) -> dict[str, Any]:
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

        parameters[key] = {
            "value": values[0],
            "provenance": "CODE_DEFAULT",
            "source": "runtime_source_sha",
            "callsites": callsites,
        }

    return parameters


def _require_value(parameters: dict[str, Any], key: str, expected: str) -> None:
    record = parameters.get(key)
    if record is None or str(record["value"]).lower() != expected.lower():
        raise ConfigFreezeError(
            f"required experiment invariant {key}={expected!r} is not satisfied"
        )


def _activation_bytes(pb_max_positions: int) -> bytes:
    if pb_max_positions < 1:
        raise ConfigFreezeError("activation PB_MAX_POSITIONS must be >= 1")
    return f"PB_MAX_POSITIONS={pb_max_positions}\n".encode("utf-8")


def build_snapshot_payload(
    *,
    repo_root: Path,
    env_files: list[Path],
    paper_epoch_id: str,
    activation_path: Path,
    activation_bytes: bytes,
    snapshot_schema: str = SNAPSHOT_SCHEMA,
) -> dict[str, Any]:
    if not paper_epoch_id:
        raise ConfigFreezeError("paper_epoch_id is required")
    if not isinstance(snapshot_schema, str) or not snapshot_schema.strip():
        raise ConfigFreezeError("snapshot_schema is required")

    runtime_source_sha = _require_clean_repo(repo_root)
    prestart_explicit, prestart_source = _effective_explicit(env_files, repo_root)
    defaults, unresolved_defaults = _discover_defaults(repo_root)

    prestart_parameters = _resolve_parameters(
        explicit=prestart_explicit,
        explicit_source=prestart_source,
        defaults=defaults,
        unresolved_defaults=unresolved_defaults,
    )

    _require_value(
        prestart_parameters,
        "PAPER_LIFECYCLE_AUTHORITY",
        "PPL_AUTHORITY",
    )
    _require_value(prestart_parameters, "PAPER_TRADING_ENABLED", "true")
    _require_value(prestart_parameters, "PB_MAX_POSITIONS", "0")
    _require_value(
        prestart_parameters,
        "PPL_AUTHORITY_EPOCH_ID",
        paper_epoch_id,
    )

    try:
        activation_text = activation_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ConfigFreezeError("activation overlay is not UTF-8") from exc

    activation_values: dict[str, str] = {}
    for line in activation_text.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise ConfigFreezeError("malformed activation overlay")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in ACTIVATION_ALLOWED_KEYS:
            raise ConfigFreezeError(
                f"activation overlay may not change material parameter {key!r}"
            )
        activation_values[key] = value

    if set(activation_values) != ACTIVATION_ALLOWED_KEYS:
        raise ConfigFreezeError(
            "activation overlay must contain exactly PB_MAX_POSITIONS"
        )
    try:
        planned_pb = int(activation_values["PB_MAX_POSITIONS"])
    except ValueError as exc:
        raise ConfigFreezeError("activation PB_MAX_POSITIONS must be an integer") from exc
    if planned_pb < 1:
        raise ConfigFreezeError("activation PB_MAX_POSITIONS must be >= 1")

    final_explicit = dict(prestart_explicit)
    final_source = dict(prestart_source)
    activation_ref = _normalise_path(activation_path, repo_root)
    for key, value in activation_values.items():
        final_explicit[key] = value
        final_source[key] = activation_ref

    parameters = _resolve_parameters(
        explicit=final_explicit,
        explicit_source=final_source,
        defaults=defaults,
        unresolved_defaults=unresolved_defaults,
    )

    _require_value(parameters, "PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    _require_value(parameters, "PAPER_TRADING_ENABLED", "true")
    _require_value(parameters, "PPL_AUTHORITY_EPOCH_ID", paper_epoch_id)
    _require_value(parameters, "PB_MAX_POSITIONS", str(planned_pb))

    env_refs = [_normalise_path(path, repo_root) for path in env_files]

    return {
        "snapshot_schema": snapshot_schema,
        "paper_epoch_id": paper_epoch_id,
        "runtime_source_sha": runtime_source_sha,
        "prestart_environment_files_in_precedence_order": env_refs,
        "activation_overlay": {
            "path": activation_ref,
            "sha256": hashlib.sha256(activation_bytes).hexdigest(),
            "allowed_keys": sorted(ACTIVATION_ALLOWED_KEYS),
            "overrides": dict(sorted(activation_values.items())),
            "must_not_be_wired_before_owner_authorization": True,
        },
        "prestart_guard": {
            "PB_MAX_POSITIONS": "0",
        },
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
    activation_output: Path,
    activation_pb_max_positions: int,
    snapshot_schema: str = SNAPSHOT_SCHEMA,
) -> dict[str, Any]:
    if output.exists():
        raise ConfigFreezeError(
            f"snapshot already exists and will not be overwritten: {output}"
        )
    if activation_output.exists():
        raise ConfigFreezeError(
            "activation overlay already exists and will not be overwritten: "
            f"{activation_output}"
        )

    activation_bytes = _activation_bytes(activation_pb_max_positions)
    payload = build_snapshot_payload(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
        activation_path=activation_output,
        activation_bytes=activation_bytes,
        snapshot_schema=snapshot_schema,
    )
    document = _snapshot_document(payload)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"

    _write_exclusive(activation_output, activation_bytes)
    try:
        _write_exclusive(output, encoded)
    except Exception:
        try:
            activation_output.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return document


def validate(
    *,
    repo_root: Path,
    snapshot_path: Path,
    snapshot_schema: str = SNAPSHOT_SCHEMA,
) -> dict[str, Any]:
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
            f"snapshot content hash mismatch: stored={stored_hash} "
            f"actual={actual_stored_hash}"
        )
    if document.get("snapshot_schema") != snapshot_schema:
        raise ConfigFreezeError(
            f"unsupported snapshot schema: {document.get('snapshot_schema')!r}; "
            f"expected {snapshot_schema!r}"
        )

    env_refs = document.get("prestart_environment_files_in_precedence_order")
    if not isinstance(env_refs, list) or not env_refs:
        raise ConfigFreezeError("snapshot prestart environment file list is missing")
    env_files = [
        Path(item) if Path(item).is_absolute() else repo_root / item
        for item in env_refs
        if isinstance(item, str) and item
    ]
    if len(env_files) != len(env_refs):
        raise ConfigFreezeError("snapshot prestart environment file list is malformed")

    activation = document.get("activation_overlay")
    if not isinstance(activation, dict):
        raise ConfigFreezeError("snapshot activation overlay metadata is missing")
    activation_ref = activation.get("path")
    activation_hash = activation.get("sha256")
    if not isinstance(activation_ref, str) or not activation_ref:
        raise ConfigFreezeError("snapshot activation overlay path is missing")
    if not isinstance(activation_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", activation_hash
    ):
        raise ConfigFreezeError("snapshot activation overlay SHA-256 is malformed")

    activation_path = (
        Path(activation_ref)
        if Path(activation_ref).is_absolute()
        else repo_root / activation_ref
    )
    try:
        activation_bytes = activation_path.read_bytes()
    except OSError as exc:
        raise ConfigFreezeError(
            f"cannot read activation overlay {activation_path}: {exc}"
        ) from exc
    if hashlib.sha256(activation_bytes).hexdigest() != activation_hash:
        raise ConfigFreezeError("activation overlay hash mismatch")

    paper_epoch_id = document.get("paper_epoch_id")
    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise ConfigFreezeError("snapshot paper_epoch_id is missing")

    current = build_snapshot_payload(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
        activation_path=activation_path,
        activation_bytes=activation_bytes,
        snapshot_schema=snapshot_schema,
    )
    current_hash = snapshot_sha256(current)
    if current != document or current_hash != stored_hash:
        raise ConfigFreezeError(
            "effective experiment configuration differs from frozen snapshot: "
            f"frozen={stored_hash} current={current_hash}"
        )

    return {
        "snapshot_sha256": stored_hash,
        "activation_sha256": activation_hash,
        "paper_epoch_id": paper_epoch_id,
        "runtime_source_sha": current["runtime_source_sha"],
        "material_parameter_count": current["material_parameter_count"],
        "planned_pb_max_positions": current["activation_overlay"]["overrides"][
            "PB_MAX_POSITIONS"
        ],
    }


def _default_output(repo_root: Path, epoch: str) -> Path:
    return (
        repo_root
        / "databases"
        / "ppl_authority"
        / f"{epoch}.experiment-config.json"
    )


def _default_activation_output(repo_root: Path, epoch: str) -> Path:
    return (
        repo_root
        / "databases"
        / "ppl_authority"
        / f"{epoch}.admission.env"
    )


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
        help="active pre-start EnvironmentFile in exact precedence order",
    )
    cap.add_argument(
        "--activation-pb-max-positions",
        type=int,
        required=True,
        help=(
            "future PB_MAX_POSITIONS to freeze in an inactive admission overlay; "
            "capture does not wire or activate it"
        ),
    )
    cap.add_argument("--output", default=None)
    cap.add_argument("--activation-output", default=None)

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
            activation_output = (
                Path(args.activation_output)
                if args.activation_output
                else _default_activation_output(repo_root, args.epoch)
            )
            if not output.is_absolute():
                output = repo_root / output
            if not activation_output.is_absolute():
                activation_output = repo_root / activation_output

            doc = capture(
                repo_root=repo_root,
                env_files=env_files,
                paper_epoch_id=args.epoch,
                output=output,
                activation_output=activation_output,
                activation_pb_max_positions=args.activation_pb_max_positions,
            )
            explicit_count = sum(
                1
                for item in doc["parameters"].values()
                if item["provenance"] == "EXPLICIT_ENVIRONMENT_FILE"
            )
            default_count = doc["material_parameter_count"] - explicit_count
            print(f"SNAPSHOT_PATH={_normalise_path(output, repo_root)}")
            print(f"SNAPSHOT_SHA256={doc['snapshot_sha256']}")
            print(
                "ACTIVATION_OVERLAY_PATH="
                + doc["activation_overlay"]["path"]
            )
            print(
                "ACTIVATION_OVERLAY_SHA256="
                + doc["activation_overlay"]["sha256"]
            )
            print(
                "PLANNED_PB_MAX_POSITIONS="
                + doc["activation_overlay"]["overrides"]["PB_MAX_POSITIONS"]
            )
            print(f"RUNTIME_SOURCE_SHA={doc['runtime_source_sha']}")
            print(f"PAPER_EPOCH_ID={doc['paper_epoch_id']}")
            print(f"MATERIAL_PARAMETER_COUNT={doc['material_parameter_count']}")
            print(f"EXPLICIT_PARAMETER_COUNT={explicit_count}")
            print(f"CODE_DEFAULT_PARAMETER_COUNT={default_count}")
            print("ACTIVATION_OVERLAY_WIRED=NO")
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
        print(f"ACTIVATION_OVERLAY_SHA256={result['activation_sha256']}")
        print(f"PLANNED_PB_MAX_POSITIONS={result['planned_pb_max_positions']}")
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
