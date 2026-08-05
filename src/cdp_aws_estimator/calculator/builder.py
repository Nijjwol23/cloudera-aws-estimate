from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cdp_aws_estimator.models import EstimateManifest

_NODE_DEPS = (
    "node_modules/@modelcontextprotocol/sdk",
    "node_modules/sample-aws-pricing-calculator-mcp",
)


def _ensure_node_bridge(root: Path) -> None:
    if not shutil.which("node"):
        raise RuntimeError(
            "Node.js is required for --create-link. Install Node 18+ then run:\n"
            f"  cd {root}\n"
            "  npm install"
        )
    missing = [dep for dep in _NODE_DEPS if not (root / dep).exists()]
    if missing:
        raise RuntimeError(
            "Node dependencies are missing (npm install was not run). From the repo root:\n"
            f"  cd {root}\n"
            "  npm install\n"
            "Then re-run with --create-link."
        )


def create_calculator_estimate(
    manifest: EstimateManifest,
    *,
    project_root: Path | None = None,
) -> str:
    root = project_root or Path(__file__).resolve().parents[3]
    script = root / "scripts" / "build_estimate.mjs"
    if not script.exists():
        raise FileNotFoundError(f"Estimate builder script not found: {script}")
    _ensure_node_bridge(root)

    manifest_path = root / ".tmp_manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    try:
        result = subprocess.run(
            ["node", str(script), str(manifest_path)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        manifest_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to create calculator.aws estimate:\n"
            f"{result.stderr or result.stdout}"
        )

    payload = json.loads(result.stdout)
    url = payload.get("url")
    if not url:
        raise RuntimeError(f"Estimate builder returned unexpected output: {result.stdout}")

    added = payload.get("services_added")
    expected = payload.get("services_expected")
    if isinstance(added, int) and isinstance(expected, int) and added != expected:
        raise RuntimeError(
            f"Estimate builder added {added}/{expected} services before export."
        )

    return url
