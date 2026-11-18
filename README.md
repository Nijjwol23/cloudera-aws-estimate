# CDP → AWS / Azure Pricing Calculators

Convert Cloudera CDP pricing spreadsheets into grouped cloud calculator estimates:

- **AWS:** [AWS Pricing Calculator](https://calculator.aws/) with optional `--create-link`
- **Azure:** [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) via grouped import workbook (`--import-out`)

**Author:** [Nijjwol Lamsal](https://github.com/nijjwol23)

## Why this exists

Funding applications for CDP on AWS deployments require a shareable **AWS Pricing Calculator** estimate — the official AWS cost view reviewers expect alongside the Cloudera workbook.

Until now that estimate was built **by hand**: someone opened [calculator.aws](https://calculator.aws/), re-entered every EC2, EKS, EFS, RDS, and S3 line from the spreadsheet, grouped them to match the workbook, and saved a link. That work was slow, easy to get wrong (missing services, $0 pricing traps, wrong instance counts), and had to be repeated for every customer and sizing variant.

This tool automates that step. It reads the same Cloudera pricing calculator `.xlsx` the solutions team already maintains, maps each tab to calculator groups, and publishes a grouped shareable link with `--create-link` — ready to attach to a funding application without manual re-entry.

## What it does

1. Parses the Cloudera workbook (Datalake, CDE, CDW, CDF, COD, CAI/CML, multiple Datahub tabs, S3)
2. Groups resources by **Purpose** (FreeIPA, DL Master, Liftie nodes, etc.)
3. Bundles attached `gp3` / `standard` / `st1` storage into parent EC2 entries
4. Optionally publishes a shareable `calculator.aws` link grouped like your manual ADR estimates

## Install

After cloning or moving this repo, recreate the virtualenv (moving the folder breaks an existing `.venv`):

```bash
cd /Users/njlamsal/Documents/GitHub/pricing-automation
./setup.sh
source .venv/bin/activate
```

Or manually:

```bash
cd /Users/njlamsal/Documents/GitHub/pricing-automation
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
npm install
```

If you see `bad interpreter: /Users/njlamsal/pricing-automation/.venv/...`, delete `.venv` and run `./setup.sh` again.

## Usage (AWS)

```bash
cdp-aws-estimate \
  "/path/to/AUTOMATION- CDP on AWS Pricing Calculator -v7.xlsx" \
  --customer "Example Corp" \
  --manifest-out example-manifest.json \
  --report-out example-report.txt \
  --create-link
```

## Usage (Azure)

This tool parses the CDP on Azure workbook, validates totals against the Summary sheet, and can publish a **shareable calculator URL** with `--create-link` (browser automation via Playwright — Microsoft requires sign-in to enable **Share estimate**).

```bash
cdp-azure-estimate \
  "/path/to/CDP on Azure Pricing Calculator -v7.xlsx" \
  --customer "Example Corp" \
  --manifest-out azure-manifest.json \
  --create-link --headed
```

First run: use `--headed`, sign in when the browser opens; auth is saved to `.azure-calculator-auth.json` for later headless runs.

Optional manual helper workbook:

```bash
cdp-azure-estimate ... --import-out azure-calculator-import.xlsx
```

Install browser deps once: `npm install && npx playwright install chromium`

### Flags

| Flag | Description |
|---|---|
| `--customer` | Required. Used for estimate title: `{Customer} Pricing` |
| `--manifest-out` | Write normalized JSON manifest |
| `--report-out` | Write validation report |
| `--create-link` | Publish to calculator.aws and print shareable URL |
| `--json` | Also print manifest JSON to stdout |

## Datahub tabs

The parser supports:

- **v7 style:** `Datahub 1` with template selected in `A1` (e.g. `Streams Messaging Heavy Duty`)
- **Named DH tabs:** `Flow Management DH`, `Streams Messaging DH` (template in `A1`)
- **Duplicated tabs:** `Datahub DF`, `Datahub DE`, `Datahub DW`, etc.
- **Summary chain:** reads Summary columns C and D (~rows 22+) for additional Datahub tab references

Each enabled Datahub tab becomes its own calculator group:

`Data Hub - {template name}`

## Group mapping

| Cloudera source | Calculator group |
|---|---|
| Datalake | Data Lake Core |
| CDE | Cloudera Data Engineering |
| CDW | Cloudera Data Warehouse |
| CDF | Cloudera Data Flow |
| COD | Cloudera Operational Database |
| CAI / CML tabs | Cloudera AI - … |
| Each Datahub tab | Data Hub - {template} |
| Summary S3 | Storage |

Description aliases live in `config/aliases.yaml`.

## Tests

```bash
pytest
```

## Notes

- Prefer **Google Sheets export with calculated values** or live Sheets API; cached xlsx formulas may be stale.
- `--create-link` uses the public calculator.aws save API via `scripts/build_estimate.mjs`.
- Sheet **Cloudera** costs are ignored; only AWS-native resources are exported.
