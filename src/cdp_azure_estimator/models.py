from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ManagedDiskVolume:
    sku: str
    size_or_count: float


@dataclass
class ResourceRow:
    purpose: str | None
    resource_type: str
    count: float
    hours: float
    azure_cost: float | None = None
    row: int = 0


@dataclass
class VmService:
    description: str
    vm_size: str
    quantity: float
    hours_per_month: float
    managed_disks: list[ManagedDiskVolume] = field(default_factory=list)
    sheet_azure_cost: float | None = None


@dataclass
class AksService:
    description: str
    clusters: float = 1.0
    hours_per_month: float = 730.0
    sheet_azure_cost: float | None = None


@dataclass
class PostgresFlexibleService:
    description: str
    compute_sku: str
    quantity: float = 1.0
    hours_per_month: float = 730.0
    sheet_azure_cost: float | None = None


@dataclass
class MysqlFlexibleService:
    description: str
    compute_sku: str
    quantity: float = 1.0
    hours_per_month: float = 730.0
    sheet_azure_cost: float | None = None


@dataclass
class AdlsStorageService:
    description: str
    storage_tb: float
    sheet_azure_cost: float | None = None


@dataclass
class GenericAzureService:
    description: str
    resource_type: str
    quantity: float
    hours_per_month: float
    sheet_azure_cost: float | None = None


CalculatorService = (
    VmService
    | AksService
    | PostgresFlexibleService
    | MysqlFlexibleService
    | AdlsStorageService
    | GenericAzureService
)


@dataclass
class EstimateGroup:
    name: str
    source_tab: str
    services: list[CalculatorService] = field(default_factory=list)
    sheet_azure_total: float | None = None


@dataclass
class EstimateManifest:
    customer: str
    name: str
    region: str
    groups: list[EstimateGroup] = field(default_factory=list)

    @property
    def sheet_azure_total(self) -> float:
        return sum(g.sheet_azure_total or 0 for g in self.groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer": self.customer,
            "name": self.name,
            "region": self.region,
            "cloud": "azure",
            "sheet_azure_total": self.sheet_azure_total,
            "groups": [group_to_dict(g) for g in self.groups],
        }


def group_to_dict(group: EstimateGroup) -> dict[str, Any]:
    return {
        "name": group.name,
        "source_tab": group.source_tab,
        "sheet_azure_total": group.sheet_azure_total,
        "services": [service_to_dict(s) for s in group.services],
    }


def service_to_dict(service: CalculatorService) -> dict[str, Any]:
    if isinstance(service, VmService):
        return {
            "type": "vm",
            "description": service.description,
            "vm_size": service.vm_size,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "managed_disks": [
                {"sku": disk.sku, "size_or_count": disk.size_or_count}
                for disk in service.managed_disks
            ],
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    if isinstance(service, AksService):
        return {
            "type": "aks",
            "description": service.description,
            "clusters": service.clusters,
            "hours_per_month": service.hours_per_month,
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    if isinstance(service, PostgresFlexibleService):
        return {
            "type": "postgres_flexible",
            "description": service.description,
            "compute_sku": service.compute_sku,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    if isinstance(service, MysqlFlexibleService):
        return {
            "type": "mysql_flexible",
            "description": service.description,
            "compute_sku": service.compute_sku,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    if isinstance(service, AdlsStorageService):
        return {
            "type": "adls",
            "description": service.description,
            "storage_tb": service.storage_tb,
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    if isinstance(service, GenericAzureService):
        return {
            "type": "generic",
            "description": service.description,
            "resource_type": service.resource_type,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "sheet_azure_cost": service.sheet_azure_cost,
        }
    raise TypeError(f"Unknown service type: {type(service)}")
