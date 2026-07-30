from __future__ import annotations

import pytest

from cdp_aws_estimator.parser.workbook import build_manifest
from cdp_aws_estimator.transform.aliases import alias_purpose, is_ec2_instance_type, parse_rds_type


WORKBOOK = "/Users/njlamsal/Downloads/AUTOMATION-  CDP on AWS Pricing Calculator -v7.xlsx"
V5_WORKBOOK = "/Users/njlamsal/Downloads/AUTOMATION of WORKING COPY of Solutions CDP on AWS Pricing Calculator - v5 (1).xlsx"


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


def test_data_mart_service_count(v5_manifest):
    data_mart = next(
        g for g in v5_manifest.groups if g.name == "Data Hub - Data Mart"
    )
    assert len(data_mart.services) == 3
    descriptions = {s.description for s in data_mart.services if hasattr(s, "description")}
    assert descriptions == {"Master Node", "Executor Node", "Coordinator Node"}
    assert abs((data_mart.sheet_aws_total or 0) - 2935.8) < 1
