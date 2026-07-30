from __future__ import annotations

from cdp_aws_estimator.models import EstimateManifest
from cdp_aws_estimator.parser.summary import parse_summary_grand_total


def render_diff_report(manifest: EstimateManifest, *, summary_grand_total: float | None = None) -> str:
    lines = [
        "Validation report (sheet AWS totals vs parsed groups)",
        "=" * 72,
        f"Customer: {manifest.customer}",
        f"Region:   {manifest.region}",
        "",
        f"{'Group':<45} {'Sheet AWS':>12}",
        "-" * 72,
    ]
    for group in manifest.groups:
        total = group.sheet_aws_total or 0.0
        lines.append(f"{group.name:<45} ${total:>11,.2f}")
    lines.extend(
        [
            "-" * 72,
            f"{'TOTAL (parsed groups)':<45} ${manifest.sheet_aws_total:>11,.2f}",
        ]
    )
    if summary_grand_total is not None:
        lines.append(f"{'Summary sheet total (AWS)':<45} ${summary_grand_total:>11,.2f}")
    lines.extend(
        [
            "",
            f"Services parsed: {sum(len(g.services) for g in manifest.groups)}",
            f"Groups:          {len(manifest.groups)}",
        ]
    )
    if summary_grand_total is not None and abs(summary_grand_total - manifest.sheet_aws_total) > 1:
        lines.extend(
            [
                "",
                "Note: Parsed groups total may differ from the Summary sheet total when",
                "Datahub tabs share one workbook section or Summary rolls up differently.",
            ]
        )
    return "\n".join(lines)
