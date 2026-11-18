from __future__ import annotations

import re

VM_SIZE_PATTERN = re.compile(
    r"^(?:Standard_)?(?:"
    r"[A-Z]\d+[a-z]?\s*v\d+(?:_\d+)?|"  # D4s v5, F16s v2
    r"[A-Z]\d+[a-z]?\s*v\d+"  # D8s v3
    r")$",
    re.IGNORECASE,
)

VM_SIZE_COMPACT = re.compile(
    r"^[A-Z]\d+[a-z]?\s*v\d+(?:_\d+)?$",
    re.IGNORECASE,
)

MANAGED_DISK_PATTERN = re.compile(
    r"^(?:Standard_)?(?:[EPPS]\d+|S\d+|P\d+)\s*(?:LRS|ZRS|GRS)?$",
    re.IGNORECASE,
)

DISK_SKU_PATTERN = re.compile(
    r"^[EPPS]\d+\s+LRS$|^[EPPS]\d+\s+ZRS$|^S\d+\s+LRS$|^P\d+\s+LRS$",
    re.IGNORECASE,
)


def normalize_vm_size(resource_type: str) -> str:
    raw = resource_type.strip()
    if raw.lower().startswith("standard_"):
        return raw
    compact = raw.replace(" ", "_")
    return f"Standard_{compact}"


def is_vm_size(resource_type: str) -> bool:
    raw = resource_type.strip()
    if raw.lower() in {"standard", "files v2"}:
        return False
    if VM_SIZE_COMPACT.match(raw):
        return True
    normalized = raw.replace("_", " ")
    return bool(VM_SIZE_PATTERN.match(normalized))


def is_managed_disk_sku(resource_type: str) -> bool:
    raw = resource_type.strip()
    if DISK_SKU_PATTERN.match(raw):
        return True
    return bool(MANAGED_DISK_PATTERN.match(raw.replace(" ", "_")))


def is_aks_cluster(resource_type: str, purpose: str | None) -> bool:
    if resource_type.strip().lower() == "standard" and purpose:
        return "kubernetes" in purpose.lower()
    return False


def is_postgres_flexible(resource_type: str, purpose: str | None) -> bool:
    combined = f"{purpose or ''} {resource_type}".lower()
    return "postgresql" in combined or "postgres" in resource_type.lower()


def is_mysql_flexible(resource_type: str, purpose: str | None) -> bool:
    combined = f"{purpose or ''} {resource_type}".lower()
    return "mysql" in combined
