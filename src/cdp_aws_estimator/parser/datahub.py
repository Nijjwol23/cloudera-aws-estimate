from __future__ import annotations

from openpyxl.workbook.workbook import Workbook

from cdp_aws_estimator.models import EstimateGroup
from cdp_aws_estimator.parser.resource_table import find_header_row, find_total_aws, parse_resource_table
from cdp_aws_estimator.transform.aliases import (
    datahub_group_name,
    datahub_template_from_tab,
    is_datahub_tab,
    to_float,
)
from cdp_aws_estimator.transform.blocks import rows_to_services, sum_service_costs


def discover_datahub_tabs(workbook: Workbook) -> list[str]:
    tabs: list[str] = []
    for name in workbook.sheetnames:
        if is_datahub_tab(name):
            tabs.append(name)

    summary_tabs = discover_summary_datahub_tabs(workbook)
    ordered: list[str] = []
    seen: set[str] = set()
    for tab in summary_tabs + tabs:
        if tab and tab in workbook.sheetnames and tab not in seen:
            ordered.append(tab)
            seen.add(tab)
    return ordered


def discover_summary_datahub_tabs(workbook: Workbook) -> list[str]:
    if "Summary" not in workbook.sheetnames:
        return []
    ws = workbook["Summary"]
    sheet_names = set(workbook.sheetnames)
    tabs: list[str] = []
    seen: set[str] = set()
    for row_idx in range(20, 40):
        # Column C often holds tab refs; some workbooks put the tab name in column D
        # (Product Name) with column C pointing at another sheet or copy label.
        for col_idx in (3, 4):
            tab_name = ws.cell(row_idx, col_idx).value
            if not tab_name or not isinstance(tab_name, str):
                continue
            if tab_name.startswith("="):
                continue
            tab_name = tab_name.strip()
            if tab_name not in sheet_names or not is_datahub_tab(tab_name):
                continue
            if tab_name not in seen:
                tabs.append(tab_name)
                seen.add(tab_name)
    return tabs


def selected_template_name(ws) -> str:
    value = ws["A1"].value
    if value and str(value).strip() and str(value).strip() != "Datahub Type":
        return str(value).strip()
    return datahub_template_from_tab(ws.title, None)


def template_has_active_rows(ws, template_name: str) -> bool:
    rows = parse_resource_table(ws, cluster_filter=template_name)
    return len(rows) > 0


def find_datahub_section(ws, template_name: str) -> tuple[int, int] | None:
    """Return (start_row, end_row) for one cluster block on a multi-template Datahub tab."""
    template = str(template_name).strip()
    if not template:
        return None

    for row_idx in range(1, ws.max_row + 1):
        cluster = ws.cell(row_idx, 4).value
        if str(cluster or "").strip() != template:
            continue
        if ws.cell(row_idx, 6).value != "Purpose":
            continue

        start_row = row_idx + 1
        end_row = ws.max_row
        for scan_row in range(start_row, ws.max_row + 1):
            cluster = ws.cell(scan_row, 4).value
            if str(cluster or "").strip() != template:
                end_row = scan_row - 1
                break
            purpose = ws.cell(scan_row, 6).value
            hours = ws.cell(scan_row, 9).value
            if (purpose and "Total" in str(purpose)) or hours == "Total":
                end_row = scan_row
                break
        if start_row <= end_row:
            return start_row, end_row
    return None


def parse_datahub_tab(
    workbook: Workbook,
    tab_name: str,
    aliases: dict[str, str],
    *,
    group_name: str | None = None,
) -> EstimateGroup | None:
    ws = workbook[tab_name]
    template_name = selected_template_name(ws)
    section = find_datahub_section(ws, template_name)
    if section:
        start_row, end_row = section
        rows = parse_resource_table(ws, start_row=start_row, end_row=end_row)
    elif template_has_active_rows(ws, template_name):
        rows = parse_resource_table(ws, cluster_filter=template_name)
    else:
        alt_template = datahub_template_from_tab(tab_name, ws["A1"].value)
        if alt_template != template_name:
            section = find_datahub_section(ws, alt_template)
            if section:
                template_name = alt_template
                start_row, end_row = section
                rows = parse_resource_table(ws, start_row=start_row, end_row=end_row)
            elif template_has_active_rows(ws, alt_template):
                template_name = alt_template
                rows = parse_resource_table(ws, cluster_filter=template_name)
            else:
                rows = parse_resource_table(ws)
        else:
            rows = parse_resource_table(ws)

    if not rows:
        return None

    services = rows_to_services(rows, aliases)
    if not services:
        return None

    header = find_header_row(ws)
    sheet_total = None
    try:
        o1_value = ws["O1"].value
    except KeyError:
        o1_value = None
    if isinstance(o1_value, (int, float)) and o1_value > 0:
        sheet_total = float(o1_value)
    if sheet_total is None and header:
        header_row, columns = header
        sheet_total = find_total_aws(ws, header_row, columns)

    return EstimateGroup(
        name=group_name or datahub_group_name(tab_name, template_name),
        source_tab=tab_name,
        services=services,
        sheet_aws_total=sheet_total or sum_service_costs(services),
    )


def parse_all_datahub_groups(workbook: Workbook, aliases: dict[str, str]) -> list[EstimateGroup]:
    groups: list[EstimateGroup] = []
    for tab_name in discover_datahub_tabs(workbook):
        group = parse_datahub_tab(workbook, tab_name, aliases)
        if group and group.services:
            groups.append(group)
    return groups


def summary_datahub_is_active(workbook: Workbook, tab_name: str) -> bool:
    if "Summary" not in workbook.sheetnames:
        return True
    ws = workbook["Summary"]
    for row_idx in range(20, 40):
        ref_tab = ws.cell(row_idx, 3).value
        if ref_tab != tab_name:
            continue
        aws_formula = ws.cell(row_idx, 5).value
        if isinstance(aws_formula, (int, float)):
            return float(aws_formula) > 0
    return True
