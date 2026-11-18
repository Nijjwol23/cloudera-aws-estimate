from __future__ import annotations

from cdp_azure_estimator.models import (
    AksService,
    CalculatorService,
    GenericAzureService,
    ManagedDiskVolume,
    MysqlFlexibleService,
    PostgresFlexibleService,
    ResourceRow,
    VmService,
)
from cdp_azure_estimator.transform.aliases import alias_purpose
from cdp_azure_estimator.transform.azure_skus import (
    is_aks_cluster,
    is_managed_disk_sku,
    is_mysql_flexible,
    is_postgres_flexible,
    is_vm_size,
    normalize_vm_size,
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
    vm_row: ResourceRow | None = None
    managed_disks: list[ManagedDiskVolume] = []
    azure_cost = 0.0
    has_cost = False
    managed: list[CalculatorService] = []

    for row in rows:
        rtype = row.resource_type
        if row.azure_cost is not None:
            azure_cost += float(row.azure_cost)
            has_cost = True

        if is_aks_cluster(rtype, purpose or row.purpose):
            managed.append(
                AksService(
                    description=description,
                    clusters=row.count,
                    hours_per_month=row.hours,
                    sheet_azure_cost=row.azure_cost,
                )
            )
            continue

        if is_postgres_flexible(rtype, purpose or row.purpose):
            managed.append(
                PostgresFlexibleService(
                    description=description if "database" in description.lower() else "PostgreSQL",
                    compute_sku=rtype,
                    quantity=row.count,
                    hours_per_month=row.hours,
                    sheet_azure_cost=row.azure_cost,
                )
            )
            continue

        if is_mysql_flexible(rtype, purpose or row.purpose):
            managed.append(
                MysqlFlexibleService(
                    description=description if "database" in description.lower() else "MySQL",
                    compute_sku=rtype,
                    quantity=row.count,
                    hours_per_month=row.hours,
                    sheet_azure_cost=row.azure_cost,
                )
            )
            continue

        if is_vm_size(rtype):
            vm_row = row
            continue

        if is_managed_disk_sku(rtype):
            managed_disks.append(ManagedDiskVolume(sku=rtype, size_or_count=row.count))
            continue

        managed.append(
            GenericAzureService(
                description=description,
                resource_type=rtype,
                quantity=row.count,
                hours_per_month=row.hours,
                sheet_azure_cost=row.azure_cost,
            )
        )

    if managed and not vm_row and not managed_disks:
        return managed

    vm = build_vm_service(
        vm_row,
        managed_disks,
        description,
        azure_cost if has_cost and vm_row else None,
    )
    if vm and managed:
        return [vm, *managed]
    if vm:
        return vm
    if managed:
        return managed
    return None


def build_vm_service(
    vm_row: ResourceRow | None,
    managed_disks: list[ManagedDiskVolume],
    description: str,
    sheet_azure_cost: float | None,
) -> VmService | None:
    if vm_row is None:
        return None
    merged: dict[str, float] = {}
    for disk in managed_disks:
        merged[disk.sku] = merged.get(disk.sku, 0.0) + disk.size_or_count
    return VmService(
        description=description,
        vm_size=normalize_vm_size(vm_row.resource_type),
        quantity=vm_row.count,
        hours_per_month=vm_row.hours,
        managed_disks=[
            ManagedDiskVolume(sku=sku, size_or_count=size)
            for sku, size in merged.items()
        ],
        sheet_azure_cost=sheet_azure_cost,
    )


def sum_service_costs(services: list[CalculatorService]) -> float:
    total = 0.0
    for service in services:
        cost = getattr(service, "sheet_azure_cost", None)
        if cost is not None:
            total += float(cost)
    return total
