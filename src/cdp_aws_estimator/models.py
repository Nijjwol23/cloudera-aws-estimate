from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EbsVolume:
    volume_type: str
    size_gb: float


@dataclass
class ResourceRow:
    purpose: str | None
    resource_type: str
    count: float
    hours: float
    aws_cost: float | None = None
    row: int = 0


@dataclass
class Ec2Service:
    description: str
    instance_type: str
    quantity: float
    hours_per_month: float
    ebs_volumes: list[EbsVolume] = field(default_factory=list)
    instance_store_gb: float = 0.0
    sheet_aws_cost: float | None = None


@dataclass
class EksService:
    description: str
    clusters: float = 1.0
    hours_per_month: float = 730.0
    sheet_aws_cost: float | None = None


@dataclass
class EfsService:
    description: str
    size_gb: float
    hours_per_month: float = 730.0
    sheet_aws_cost: float | None = None


@dataclass
class RdsService:
    description: str
    instance_class: str
    engine: str
    multi_az: bool
    quantity: float = 1.0
    hours_per_month: float = 730.0
    storage_gb: float = 100.0
    sheet_aws_cost: float | None = None


@dataclass
class S3Service:
    description: str
    standard_storage_tb: float
    sheet_aws_cost: float | None = None


CalculatorService = Ec2Service | EksService | EfsService | RdsService | S3Service


@dataclass
class EstimateGroup:
    name: str
    source_tab: str
    services: list[CalculatorService] = field(default_factory=list)
    sheet_aws_total: float | None = None


@dataclass
class EstimateManifest:
    customer: str
    name: str
    region: str
    groups: list[EstimateGroup] = field(default_factory=list)

    @property
    def sheet_aws_total(self) -> float:
        return sum(g.sheet_aws_total or 0 for g in self.groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer": self.customer,
            "name": self.name,
            "region": self.region,
            "sheet_aws_total": self.sheet_aws_total,
            "groups": [group_to_dict(g) for g in self.groups],
        }


def group_to_dict(group: EstimateGroup) -> dict[str, Any]:
    return {
        "name": group.name,
        "source_tab": group.source_tab,
        "sheet_aws_total": group.sheet_aws_total,
        "services": [service_to_dict(s) for s in group.services],
    }


def service_to_dict(service: CalculatorService) -> dict[str, Any]:
    if isinstance(service, Ec2Service):
        return {
            "type": "ec2",
            "description": service.description,
            "instance_type": service.instance_type,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "ebs_volumes": [
                {"volume_type": v.volume_type, "size_gb": v.size_gb}
                for v in service.ebs_volumes
            ],
            "instance_store_gb": service.instance_store_gb,
            "sheet_aws_cost": service.sheet_aws_cost,
        }
    if isinstance(service, EksService):
        return {
            "type": "eks",
            "description": service.description,
            "clusters": service.clusters,
            "hours_per_month": service.hours_per_month,
            "sheet_aws_cost": service.sheet_aws_cost,
        }
    if isinstance(service, EfsService):
        return {
            "type": "efs",
            "description": service.description,
            "size_gb": service.size_gb,
            "hours_per_month": service.hours_per_month,
            "sheet_aws_cost": service.sheet_aws_cost,
        }
    if isinstance(service, RdsService):
        return {
            "type": "rds",
            "description": service.description,
            "instance_class": service.instance_class,
            "engine": service.engine,
            "multi_az": service.multi_az,
            "quantity": service.quantity,
            "hours_per_month": service.hours_per_month,
            "storage_gb": service.storage_gb,
            "sheet_aws_cost": service.sheet_aws_cost,
        }
    if isinstance(service, S3Service):
        return {
            "type": "s3",
            "description": service.description,
            "standard_storage_tb": service.standard_storage_tb,
            "sheet_aws_cost": service.sheet_aws_cost,
        }
    raise TypeError(f"Unknown service type: {type(service)}")
