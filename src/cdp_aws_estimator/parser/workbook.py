from __future__ import annotations

from pathlib import Path

import openpyxl

from cdp_aws_estimator.models import EstimateManifest
from cdp_aws_estimator.parser.datahub import parse_all_datahub_groups
from cdp_aws_estimator.parser.summary import (
    apply_summary_sheet_totals,
    discover_service_tabs,
    parse_datalake_groups,
    parse_service_tab,
    parse_storage_group,
    parse_summary_cluster_groups,
    parse_summary_misc_groups,
    parse_summary_region,
)
from cdp_aws_estimator.transform.aliases import load_aliases


def load_workbook(path: str | Path):
    return openpyxl.load_workbook(path, data_only=True)


def build_manifest(workbook_path: str | Path, customer: str) -> EstimateManifest:
    aliases = load_aliases()
    workbook = load_workbook(workbook_path)
    region = parse_summary_region(workbook)

    groups = []
    groups.extend(parse_datalake_groups(workbook, aliases))

    for tab_name, group_name in discover_service_tabs(workbook):
        group = parse_service_tab(workbook, tab_name, group_name, aliases)
        if group and group.services:
            groups.append(group)

    groups.extend(parse_all_datahub_groups(workbook, aliases))

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
