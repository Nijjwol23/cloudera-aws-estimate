from __future__ import annotations

import re
from dataclasses import dataclass

from openpyxl.workbook.workbook import Workbook

from cdp_azure_estimator.models import AdlsStorageService, EstimateGroup
from cdp_azure_estimator.parser.datahub import parse_datahub_tab
from cdp_azure_estimator.parser.resource_table import (
    find_header_row,
    find_total_azure,
    is_cluster_worksheet,
    parse_resource_table,
)
from cdp_azure_estimator.transform.aliases import to_float
from cdp_azure_estimator.transform.blocks import rows_to_services, sum_service_costs

SUMMARY_BILLING_START_ROW = 9
SUMMARY_LABEL_COL = 4
SUMMARY_TAB_HINT_COL = 3
SUMMARY_AZURE_COL = 5

_SKIP_SUMMARY_LABEL_PREFIXES = (
    "total",
    "discount",
    "total año",
    "total ano",
    "only ",
)

SERVICE_TAB_MAP = {
    "CDE": "CDE - Data Engineering Data Service",
    "CDW": "CDW - Data Warehouse Data Service",
    "CDF": "CDF - Data Flow Data Service",
    "COD": "COD - Operational Database Data Service",
    "CAI - Workbench": "CAI - Workbench",
    "CAI - Inference Service": "CAI - Inference Service",
}


@dataclass(frozen=True)
class SummaryBillingRow:
    product_label: str
    azure_total: float
    tab_hint: str | None
    row: int


def parse_summary_billing_rows(workbook: Workbook) -> list[SummaryBillingRow]:
    if "Summary" not in workbook.sheetnames:
        return []
    ws = workbook["Summary"]
    rows: list[SummaryBillingRow] = []
    for row_idx in range(SUMMARY_BILLING_START_ROW, ws.max_row + 1):
        label = ws.cell(row_idx, SUMMARY_LABEL_COL).value
        azure_value = ws.cell(row_idx, SUMMARY_AZURE_COL).value
        if not label or not isinstance(azure_value, (int, float)) or azure_value <= 0:
            continue
        product_label = str(label).strip()
        normalized = normalize_summary_label(product_label)
        if any(normalized.startswith(prefix) for prefix in _SKIP_SUMMARY_LABEL_PREFIXES):
            continue
        tab_hint = ws.cell(row_idx, SUMMARY_TAB_HINT_COL).value
        hint = str(tab_hint).strip() if tab_hint and isinstance(tab_hint, str) else None
        if hint and hint.startswith("="):
            hint = None
        rows.append(
            SummaryBillingRow(
                product_label=product_label,
                azure_total=float(azure_value),
                tab_hint=hint,
                row=row_idx,
            )
        )
    return rows


def normalize_summary_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label).strip().lower().replace("*", ""))


def is_datalake_summary_label(label: str) -> bool:
    return normalize_summary_label(label).startswith("datalake")


def is_storage_summary_label(label: str) -> bool:
    normalized = normalize_summary_label(label)
    return "adls storage" in normalized or normalized == "s3 storage"


def resolve_cluster_tab(
    workbook: Workbook,
    product_label: str,
    tab_hint: str | None,
) -> str | None:
    sheet_names = set(workbook.sheetnames)

    def valid_cluster_tab(name: str) -> bool:
        return name in sheet_names and is_cluster_worksheet(workbook[name])

    prefix_candidates: list[str] = []
    if product_label in sheet_names:
        prefix_candidates.append(product_label)
    for name in workbook.sheetnames:
        if product_label.startswith(f"{name} - "):
            prefix_candidates.append(name)
    if prefix_candidates:
        match = max(prefix_candidates, key=len)
        if valid_cluster_tab(match):
            return match

    parts = [part.strip() for part in product_label.split(" - ") if part.strip()]
    for end in range(len(parts), 0, -1):
        candidate = " - ".join(parts[:end])
        if valid_cluster_tab(candidate):
            return candidate

    if tab_hint and valid_cluster_tab(tab_hint):
        return tab_hint

    embedded: list[str] = []
    for name in workbook.sheetnames:
        if name in product_label and valid_cluster_tab(name):
            embedded.append(name)
    if embedded:
        return max(embedded, key=len)
    return None


def resolve_service_tab(workbook: Workbook, product_label: str) -> str | None:
    normalized = normalize_summary_label(product_label)
    sheet_by_lower = {name.lower(): name for name in workbook.sheetnames}
    for tab_name, summary_name in SERVICE_TAB_MAP.items():
        if normalize_summary_label(summary_name) == normalized:
            actual = sheet_by_lower.get(tab_name.lower())
            if actual:
                return actual
    for tab_name in workbook.sheetnames:
        if normalize_summary_label(tab_name) == normalized:
            return tab_name
        if normalized.startswith(normalize_summary_label(tab_name)):
            return tab_name
    return None


def parse_service_tab(
    workbook: Workbook,
    tab_name: str,
    group_name: str,
    aliases: dict[str, str],
) -> EstimateGroup | None:
    if tab_name not in workbook.sheetnames:
        return None
    ws = workbook[tab_name]
    header = find_header_row(ws)
    if not header:
        return None
    header_row, columns = header
    rows = parse_resource_table(ws)
    if not rows:
        return None
    services = rows_to_services(rows, aliases)
    if not services:
        return None
    return EstimateGroup(
        name=group_name,
        source_tab=tab_name,
        services=services,
        sheet_azure_total=find_total_azure(ws, header_row, columns) or sum_service_costs(services),
    )


def discover_service_groups_from_summary(
    workbook: Workbook,
    aliases: dict[str, str],
    existing_groups: list[EstimateGroup],
) -> list[EstimateGroup]:
    handled_tabs = {g.source_tab for g in existing_groups}
    handled_labels = {normalize_summary_label(g.name) for g in existing_groups}
    groups: list[EstimateGroup] = []

    for billing_row in parse_summary_billing_rows(workbook):
        if is_datalake_summary_label(billing_row.product_label):
            continue
        if is_storage_summary_label(billing_row.product_label):
            continue

        tab_name = resolve_service_tab(workbook, billing_row.product_label)
        if not tab_name or tab_name in handled_tabs:
            continue
        if normalize_summary_label(billing_row.product_label) in handled_labels:
            continue

        group = parse_service_tab(
            workbook,
            tab_name,
            billing_row.product_label,
            aliases,
        )
        if not group or not group.services:
            continue
        group.sheet_azure_total = billing_row.azure_total
        groups.append(group)
        handled_tabs.add(tab_name)
        handled_labels.add(normalize_summary_label(group.name))

    return groups


def parse_summary_cluster_groups(
    workbook: Workbook,
    aliases: dict[str, str],
    existing_groups: list[EstimateGroup],
) -> list[EstimateGroup]:
    handled_tabs = {group.source_tab for group in existing_groups}
    handled_labels = {normalize_summary_label(group.name) for group in existing_groups}
    groups: list[EstimateGroup] = []

    for billing_row in parse_summary_billing_rows(workbook):
        if is_datalake_summary_label(billing_row.product_label):
            continue
        if is_storage_summary_label(billing_row.product_label):
            continue
        if resolve_service_tab(workbook, billing_row.product_label):
            continue

        tab_name = resolve_cluster_tab(
            workbook,
            billing_row.product_label,
            billing_row.tab_hint,
        )
        if not tab_name or tab_name in handled_tabs:
            continue

        label_key = normalize_summary_label(billing_row.product_label)
        if label_key in handled_labels:
            continue

        group = parse_datahub_tab(
            workbook,
            tab_name,
            aliases,
            group_name=billing_row.product_label,
        )
        if not group or not group.services:
            continue

        group.sheet_azure_total = billing_row.azure_total
        groups.append(group)
        handled_tabs.add(tab_name)
        handled_labels.add(label_key)

    return groups


def parse_summary_misc_groups(
    workbook: Workbook,
    existing_groups: list[EstimateGroup],
) -> list[EstimateGroup]:
    handled_labels = {normalize_summary_label(group.name) for group in existing_groups}
    groups: list[EstimateGroup] = []

    for billing_row in parse_summary_billing_rows(workbook):
        if is_datalake_summary_label(billing_row.product_label):
            continue
        if is_storage_summary_label(billing_row.product_label):
            continue
        if resolve_service_tab(workbook, billing_row.product_label):
            continue
        if resolve_cluster_tab(workbook, billing_row.product_label, billing_row.tab_hint):
            continue

        label_key = normalize_summary_label(billing_row.product_label)
        if label_key in handled_labels:
            continue

        groups.append(
            EstimateGroup(
                name=billing_row.product_label,
                source_tab="Summary",
                services=[],
                sheet_azure_total=billing_row.azure_total,
            )
        )
        handled_labels.add(label_key)

    return groups


def parse_storage_group(workbook: Workbook) -> EstimateGroup | None:
    if "Summary" not in workbook.sheetnames:
        return None
    ws = workbook["Summary"]
    tb = to_float(ws["K1"].value)
    if tb <= 0:
        return None

    azure_total = find_summary_azure_for_label(ws, "adls storage")
    if azure_total is None:
        azure_total = find_summary_azure_for_label(ws, "s3 storage")

    return EstimateGroup(
        name="ADLS Storage",
        source_tab="Summary",
        services=[
            AdlsStorageService(
                description="ADLS Storage",
                storage_tb=tb,
                sheet_azure_cost=azure_total,
            )
        ],
        sheet_azure_total=azure_total,
    )


def find_summary_azure_for_label(ws, label_match: str) -> float | None:
    target = normalize_summary_label(label_match)
    for row_idx in range(1, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        if not label:
            continue
        if target not in normalize_summary_label(str(label)):
            continue
        azure_value = ws.cell(row_idx, 5).value
        if isinstance(azure_value, (int, float)):
            return float(azure_value)
    return None


def apply_summary_sheet_totals(workbook: Workbook, groups: list[EstimateGroup]) -> None:
    if "Summary" not in workbook.sheetnames:
        return
    ws = workbook["Summary"]
    summary_rows: list[tuple[str, float]] = []
    for row_idx in range(9, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        azure_value = ws.cell(row_idx, 5).value
        if not label or not isinstance(azure_value, (int, float)) or azure_value <= 0:
            continue
        summary_rows.append((normalize_summary_label(str(label)), float(azure_value)))

    for group in groups:
        group_key = normalize_summary_label(group.name)
        if group.name in {"ADLS Storage", "Storage"}:
            azure_total = find_summary_azure_for_label(ws, "adls storage")
            if azure_total is not None:
                group.sheet_azure_total = azure_total
            continue

        if group_key.startswith("datalake"):
            for label, azure_total in summary_rows:
                if label == group_key:
                    group.sheet_azure_total = azure_total
                    break
            continue

        best_match: float | None = None
        best_len = -1
        for label, azure_total in summary_rows:
            if group_key in label or label in group_key:
                if len(label) > best_len:
                    best_match = azure_total
                    best_len = len(label)
        if best_match is not None:
            group.sheet_azure_total = best_match


def parse_summary_grand_total(workbook: Workbook) -> float | None:
    if "Summary" not in workbook.sheetnames:
        return None
    ws = workbook["Summary"]
    for row_idx in range(1, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        if str(label or "").strip().lower() != "total":
            continue
        azure_value = ws.cell(row_idx, 5).value
        if isinstance(azure_value, (int, float)) and azure_value > 0:
            return float(azure_value)
    return None


def parse_summary_region(workbook: Workbook) -> str:
    ws = workbook["Summary"]
    for key in ("E4", "E5"):
        value = ws[key].value
        if value and re.match(r"^[a-z0-9]+$", str(value).replace("-", "")):
            return str(value)
    for row_idx in range(1, 15):
        for col_idx in range(1, 10):
            value = ws.cell(row_idx, col_idx).value
            if isinstance(value, str) and re.match(r"^[a-z]+(us|europe|asia|central|north|south|west|east)\d*$", value):
                return value
    return "eastus"
