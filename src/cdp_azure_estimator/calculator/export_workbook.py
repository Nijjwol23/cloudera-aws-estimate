from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from cdp_azure_estimator.models import (
    AdlsStorageService,
    AksService,
    EstimateManifest,
    GenericAzureService,
    MysqlFlexibleService,
    PostgresFlexibleService,
    VmService,
)


def _service_rows(manifest: EstimateManifest) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in manifest.groups:
        for service in group.services:
            base = {
                "estimate_group": group.name,
                "region": manifest.region,
                "sheet_azure_cost": getattr(service, "sheet_azure_cost", None),
            }
            if isinstance(service, VmService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Virtual Machines",
                        "description": service.description,
                        "sku": service.vm_size,
                        "quantity": service.quantity,
                        "hours_per_month": service.hours_per_month,
                        "managed_disks": ", ".join(
                            f"{disk.sku} x{disk.size_or_count}" for disk in service.managed_disks
                        ),
                    }
                )
            elif isinstance(service, AksService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Azure Kubernetes Service (AKS)",
                        "description": service.description,
                        "sku": "Standard",
                        "quantity": service.clusters,
                        "hours_per_month": service.hours_per_month,
                        "managed_disks": "",
                    }
                )
            elif isinstance(service, PostgresFlexibleService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Azure Database for PostgreSQL",
                        "description": service.description,
                        "sku": service.compute_sku,
                        "quantity": service.quantity,
                        "hours_per_month": service.hours_per_month,
                        "managed_disks": "",
                    }
                )
            elif isinstance(service, MysqlFlexibleService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Azure Database for MySQL",
                        "description": service.description,
                        "sku": service.compute_sku,
                        "quantity": service.quantity,
                        "hours_per_month": service.hours_per_month,
                        "managed_disks": "",
                    }
                )
            elif isinstance(service, AdlsStorageService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Storage (Data Lake Storage Gen2)",
                        "description": service.description,
                        "sku": "ADLS Gen2",
                        "quantity": service.storage_tb,
                        "hours_per_month": 730,
                        "managed_disks": f"{service.storage_tb} TB",
                    }
                )
            elif isinstance(service, GenericAzureService):
                rows.append(
                    {
                        **base,
                        "calculator_product": "Other (manual mapping)",
                        "description": service.description,
                        "sku": service.resource_type,
                        "quantity": service.quantity,
                        "hours_per_month": service.hours_per_month,
                        "managed_disks": "",
                    }
                )
    return rows


def write_calculator_import_workbook(manifest: EstimateManifest, path: str | Path) -> Path:
    """Workbook to speed up manual entry at azure.microsoft.com/pricing/calculator/."""
    output = Path(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Azure Calculator Import"

    headers = [
        "Estimate Group",
        "Calculator Product",
        "Description",
        "Region",
        "SKU / Size",
        "Quantity",
        "Hours/Month",
        "Managed Disks",
        "Sheet Azure Cost (USD)",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in _service_rows(manifest):
        ws.append(
            [
                row["estimate_group"],
                row["calculator_product"],
                row["description"],
                row["region"],
                row["sku"],
                row["quantity"],
                row["hours_per_month"],
                row["managed_disks"],
                row["sheet_azure_cost"],
            ]
        )

    readme = wb.create_sheet("README")
    readme["A1"] = "Azure Pricing Calculator has no official import API."
    readme["A2"] = "Use this sheet to add products at https://azure.microsoft.com/pricing/calculator/"
    readme["A3"] = "Group names match the Cloudera Summary; costs are for cross-check only."
    readme["A4"] = f"Estimate title suggestion: {manifest.name}"

    wb.save(output)
    return output
