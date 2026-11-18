from __future__ import annotations

from openpyxl.workbook.workbook import Workbook

from cdp_azure_estimator.models import EstimateGroup
from cdp_azure_estimator.parser.resource_table import (
    find_header_row,
    find_total_azure,
    hours_column,
    parse_resource_table,
)
from cdp_azure_estimator.transform.blocks import rows_to_services, sum_service_costs

DATALAKE_SECTIONS = {
    "Light Duty": "DataLake - Light Duty",
    "Enterprise Duty": "DataLake - Enterprise Duty",
    "Medium Duty": "DataLake - Medium Duty",
}


def find_azure_datalake_section(
    ws,
    section_label: str,
) -> tuple[int, dict[str, int], int, int] | None:
    header_row: int | None = None
    columns: dict[str, int] | None = None
    start_row: int | None = None

    for row_idx in range(1, ws.max_row + 1):
        if ws.cell(row_idx, 2).value != section_label:
            continue
        if ws.cell(row_idx, 3).value != "Purpose":
            continue
        header = find_header_row(ws, max_scan=row_idx + 1)
        if not header or header[0] != row_idx:
            values = [
                str(ws.cell(row_idx, col).value).strip()
                if ws.cell(row_idx, col).value is not None
                else ""
                for col in range(1, min(20, ws.max_column + 1))
            ]
            from cdp_azure_estimator.parser.resource_table import KNOWN_HEADERS

            columns = {}
            for idx, value in enumerate(values):
                normalized = value.replace("\n", " ")
                if normalized in KNOWN_HEADERS and normalized not in columns:
                    columns[normalized] = idx + 1
                elif value in KNOWN_HEADERS and value not in columns:
                    columns[value] = idx + 1
            if "Purpose" not in columns:
                continue
        else:
            header_row, columns = header
        header_row = row_idx
        start_row = header_row + 1
        break

    if header_row is None or columns is None or start_row is None:
        return None

    purpose_col = columns["Purpose"]
    end_row = ws.max_row
    for row_idx in range(start_row, ws.max_row + 1):
        section = ws.cell(row_idx, 2).value
        if section and section != section_label:
            break
        purpose = ws.cell(row_idx, purpose_col).value
        hours_col = hours_column(columns)
        hours_value = ws.cell(row_idx, hours_col).value if hours_col else None
        if (purpose and "Total" in str(purpose)) or hours_value == "Total":
            end_row = row_idx
            break

    return header_row, columns, start_row, end_row


def parse_datalake_groups(workbook: Workbook, aliases: dict[str, str]) -> list[EstimateGroup]:
    if "Datalake" not in workbook.sheetnames:
        return []

    ws = workbook["Datalake"]
    groups: list[EstimateGroup] = []

    for section_label, group_name in DATALAKE_SECTIONS.items():
        section = find_azure_datalake_section(ws, section_label)
        if not section:
            continue
        header_row, columns, start_row, end_row = section
        rows = parse_resource_table(
            ws,
            start_row=start_row,
            end_row=end_row,
            section_column=2,
            section_label=section_label,
        )
        if not rows:
            continue
        sheet_total = find_total_azure(ws, header_row, columns, end_row=end_row)
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
                sheet_azure_total=sheet_total or sum_service_costs(services),
            )
        )
    return groups
