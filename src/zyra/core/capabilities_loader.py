# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

INDEX_FILENAME = "zyra_capabilities_index.json"


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Capabilities manifest at {path} is not a JSON object.")
    return data


def _discover_domain_files(
    directory: Path, index_path: Path | None = None
) -> tuple[dict[str, Path], dict[str, str]]:
    """Return mapping of canonical domains to files plus alias map."""

    def _from_glob() -> tuple[dict[str, Path], dict[str, str]]:
        files: dict[str, Path] = {}
        for child in directory.glob("*.json"):
            if child.name == INDEX_FILENAME:
                continue
            files[child.stem] = child
        return files, {}

    if index_path is None:
        index_path = directory / INDEX_FILENAME

    if not index_path.exists():
        return _from_glob()

    index = _read_json(index_path)
    domains = index.get("domains") or {}
    if not isinstance(domains, dict):
        raise ValueError(f"Invalid domains entry in {index_path}")

    files: dict[str, Path] = {}
    aliases: dict[str, str] = {}

    for raw_domain, value in sorted(domains.items()):
        domain = str(raw_domain).strip()
        if isinstance(value, str):
            rel_path = value
            alias_list: list[str] = []
        elif isinstance(value, dict):
            rel_path = value.get("file") or value.get("path")
            alias_val = value.get("aliases") or []
            alias_list = [str(a).strip() for a in alias_val if str(a).strip()]
        else:
            raise ValueError(f"Invalid domain entry for {domain} in {index_path}")
        if not rel_path:
            raise ValueError(f"Missing file path for domain {domain} in {index_path}")
        target = (index_path.parent / str(rel_path)).resolve()
        files[domain] = target
        for alias in alias_list:
            aliases[_normalize_key(alias)] = domain

    # Merge top-level aliases (if provided)
    top_aliases = index.get("aliases") or {}
    if isinstance(top_aliases, dict):
        for alias, target in top_aliases.items():
            aliases[_normalize_key(str(alias))] = str(target).strip()

    return files, aliases


def _read_domain_file(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    # Ensure deterministic ordering for callers by sorting command keys
    return {k: data[k] for k in sorted(data.keys())}


def load_domains(
    manifest_path: Path | str, domain: str | None = None
) -> dict[str, dict[str, Any]]:
    """Load per-domain manifest data from a directory, index file, or JSON blob."""

    path = Path(manifest_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Capabilities manifest path not found: {path}")

    if path.is_dir():
        return _load_from_directory(path, domain)

    if path.name == INDEX_FILENAME:
        return _load_from_directory(path.parent, domain, index_path=path)

    data = _read_json(path)
    return _group_manifest_dict(data, domain=domain)


def _load_from_directory(
    directory: Path, domain: str | None, index_path: Path | None = None
) -> dict[str, dict[str, Any]]:
    domain_files, aliases = _discover_domain_files(directory, index_path=index_path)
    if domain:
        canonical = aliases.get(_normalize_key(domain), domain)
        path = domain_files.get(canonical)
        if not path:
            return {}
        return {canonical: _read_domain_file(path)}

    result: dict[str, dict[str, Any]] = {}
    for dom in sorted(domain_files.keys()):
        result[dom] = _read_domain_file(domain_files[dom])
    return result


def _group_manifest_dict(
    manifest: dict[str, Any], domain: str | None = None
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for command, meta in manifest.items():
        if not isinstance(command, str):
            continue
        key = command.split(" ", 1)[0]
        grouped.setdefault(key, {})[command] = meta

    if domain:
        return {domain: grouped.get(domain, {})} if domain in grouped else {}
    return {k: grouped[k] for k in sorted(grouped.keys())}


def load_capabilities(
    manifest_path: Path | str, domain: str | None = None
) -> dict[str, Any]:
    """Return merged manifest data, optionally restricted to a domain or alias."""

    domains = load_domains(manifest_path, domain=domain)
    combined: dict[str, Any] = {}
    for dom in sorted(domains.keys()):
        combined.update(domains[dom])
    return combined


def compute_capabilities_hash(capabilities: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hash of a manifest dictionary."""

    payload = json.dumps(
        capabilities,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "INDEX_FILENAME",
    "compute_capabilities_hash",
    "load_capabilities",
    "load_domains",
]
