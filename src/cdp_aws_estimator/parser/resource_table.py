from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet

from cdp_aws_estimator.models import ResourceRow
from cdp_aws_estimator.transform.aliases import to_float


KNOWN_HEADERS = frozenset(
    {
        "Purpose",
        "Resource Type",
        "Resource Count",
        "# of Hours",
        "# of Hours ",
        "Number of Hours ",
        "AWS",
        "AWS Cost (USD)",
        "Cloudera",
        "Total",
        "Virtual Cluster Type",
    }
)


def is_cluster_worksheet(ws: Worksheet) -> bool:
    """True when a sheet has the Purpose / Resource Type cluster cost table."""
    header = find_header_row(ws, max_scan=250)
    if not header:
        return False
    header_row, columns = header
    purpose_col = columns.get("Purpose")
    type_col = columns.get("Resource Type")
    count_col = columns.get("Resource Count")
    hours_col = hours_column(columns)
    if not all((purpose_col, type_col, count_col, hours_col)):
        return False
    for row_idx in range(header_row + 1, min(ws.max_row, header_row + 250) + 1):
        resource_type = ws.cell(row_idx, type_col).value
        if resource_type is None or str(resource_type).strip() == "":
            continue
        count = to_float(ws.cell(row_idx, count_col).value)
        hours = to_float(ws.cell(row_idx, hours_col).value)
        if count > 0 and hours > 0:
            return True
    return False


def find_header_row(ws: Worksheet, max_scan: int = 40) -> tuple[int, dict[str, int]] | None:
    for row_idx in range(1, min(max_scan, ws.max_row + 1)):
        values = [
            str(ws.cell(row_idx, col).value).strip()
            if ws.cell(row_idx, col).value is not None
            else ""
            for col in range(1, min(20, ws.max_column + 1))
        ]
        if "Purpose" in values and "Resource Type" in values:
            columns: dict[str, int] = {}
            for idx, value in enumerate(values):
                if value in KNOWN_HEADERS and value not in columns:
                    columns[value] = idx + 1
            return row_idx, columns
    return None


def hours_column(columns: dict[str, int]) -> int | None:
    for key in ("# of Hours", "# of Hours ", "Number of Hours "):
        if key in columns:
            return columns[key]
    return None


def aws_column(columns: dict[str, int]) -> int | None:
    candidates = [columns[key] for key in ("AWS", "AWS Cost (USD)") if key in columns]
    return min(candidates) if candidates else None


def parse_resource_table(
    ws: Worksheet,
    *,
    start_row: int | None = None,
    end_row: int | None = None,
    cluster_filter: str | None = None,
    cluster_column: int = 4,
) -> list[ResourceRow]:
    header = find_header_row(ws)
    if not header:
        return []
    header_row, columns = header

    purpose_col = columns["Purpose"]
    type_col = columns["Resource Type"]
    count_col = columns["Resource Count"]
    hours_col = hours_column(columns)
    aws_col = aws_column(columns)
    if hours_col is None:
        return []

    first_row = start_row or header_row + 1
    last_row = end_row or ws.max_row
    rows: list[ResourceRow] = []
    current_purpose: str | None = None

    for row_idx in range(first_row, last_row + 1):
        purpose_value = ws.cell(row_idx, purpose_col).value
        resource_type = ws.cell(row_idx, type_col).value

        if purpose_value and "Total" in str(purpose_value):
            break

        if cluster_filter:
            cluster_value = ws.cell(row_idx, cluster_column).value
            if cluster_value is None or str(cluster_value).strip() == "":
                continue
            if str(cluster_value).strip() != str(cluster_filter).strip():
                continue

        if purpose_value:
            current_purpose = str(purpose_value).strip()

        if resource_type is None or str(resource_type).strip() == "":
            continue

        count = to_float(ws.cell(row_idx, count_col).value)
        hours = to_float(ws.cell(row_idx, hours_col).value)
        if count <= 0 or hours <= 0:
            continue

        aws_cost = None
        if aws_col:
            aws_value = ws.cell(row_idx, aws_col).value
            if isinstance(aws_value, (int, float)):
                aws_cost = float(aws_value)

        rows.append(
            ResourceRow(
                purpose=current_purpose,
                resource_type=str(resource_type).strip(),
                count=count,
                hours=hours,
                aws_cost=aws_cost,
                row=row_idx,
            )
        )
    return rows


def find_total_aws(
    ws: Worksheet,
    header_row: int,
    columns: dict[str, int],
    *,
    end_row: int | None = None,
) -> float | None:
    purpose_col = columns["Purpose"]
    hours_col = hours_column(columns)
    aws_col = aws_column(columns)
    if aws_col is None:
        return None
    last_row = end_row or ws.max_row
    for row_idx in range(header_row + 1, last_row + 1):
        row_values = [
            str(ws.cell(row_idx, col).value or "").strip()
            for col in range(purpose_col, purpose_col + 4)
        ]
        hours_value = ws.cell(row_idx, hours_col).value if hours_col else None
        purpose = ws.cell(row_idx, purpose_col).value
        if (
            (purpose and "Total" in str(purpose))
            or any("Total" in value for value in row_values)
            or hours_value == "Total"
        ):
            value = ws.cell(row_idx, aws_col).value
            if isinstance(value, (int, float)):
                return float(value)
            # Some exports leave totals as cached numbers in the Cloudera column block.
            for fallback_col in range(aws_col, aws_col + 3):
                fallback = ws.cell(row_idx, fallback_col).value
                if isinstance(fallback, (int, float)) and fallback > 0:
                    return float(fallback)
    return None
