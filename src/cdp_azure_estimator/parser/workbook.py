from __future__ import annotations

from pathlib import Path

import openpyxl

from cdp_azure_estimator.models import EstimateManifest
from cdp_azure_estimator.parser.datalake import parse_datalake_groups
from cdp_azure_estimator.parser.datahub import parse_all_datahub_groups
from cdp_azure_estimator.parser.summary import (
    apply_summary_sheet_totals,
    discover_service_groups_from_summary,
    parse_storage_group,
    parse_summary_cluster_groups,
    parse_summary_misc_groups,
    parse_summary_region,
)
from cdp_azure_estimator.transform.aliases import load_aliases


def load_workbook(path: str | Path):
    return openpyxl.load_workbook(path, data_only=True)


def build_manifest(workbook_path: str | Path, customer: str) -> EstimateManifest:
    aliases = load_aliases()
    workbook = load_workbook(workbook_path)
    region = parse_summary_region(workbook)

    groups: list = []
    groups.extend(parse_datalake_groups(workbook, aliases))
    groups.extend(parse_all_datahub_groups(workbook, aliases))
    groups.extend(discover_service_groups_from_summary(workbook, aliases, groups))
    groups.extend(parse_summary_cluster_groups(workbook, aliases, groups))
    groups.extend(parse_summary_misc_groups(workbook, groups))

    storage = parse_storage_group(workbook)
    if storage:
        groups.append(storage)

    apply_summary_sheet_totals(workbook, groups)

    manifest = EstimateManifest(
        customer=customer,
        name=f"{customer} Pricing",
        region=region,
        groups=sorted(groups, key=lambda item: item.name),
    )
    workbook.close()
    return manifest
