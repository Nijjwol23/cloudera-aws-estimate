from __future__ import annotations

from cdp_aws_estimator.models import (
    CalculatorService,
    EbsVolume,
    Ec2Service,
    EfsService,
    EksService,
    RdsService,
    ResourceRow,
)
from cdp_aws_estimator.transform.aliases import (
    alias_purpose,
    is_ebs_type,
    is_ec2_instance_type,
    parse_rds_type,
)


def rows_to_services(rows: list[ResourceRow], aliases: dict[str, str]) -> list[CalculatorService]:
    services: list[CalculatorService] = []
    current_purpose: str | None = None
    block_rows: list[ResourceRow] = []

    def flush_block() -> None:
        nonlocal block_rows, current_purpose
        if not block_rows:
            return
        service = block_to_service(block_rows, current_purpose, aliases)
        if service is not None:
            if isinstance(service, list):
                services.extend(service)
            else:
                services.append(service)
        block_rows = []

    for row in rows:
        if row.purpose and row.purpose != current_purpose:
            flush_block()
            current_purpose = row.purpose
        elif row.purpose and current_purpose is None:
            current_purpose = row.purpose
        block_rows.append(row)
    flush_block()
    return services


def block_to_service(
    rows: list[ResourceRow],
    purpose: str | None,
    aliases: dict[str, str],
) -> CalculatorService | list[CalculatorService] | None:
    if not rows:
        return None

    description = alias_purpose(purpose or rows[0].purpose, aliases)
    ec2_row: ResourceRow | None = None
    ebs_volumes: list[EbsVolume] = []
    instance_store_gb = 0.0
    managed: list[CalculatorService] = []
    aws_cost = 0.0
    has_cost = False

    for row in rows:
        rtype = row.resource_type
        if row.aws_cost is not None:
            aws_cost += float(row.aws_cost)
            has_cost = True

        if rtype == "AmazonEKS":
            managed.append(
                EksService(
                    description=description if description != "Unknown" else "Kubernetes Cluster",
                    clusters=row.count,
                    hours_per_month=row.hours,
                    sheet_aws_cost=row.aws_cost,
                )
            )
            continue

        if rtype == "AmazonEFS":
            managed.append(
                EfsService(
                    description=description,
                    size_gb=row.count,
                    hours_per_month=row.hours,
                    sheet_aws_cost=row.aws_cost,
                )
            )
            continue

        parsed_rds = parse_rds_type(rtype)
        if parsed_rds:
            instance_class, engine, multi_az = parsed_rds
            managed.append(
                RdsService(
                    description=description if "Database" in description or "RDS" in (purpose or "") else "Database",
                    instance_class=instance_class,
                    engine=engine,
                    multi_az=multi_az,
                    quantity=row.count,
                    hours_per_month=row.hours,
                    sheet_aws_cost=row.aws_cost,
                )
            )
            continue

        if is_ec2_instance_type(rtype):
            ec2_row = row
            continue

        if is_ebs_type(rtype):
            ebs_volumes.append(EbsVolume(volume_type=rtype, size_gb=row.count))
            continue

        if rtype == "ephemeral":
            instance_store_gb += row.count

    if managed:
        if ec2_row or ebs_volumes or instance_store_gb:
            ec2 = build_ec2_service(
                ec2_row,
                ebs_volumes,
                instance_store_gb,
                description,
                aws_cost if has_cost and ec2_row else None,
            )
            if ec2:
                managed.insert(0, ec2)
        return managed

    ec2 = build_ec2_service(ec2_row, ebs_volumes, instance_store_gb, description, aws_cost if has_cost else None)
    return ec2


def build_ec2_service(
    ec2_row: ResourceRow | None,
    ebs_volumes: list[EbsVolume],
    instance_store_gb: float,
    description: str,
    sheet_aws_cost: float | None,
) -> Ec2Service | None:
    if ec2_row is None:
        return None
    merged_ebs: dict[str, float] = {}
    for volume in ebs_volumes:
        merged_ebs[volume.volume_type] = merged_ebs.get(volume.volume_type, 0.0) + volume.size_gb
    return Ec2Service(
        description=description,
        instance_type=ec2_row.resource_type,
        quantity=ec2_row.count,
        hours_per_month=ec2_row.hours,
        ebs_volumes=[
            EbsVolume(volume_type=volume_type, size_gb=size_gb)
            for volume_type, size_gb in merged_ebs.items()
        ],
        instance_store_gb=instance_store_gb,
        sheet_aws_cost=sheet_aws_cost,
    )


def sum_service_costs(services: list[CalculatorService]) -> float:
    total = 0.0
    for service in services:
        cost = getattr(service, "sheet_aws_cost", None)
        if cost is not None:
            total += float(cost)
    return total
