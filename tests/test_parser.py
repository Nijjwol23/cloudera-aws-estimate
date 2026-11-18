from __future__ import annotations

import pytest

from cdp_aws_estimator.parser.workbook import build_manifest
from cdp_aws_estimator.transform.aliases import alias_purpose, is_datahub_tab, is_ec2_instance_type, parse_rds_type


WORKBOOK = "/Users/njlamsal/Downloads/AUTOMATION-  CDP on AWS Pricing Calculator -v7.xlsx"
V5_WORKBOOK = "/Users/njlamsal/Downloads/AUTOMATION of WORKING COPY of Solutions CDP on AWS Pricing Calculator - v5 (1).xlsx"
THREESUN_WORKBOOK = "/Users/njlamsal/Downloads/Copy of 3Sun - AWS Calculator.xlsx"
CENCOSUD_WORKBOOK = "/Users/njlamsal/Downloads/Cencosud-CDP-on-AWS.xlsx"


@pytest.fixture(scope="module")
def manifest():
    return build_manifest(WORKBOOK, "Test Customer")


@pytest.fixture(scope="module")
def v5_manifest():
    if not __import__("pathlib").Path(V5_WORKBOOK).exists():
        pytest.skip(f"v5 workbook not found: {V5_WORKBOOK}")
    return build_manifest(V5_WORKBOOK, "Example customer")


def test_manifest_region(manifest):
    assert manifest.region == "us-east-1"
    assert manifest.name == "Test Customer Pricing"


def test_core_groups_present(manifest):
    names = {group.name for group in manifest.groups}
    assert "Data Lake Core" in names
    assert "Cloudera Data Engineering" in names
    assert "Cloudera Data Warehouse" in names
    assert "Storage" in names


def test_datahub_group(manifest):
    datahub_groups = [g for g in manifest.groups if g.name.startswith("Data Hub -")]
    assert len(datahub_groups) == 1
    assert "Streams Messaging Heavy Duty" in datahub_groups[0].name


def test_datalake_service_count(manifest):
    datalake = next(g for g in manifest.groups if g.name == "Data Lake Core")
    assert len(datalake.services) >= 6


def test_alias_dictionary():
    assert alias_purpose("DataLake Master Node (CDP cluster)") == "DL Master"
    assert alias_purpose("Master Node*") == "Master Node"


def test_rds_parser():
    parsed = parse_rds_type("db.m5.large-PostgreSQL-Single-AZ")
    assert parsed == ("db.m5.large", "PostgreSQL", False)


def test_ec2_instance_types():
    assert is_ec2_instance_type("m5a.large")
    assert is_ec2_instance_type("r6id.8xlarge")
    assert is_ec2_instance_type("p4d.24xlarge")
    assert not is_ec2_instance_type("gp2")


def test_datahub_tab_detection():
    assert is_datahub_tab("Datahub 1")
    assert is_datahub_tab("Datahub DF")
    assert is_datahub_tab("Flow Management DH")
    assert is_datahub_tab("Streams Messaging DH")
    assert not is_datahub_tab("CLDR Pricing - DH")
    assert not is_datahub_tab("CDE")


@pytest.fixture(scope="module")
def threesun_manifest():
    if not __import__("pathlib").Path(THREESUN_WORKBOOK).exists():
        pytest.skip(f"3Sun workbook not found: {THREESUN_WORKBOOK}")
    return build_manifest(THREESUN_WORKBOOK, "3sun")


def test_threesun_datahub_groups(threesun_manifest):
    datahub_groups = [g for g in threesun_manifest.groups if g.name.startswith("Data Hub -")]
    names = {g.name for g in datahub_groups}
    assert len(datahub_groups) == 2
    assert "Data Hub - Flow Management - Nifi 2 Heavy Duty" in names
    assert "Data Hub - Streams Messaging Heavy Duty" in names
    totals = {g.name: g.sheet_aws_total for g in datahub_groups}
    assert abs((totals["Data Hub - Flow Management - Nifi 2 Heavy Duty"] or 0) - 3741.3) < 1
    assert abs((totals["Data Hub - Streams Messaging Heavy Duty"] or 0) - 3953.24) < 1


def test_data_mart_service_count(v5_manifest):
    data_mart = next(
        g for g in v5_manifest.groups if g.name == "Data Hub - Data Mart"
    )
    assert len(data_mart.services) == 3
    descriptions = {s.description for s in data_mart.services if hasattr(s, "description")}
    assert descriptions == {"Master Node", "Executor Node", "Coordinator Node"}
    assert abs((data_mart.sheet_aws_total or 0) - 2935.8) < 1


@pytest.fixture(scope="module")
def cencosud_manifest():
    if not __import__("pathlib").Path(CENCOSUD_WORKBOOK).exists():
        pytest.skip(f"Cencosud workbook not found: {CENCOSUD_WORKBOOK}")
    return build_manifest(CENCOSUD_WORKBOOK, "Cencosud")


def test_cencosud_flow_management_groups(cencosud_manifest):
    flow_groups = [
        g for g in cencosud_manifest.groups if g.name.startswith("Flow Management -")
    ]
    assert len(flow_groups) == 6
    regions = {g.name.split(" - ")[1] for g in flow_groups}
    assert regions == {"Chile", "Colombia", "Peru Prod", "Peru Dev", "Arg Prod", "Arg Test"}


def test_cencosud_summary_total(cencosud_manifest):
    from cdp_aws_estimator.parser.summary import parse_summary_grand_total
    from cdp_aws_estimator.parser.workbook import load_workbook

    summary_total = parse_summary_grand_total(load_workbook(CENCOSUD_WORKBOOK))
    assert abs(cencosud_manifest.sheet_aws_total - summary_total) < 1
    assert len(cencosud_manifest.groups) == 9


def test_resolve_cluster_tab_uses_product_label_prefix():
    from pathlib import Path

    if not Path(CENCOSUD_WORKBOOK).exists():
        pytest.skip(f"Cencosud workbook not found: {CENCOSUD_WORKBOOK}")

    import openpyxl

    from cdp_aws_estimator.parser.summary import resolve_cluster_tab

    workbook = openpyxl.load_workbook(CENCOSUD_WORKBOOK, data_only=True)
    tab = resolve_cluster_tab(
        workbook,
        "Flow Management - Chile - Flow Management Heavy Duty",
        "Copy of Summary",
    )
    assert tab == "Flow Management - Chile"
    tab = resolve_cluster_tab(
        workbook,
        "Flow Management - Colombia - Flow Management Heavy Duty",
        "Flow Management - Chile",
    )
    assert tab == "Flow Management - Colombia"
