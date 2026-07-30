#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Setting up cdp-aws-estimator in $ROOT"

# Remove venv if it was moved from another directory (broken shebang paths).
rm -rf .venv
python3 -m venv .venv

# Use python -m pip so we never rely on stale pip shebangs.
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"

if command -v npm >/dev/null 2>&1; then
  npm install
else
  echo "Warning: npm not found. Install Node.js before using --create-link."
fi

echo
echo "Done. Activate and run:"
echo "  source .venv/bin/activate"
echo "  cdp-aws-estimate \"/path/to/workbook.xlsx\" --customer \"Acme Corp\" --create-link"
echo
echo "Or without activating:"
echo "  .venv/bin/cdp-aws-estimate \"/path/to/workbook.xlsx\" --customer \"Acme Corp\" --create-link"
