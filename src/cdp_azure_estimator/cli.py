from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cdp_azure_estimator.calculator.builder import create_calculator_estimate
from cdp_azure_estimator.calculator.export_workbook import write_calculator_import_workbook
from cdp_azure_estimator.parser.summary import parse_summary_grand_total
from cdp_azure_estimator.parser.workbook import build_manifest, load_workbook
from cdp_azure_estimator.validate.diff import render_diff_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Cloudera CDP on Azure pricing spreadsheet into a grouped "
            "manifest and Azure Pricing Calculator import workbook."
        ),
        epilog=(
            "Use --create-link with --headed to sign in to Microsoft and publish a shareable "
            "Azure Pricing Calculator URL (same workflow as calculator.aws, via browser automation)."
        ),
    )
    parser.add_argument(
        "workbook",
        type=Path,
        help="Path to the Cloudera CDP on Azure pricing calculator .xlsx file",
    )
    parser.add_argument(
        "--customer",
        required=True,
        help='Customer name used for estimate title, e.g. "Example Corp"',
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
        "--import-out",
        type=Path,
        help="Write Excel helper for manual Azure Pricing Calculator entry",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print manifest JSON to stdout",
    )
    parser.add_argument(
        "--create-link",
        action="store_true",
        help="Publish a shareable Azure Pricing Calculator estimate (requires Microsoft sign-in)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window (required on first --create-link to sign in)",
    )
    parser.add_argument(
        "--auth-state",
        type=Path,
        help="Playwright storage state JSON for saved Microsoft login (default: .azure-calculator-auth.json)",
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

    if args.import_out:
        write_calculator_import_workbook(manifest, args.import_out)
        print(f"Azure calculator import helper: {args.import_out}")

    print(report)
    print()

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2))
        print()

    if args.create_link:
        try:
            url = create_calculator_estimate(
                manifest,
                headed=args.headed,
                auth_state=args.auth_state,
            )
        except Exception as error:  # noqa: BLE001
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(f"Shareable estimate: {url}")
    elif not args.import_out:
        print(
            "Tip: add --create-link --headed to publish a shareable Azure calculator URL "
            "(sign in to Microsoft on first run)."
        )

    if summary_total is not None and abs(summary_total - manifest.sheet_azure_total) > 1:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
