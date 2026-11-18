from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALIASES_PATH = PACKAGE_ROOT / "config" / "azure_aliases.yaml"


@lru_cache(maxsize=1)
def load_aliases(path: str | Path | None = None) -> dict[str, str]:
    aliases_path = Path(path) if path else DEFAULT_ALIASES_PATH
    with aliases_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return {str(k): str(v) for k, v in data.items()}


def alias_purpose(purpose: str | None, aliases: dict[str, str] | None = None) -> str:
    if not purpose:
        return "Unknown"
    raw = purpose.strip()
    mapping = aliases or load_aliases()
    if raw in mapping:
        return mapping[raw]
    return raw.rstrip("*").strip()


def normalize_tab_name(name: str) -> str:
    return name.strip()


_DATAHUB_TAB_EXCLUDE = frozenset({"cldr pricing - dh", "cldr pricing - all", "cldr pricing - flow"})


def is_datahub_tab(name: str) -> bool:
    normalized = normalize_tab_name(name).lower()
    if normalized in _DATAHUB_TAB_EXCLUDE:
        return False
    if normalized.startswith("datahub") or normalized == "data hub":
        return True
    return normalized.endswith(" dh")


def datahub_group_name(tab_name: str, template_name: str) -> str:
    return f"Data Hub - {template_name}"


def datahub_template_from_tab(tab_name: str, cell_a1: str | None) -> str:
    if cell_a1 and str(cell_a1).strip():
        return str(cell_a1).strip()
    suffix = normalize_tab_name(tab_name)
    if suffix.lower().startswith("datahub"):
        suffix = suffix[7:].strip()
    return suffix or tab_name


def to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "" or value == "-":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default
