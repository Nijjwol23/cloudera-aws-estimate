from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cdp_aws_estimator.calculator.builder import create_calculator_estimate
from cdp_aws_estimator.parser.summary import parse_summary_grand_total
from cdp_aws_estimator.parser.workbook import build_manifest, load_workbook
from cdp_aws_estimator.validate.diff import render_diff_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Cloudera CDP pricing spreadsheet into a grouped "
            "calculator.aws estimate for funding applications."
        ),
        epilog=(
            "Funding submissions require a shareable AWS Pricing Calculator link; "
            "this replaces the manual step of re-entering workbook line items."
        ),
    )
    parser.add_argument(
        "workbook",
        type=Path,
        help="Path to the Cloudera CDP pricing calculator .xlsx file",
    )
    parser.add_argument(
        "--customer",
        required=True,
        help='Customer name used for estimate title, e.g. "Acme Corp"',
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        help="Optional path to write the normalized manifest JSON",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        help="Optional path to write the validation report",
    )
    parser.add_argument(
        "--create-link",
        action="store_true",
        help="Create a shareable calculator.aws estimate link",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print manifest JSON to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.workbook.exists():
        parser.error(f"Workbook not found: {args.workbook}")

    manifest = build_manifest(args.workbook, args.customer)
    summary_total = parse_summary_grand_total(load_workbook(args.workbook))
    report = render_diff_report(manifest, summary_grand_total=summary_total)

    if args.manifest_out:
        args.manifest_out.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )

    if args.report_out:
        args.report_out.write_text(report + "\n", encoding="utf-8")

    print(report)
    print()

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2))
        print()

    if args.create_link:
        try:
            url = create_calculator_estimate(manifest)
        except Exception as error:  # noqa: BLE001 - surface builder errors to CLI user
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(f"Shareable estimate: {url}")
    else:
        print("Tip: add --create-link to publish a calculator.aws estimate.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
