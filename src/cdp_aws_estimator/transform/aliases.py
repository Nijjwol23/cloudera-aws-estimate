from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

EC2_PATTERN = re.compile(
    r"^(?:"
    r"[a-z]\d+[a-z0-9]*\.(?:nano|micro|small|medium|large|xlarge|\d+xlarge|metal)"
    r"|[a-z]+\d+[a-z0-9]*\.(?:nano|micro|small|medium|large|xlarge|\d+xlarge|metal)"
    r")$"
)
EBS_TYPES = frozenset({"gp3", "gp2", "standard", "st1", "sc1", "io1", "io2"})
RDS_PATTERN = re.compile(
    r"^(?P<class>db\.[^-]+)-(?P<engine>PostgreSQL|MySQL)-(?P<az>Single-AZ|Multi-AZ)$"
)

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALIASES_PATH = PACKAGE_ROOT / "config" / "aliases.yaml"


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


def is_ec2_instance_type(resource_type: str) -> bool:
    return bool(EC2_PATTERN.match(resource_type))


def is_ebs_type(resource_type: str) -> bool:
    return resource_type in EBS_TYPES


def parse_rds_type(resource_type: str) -> tuple[str, str, bool] | None:
    match = RDS_PATTERN.match(resource_type)
    if not match:
        return None
    return (
        match.group("class"),
        match.group("engine"),
        match.group("az") == "Multi-AZ",
    )


def normalize_tab_name(name: str) -> str:
    return name.strip()


_DATAHUB_TAB_EXCLUDE = frozenset(
    {
        "cldr pricing - dh",
    }
)


def is_datahub_tab(name: str) -> bool:
    normalized = normalize_tab_name(name).lower()
    if normalized in _DATAHUB_TAB_EXCLUDE:
        return False
    if normalized.startswith("datahub") or normalized == "data hub":
        return True
    # Workbooks often name Data Hub tabs "{Template} DH" instead of "Datahub …"
    return normalized.endswith(" dh")


def datahub_group_name(tab_name: str, template_name: str) -> str:
    return f"Data Hub - {template_name}"


def datahub_template_from_tab(tab_name: str, cell_a1: str | None) -> str:
    if cell_a1 and str(cell_a1).strip():
        return str(cell_a1).strip()
    suffix = normalize_tab_name(tab_name)
    if suffix.lower().startswith("datahub"):
        suffix = suffix[7:].strip()
    if suffix:
        return suffix
    return tab_name


def to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "" or value == "-":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default
