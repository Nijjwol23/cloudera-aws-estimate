from __future__ import annotations

import re
from dataclasses import dataclass

from openpyxl.workbook.workbook import Workbook

from cdp_aws_estimator.models import EstimateGroup, S3Service
from cdp_aws_estimator.parser.datahub import parse_datahub_tab
from cdp_aws_estimator.parser.resource_table import (
    KNOWN_HEADERS,
    find_header_row,
    find_total_aws,
    hours_column,
    is_cluster_worksheet,
    parse_resource_table,
)
from cdp_aws_estimator.transform.aliases import to_float
from cdp_aws_estimator.transform.blocks import rows_to_services, sum_service_costs

DATALAKE_GROUPS = {
    "DataLake - Light Duty": ("Light Duty", "Data Lake Core"),
    "DataLake - Enterprise Duty": ("Enterprise Duty", "Data Lake Core"),
    "DataLake - Medium Duty": ("Medium Duty", "Data Lake Core"),
}

SUMMARY_BILLING_START_ROW = 9
SUMMARY_LABEL_COL = 4
SUMMARY_TAB_HINT_COL = 3
SUMMARY_AWS_COL = 5

_SKIP_SUMMARY_LABEL_PREFIXES = (
    "total",
    "discount",
    "total año",
    "total ano",
    "only ",
)


@dataclass(frozen=True)
class SummaryBillingRow:
    product_label: str
    aws_total: float
    tab_hint: str | None
    row: int


def parse_summary_billing_rows(workbook: Workbook) -> list[SummaryBillingRow]:
    if "Summary" not in workbook.sheetnames:
        return []
    ws = workbook["Summary"]
    rows: list[SummaryBillingRow] = []
    for row_idx in range(SUMMARY_BILLING_START_ROW, ws.max_row + 1):
        label = ws.cell(row_idx, SUMMARY_LABEL_COL).value
        aws_value = ws.cell(row_idx, SUMMARY_AWS_COL).value
        if not label or not isinstance(aws_value, (int, float)) or aws_value <= 0:
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
                aws_total=float(aws_value),
                tab_hint=hint,
                row=row_idx,
            )
        )
    return rows


def is_datalake_summary_label(label: str) -> bool:
    return normalize_summary_label(label).startswith("datalake")


def is_storage_summary_label(label: str) -> bool:
    return "s3 storage" in normalize_summary_label(label)


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

        group.sheet_aws_total = billing_row.aws_total
        groups.append(group)
        handled_tabs.add(tab_name)
        handled_labels.add(label_key)

    return groups


def parse_summary_misc_groups(
    workbook: Workbook,
    existing_groups: list[EstimateGroup],
) -> list[EstimateGroup]:
    """Summary line items with AWS cost but no cluster worksheet (e.g. Private Link)."""
    handled_labels = {normalize_summary_label(group.name) for group in existing_groups}
    groups: list[EstimateGroup] = []

    for billing_row in parse_summary_billing_rows(workbook):
        if is_datalake_summary_label(billing_row.product_label):
            continue
        if is_storage_summary_label(billing_row.product_label):
            continue

        label_key = normalize_summary_label(billing_row.product_label)
        if label_key in handled_labels:
            continue

        if resolve_cluster_tab(workbook, billing_row.product_label, billing_row.tab_hint):
            continue

        groups.append(
            EstimateGroup(
                name=billing_row.product_label,
                source_tab="Summary",
                services=[],
                sheet_aws_total=billing_row.aws_total,
            )
        )
        handled_labels.add(label_key)

    return groups


def parse_datalake_groups(workbook: Workbook, aliases: dict[str, str]) -> list[EstimateGroup]:
    if "Datalake" not in workbook.sheetnames:
        return []

    ws = workbook["Datalake"]
    groups: list[EstimateGroup] = []

    for product_name, (section_label, group_name) in DATALAKE_GROUPS.items():
        section = find_datalake_section(ws, section_label)
        if not section:
            continue
        header_row, columns, start_row, end_row = section
        rows = parse_resource_table(ws, start_row=start_row, end_row=end_row)
        if not rows:
            continue
        sheet_total = find_total_aws(ws, header_row, columns, end_row=end_row)
        if not sheet_total or sheet_total <= 0:
            continue
        services = rows_to_services(rows, aliases)
        if not services:
            continue
        groups.append(
            EstimateGroup(
                name=group_name,
                source_tab=f"Datalake ({section_label})",
                services=services,
                sheet_aws_total=sheet_total or sum_service_costs(services),
            )
        )
    return groups


def find_datalake_section(
    ws,
    section_label: str,
) -> tuple[int, dict[str, int], int, int] | None:
    header_row: int | None = None
    columns: dict[str, int] | None = None
    start_row: int | None = None

    for row_idx in range(1, ws.max_row + 1):
        label = ws.cell(row_idx, 2).value
        if label != section_label:
            continue
        purpose = ws.cell(row_idx, 3).value
        if purpose == "Purpose":
            values = [
                str(ws.cell(row_idx, col).value).strip()
                if ws.cell(row_idx, col).value is not None
                else ""
                for col in range(1, min(20, ws.max_column + 1))
            ]
            columns = {}
            for idx, value in enumerate(values):
                if value in KNOWN_HEADERS and value not in columns:
                    columns[value] = idx + 1
            if "Purpose" not in columns or "Resource Type" not in columns:
                continue
            header_row = row_idx
            start_row = header_row + 1
            break

    if header_row is None or columns is None or start_row is None:
        return None

    end_row = ws.max_row
    purpose_col = columns["Purpose"]
    for row_idx in range(start_row, ws.max_row + 1):
        label = ws.cell(row_idx, 2).value
        if label and label != section_label:
            break
        purpose = ws.cell(row_idx, purpose_col).value
        hours_col = hours_column(columns)
        hours_value = ws.cell(row_idx, hours_col).value if hours_col else None
        if (purpose and "Total" in str(purpose)) or hours_value == "Total":
            end_row = row_idx
            break

    return header_row, columns, start_row, end_row


def parse_storage_group(workbook: Workbook) -> EstimateGroup | None:
    if "Summary" not in workbook.sheetnames:
        return None
    ws = workbook["Summary"]
    tb = to_float(ws["K1"].value)
    if tb <= 0:
        return None

    aws_total = find_summary_aws_for_label(ws, "s3 storage")
    if aws_total is None:
        aws_value = ws["E11"].value if ws["E11"].value is not None else ws.cell(11, 5).value
        if isinstance(aws_value, (int, float)):
            aws_total = float(aws_value)

    return EstimateGroup(
        name="Storage",
        source_tab="Summary",
        services=[
            S3Service(
                description="S3 Storage",
                standard_storage_tb=tb,
                sheet_aws_cost=aws_total,
            )
        ],
        sheet_aws_total=aws_total,
    )


def normalize_summary_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label).strip().lower().replace("*", ""))


def find_summary_aws_for_label(ws, label_match: str) -> float | None:
    target = normalize_summary_label(label_match)
    for row_idx in range(1, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        if not label:
            continue
        if target not in normalize_summary_label(str(label)):
            continue
        aws_value = ws.cell(row_idx, 5).value
        if isinstance(aws_value, (int, float)):
            return float(aws_value)
    return None


def apply_summary_sheet_totals(workbook: Workbook, groups: list[EstimateGroup]) -> None:
    if "Summary" not in workbook.sheetnames:
        return
    ws = workbook["Summary"]
    summary_rows: list[tuple[str, float]] = []
    for row_idx in range(9, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        aws_value = ws.cell(row_idx, 5).value
        if not label or not isinstance(aws_value, (int, float)) or aws_value <= 0:
            continue
        summary_rows.append((normalize_summary_label(str(label)), float(aws_value)))

    for group in groups:
        group_key = normalize_summary_label(group.name)
        if group.name == "Storage":
            aws_total = find_summary_aws_for_label(ws, "s3 storage")
            if aws_total is not None:
                group.sheet_aws_total = aws_total
            continue

        if group.name == "Data Lake Core":
            section_label: str | None = None
            if group.source_tab.startswith("Datalake (") and group.source_tab.endswith(")"):
                section_label = group.source_tab[len("Datalake (") : -1]
            for product_name, (datalake_section, _) in DATALAKE_GROUPS.items():
                if section_label and datalake_section != section_label:
                    continue
                aws_total = find_summary_aws_for_label(ws, product_name)
                if aws_total is None:
                    continue
                group.sheet_aws_total = aws_total
                break
            continue

        best_match: float | None = None
        best_len = -1
        for label, aws_total in summary_rows:
            if group_key in label or label in group_key:
                if len(label) > best_len:
                    best_match = aws_total
                    best_len = len(label)
        if best_match is not None:
            group.sheet_aws_total = best_match


def parse_summary_grand_total(workbook: Workbook) -> float | None:
    if "Summary" not in workbook.sheetnames:
        return None
    ws = workbook["Summary"]
    for row_idx in range(1, ws.max_row + 1):
        label = ws.cell(row_idx, 4).value
        if str(label or "").strip().lower() != "total":
            continue
        aws_value = ws.cell(row_idx, 5).value
        if isinstance(aws_value, (int, float)) and aws_value > 0:
            return float(aws_value)
    return None


def parse_summary_region(workbook: Workbook) -> str:
    ws = workbook["Summary"]
    for key in ("E4", "E5"):
        value = ws[key].value
        if value and re.match(r"^[a-z]{2}-[a-z]+-\d+$", str(value)):
            return str(value)
    for row_idx in range(1, 10):
        for col_idx in range(1, 10):
            value = ws.cell(row_idx, col_idx).value
            if isinstance(value, str) and re.match(r"^[a-z]{2}-[a-z]+-\d+$", value):
                return value
    return "us-east-1"


SERVICE_TAB_MAP = {
    "CDE": "Cloudera Data Engineering",
    "CDW": "Cloudera Data Warehouse",
    "CDF": "Cloudera Data Flow",
    "COD": "Cloudera Operational Database",
    "CAI - Workbench": "Cloudera AI - Workbench",
    "CAI - Inference Service": "Cloudera AI - Inference Service",
    "CML - Small": "Cloudera AI - Data Services - Small",
    "CML - Med": "Cloudera AI - Data Services - Medium",
    "CML - Large": "Cloudera AI - Data Services - Large",
    "CML - AI Inference - Med": "Cloudera AI - Inference Service - Medium",
    "CML - AI Inference - Large": "Cloudera AI - Inference Service - Large",
}


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
        sheet_aws_total=find_total_aws(ws, header_row, columns) or sum_service_costs(services),
    )


def discover_service_tabs(workbook: Workbook) -> list[tuple[str, str]]:
    sheet_names = {name.lower(): name for name in workbook.sheetnames}
    discovered: list[tuple[str, str]] = []
    for tab_name, group_name in SERVICE_TAB_MAP.items():
        actual_name = sheet_names.get(tab_name.lower())
        if actual_name:
            discovered.append((actual_name, group_name))
    return discovered
