from __future__ import annotations

import pytest

from cdp_azure_estimator.parser.summary import parse_summary_grand_total, resolve_cluster_tab
from cdp_azure_estimator.parser.workbook import build_manifest, load_workbook

AZURE_V7 = "/Users/njlamsal/Downloads/CDP on Azure Pricing Calculator -v7.xlsx"


@pytest.fixture(scope="module")
def azure_manifest():
    if not __import__("pathlib").Path(AZURE_V7).exists():
        pytest.skip(f"Azure v7 workbook not found: {AZURE_V7}")
    return build_manifest(AZURE_V7, "Azure Baseline")


def test_azure_region(azure_manifest):
    assert azure_manifest.region == "eastus"


def test_azure_core_groups(azure_manifest):
    names = {g.name for g in azure_manifest.groups}
    assert "DataLake - Enterprise Duty" in names
    assert "ADLS Storage" in names
    assert "CDE - Data Engineering Data Service" in names
    assert "Data Hub - Flow Management Heavy Duty" in names


def test_azure_summary_total(azure_manifest):
    summary_total = parse_summary_grand_total(load_workbook(AZURE_V7))
    assert summary_total is not None
    assert abs(azure_manifest.sheet_azure_total - summary_total) < 2


def test_resolve_datahub_tab_from_summary_label():
    if not __import__("pathlib").Path(AZURE_V7).exists():
        pytest.skip(f"Azure v7 workbook not found: {AZURE_V7}")
    import openpyxl

    workbook = openpyxl.load_workbook(AZURE_V7, data_only=True)
    tab = resolve_cluster_tab(
        workbook,
        "Datahub 1 - Flow Management Heavy Duty",
        "Datahub 1",
    )
    assert tab == "Datahub 1"
