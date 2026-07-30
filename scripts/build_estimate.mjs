#!/usr/bin/env node
/**
 * Publish a calculator.aws estimate from a normalized manifest.
 *
 * Used by cdp-aws-estimate --create-link so funding applications get a
 * shareable AWS estimate without manually re-entering spreadsheet line items.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const MCP_SERVER = path.join(
  ROOT,
  "node_modules/sample-aws-pricing-calculator-mcp/dist/mcp-server.js"
);
const CATALOG_DIR = path.join(
  ROOT,
  "node_modules/sample-aws-pricing-calculator-mcp/catalog/services"
);

function loadCatalogEntry(serviceCode) {
  const file = path.join(CATALOG_DIR, `${serviceCode}.json`);
  if (!fs.existsSync(file)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const EC2_CATALOG = loadCatalogEntry("ec2Enhancement");
const RDS_PG_CATALOG = loadCatalogEntry("amazonRDSPostgreSQLDB");
const S3_GROUP_CATALOG = loadCatalogEntry("amazonSimpleStorageServiceGroup");

function hoursToUtilization(hours) {
  const pct = Math.min(100, Math.round((Number(hours || 730) / 730) * 100));
  return String(Math.max(1, pct));
}

function mergeConfig(base, overrides) {
  return { ...(base || {}), ...overrides };
}

function ec2Config(item, region) {
  const totalStorage = (item.ebs_volumes || []).reduce(
    (sum, volume) => sum + Number(volume.size_gb || 0),
    0
  );

  const config = mergeConfig(EC2_CATALOG?.minimalConfig, {
    region,
    description: item.description,
    instanceType: item.instance_type,
    workload: Math.max(1, Math.round(Number(item.quantity) || 1)),
    selectedOS: "linux",
    tenancy: "shared",
    pricingStrategy: "ondemand",
    utilization: hoursToUtilization(item.hours_per_month),
  });

  if (totalStorage > 0) {
    config.storageAmount = {
      value: String(Math.round(totalStorage)),
      unit: "gb|NA",
    };
  } else {
    delete config.storageAmount;
    delete config.storageType;
  }

  return { serviceCode: "ec2Enhancement", config };
}

function rdsConfig(item, region) {
  const serviceCode =
    item.engine === "MySQL" ? "amazonRDSMySQLDB" : "amazonRDSPostgreSQLDB";
  const base = serviceCode === "amazonRDSPostgreSQLDB"
    ? RDS_PG_CATALOG?.minimalConfig
    : null;

  const storageGb = {
    value: String(Math.max(20, Math.round(item.storage_gb || 100))),
    unit: "gb|NA",
  };
  const storageFields =
    item.engine === "MySQL"
      ? { storageType: "General Purpose-GP3", storageAmount: storageGb }
      : { storageVolume: "General Purpose-GP3", storageAmount: storageGb };

  return {
    serviceCode,
    config: mergeConfig(base, {
      region,
      description: item.description,
      columnFormIPM: {
        value: [
          {
            "Number of Nodes": {
              value: String(Math.max(1, Math.round(item.quantity || 1))),
            },
            "Instance Type": { value: item.instance_class },
            "Deployment Option": {
              value: item.multi_az ? "Multi-AZ" : "Single-AZ",
            },
            TermType: { value: "OnDemand" },
            undefined: {
              value: {
                unit: hoursToUtilization(item.hours_per_month),
                selectedId: "%Utilized/Month",
              },
            },
          },
        ],
      },
      ...storageFields,
    }),
  };
}

function buildEksConfig(item, region, serviceFields) {
  const fieldIds = new Set((serviceFields?.fields || []).map((field) => field.id));
  const config = mergeConfig(serviceFields?.catalog?.minimalConfig, {
    region,
    description: item.description,
  });

  const clusters = String(Math.max(1, Math.round(Number(item.clusters || 1))));
  if (fieldIds.has("numberOfClusters")) {
    config.numberOfClusters = clusters;
  } else if (fieldIds.has("numberOfEKSClusters")) {
    config.numberOfEKSClusters = clusters;
  } else {
    config.numberOfClusters = clusters;
  }

  return { serviceCode: "awsEks", config };
}

function buildEfsConfig(item, region, serviceFields) {
  const throughputField = (serviceFields?.fields || []).find(
    (field) => field.id === "throughputModeSS"
  );
  const elasticThroughputId =
    throughputField?.defaultValue ||
    throughputField?.options?.find((option) =>
      /elastic throughput/i.test(option.label)
    )?.id ||
    "pPg1vmtASUb_DcOGFyxPNa8abU3NDsNcdbBc06f_K_U";

  const config = mergeConfig(serviceFields?.catalog?.minimalConfig, {
    region,
    description: item.description,
    throughputModeSS: elasticThroughputId,
    standardStorageSize: {
      value: String(Math.max(1, Math.round(Number(item.size_gb || 0)))),
      unit: "gb|NA",
    },
  });

  return { serviceCode: "amazonEFS", config };
}

function s3Config(item, region) {
  const gb = Math.max(
    1,
    Math.round(Number(item.standard_storage_tb || 0) * 1024)
  );
  const base = S3_GROUP_CATALOG?.minimalConfig?.amazonS3Standard || {
    region: "us-east-1",
    s3StandardStorageSize: { value: "500", unit: "gb|month" },
  };

  return {
    serviceCode: "amazonS3Standard",
    config: mergeConfig(base, {
      region,
      description: item.description,
      s3StandardStorageSize: { value: String(gb), unit: "gb|month" },
    }),
  };
}

function toAddServiceCall(item, region, groupName, serviceFields) {
  let payload;
  switch (item.type) {
    case "ec2":
      payload = ec2Config(item, region);
      break;
    case "rds":
      payload = rdsConfig(item, region);
      break;
    case "eks":
      payload = buildEksConfig(item, region, serviceFields.awsEks);
      break;
    case "efs":
      payload = buildEfsConfig(item, region, serviceFields.amazonEFS);
      break;
    case "s3":
      payload = s3Config(item, region);
      break;
    default:
      throw new Error(`Unsupported service type: ${item.type}`);
  }

  return {
    service: payload.serviceCode,
    group: groupName,
    instance: item.description,
    config: payload.config,
  };
}

async function callTool(client, name, args) {
  const result = await client.callTool({ name, arguments: args });
  const text = result.content?.find((part) => part.type === "text")?.text || "";
  if (result.isError) {
    throw new Error(`${name} failed: ${text}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function normalizeAddServiceResults(parsed) {
  if (Array.isArray(parsed)) {
    return parsed;
  }
  if (Array.isArray(parsed?.results)) {
    return parsed.results;
  }
  return [parsed];
}

function summarizeFailures(failures) {
  const lines = failures.slice(0, 12).map(
    (entry) =>
      `${entry.group} / ${entry.description} (${entry.type}): ${entry.error}`
  );
  const uniqueErrors = [
    ...new Set(failures.map((entry) => String(entry.error).split("\n")[0])),
  ];
  if (uniqueErrors.length <= 4) {
    lines.push("", "Error patterns:", ...uniqueErrors.map((msg) => `  - ${msg}`));
  }
  return lines.join("\n  ");
}

async function loadServiceFields(client) {
  const response = await callTool(client, "get_service_fields", {
    service: "awsEks,amazonEFS",
  });
  if (Array.isArray(response)) {
    return {
      awsEks: response.find((entry) => entry.serviceCode === "awsEks") || null,
      amazonEFS:
        response.find((entry) => entry.serviceCode === "amazonEFS") || null,
    };
  }
  if (response?.serviceCode === "awsEks") {
    return { awsEks: response, amazonEFS: null };
  }
  if (response?.serviceCode === "amazonEFS") {
    return { awsEks: null, amazonEFS: response };
  }
  return {
    awsEks: response?.services?.awsEks || response?.awsEks || null,
    amazonEFS: response?.services?.amazonEFS || response?.amazonEFS || null,
  };
}

async function main() {
  const manifestPath = process.argv[2];
  if (!manifestPath) {
    console.error("Usage: node scripts/build_estimate.mjs path/to/manifest.json");
    process.exit(1);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const expectedServices = manifest.groups.reduce(
    (count, group) => count + group.services.length,
    0
  );

  const transport = new StdioClientTransport({
    command: "node",
    args: [MCP_SERVER],
    cwd: ROOT,
  });
  const client = new Client({ name: "cdp-aws-estimator", version: "0.1.0" });
  await client.connect(transport);

  try {
    const serviceFields = await loadServiceFields(client);

    const created = await callTool(client, "create_estimate", {
      name: manifest.name,
    });
    const estimateId = created.estimate_id || created.estimateId || created.id;
    if (!estimateId) {
      throw new Error(
        `create_estimate returned unexpected payload: ${JSON.stringify(created)}`
      );
    }

    const failures = [];
    let added = 0;

    for (const group of manifest.groups) {
      for (const item of group.services) {
        const serviceEntry = toAddServiceCall(
          item,
          manifest.region,
          group.name,
          serviceFields
        );
        const response = await callTool(client, "add_service", {
          estimate_id: estimateId,
          services: JSON.stringify([serviceEntry]),
        });
        const results = normalizeAddServiceResults(response);
        if (results.length === 0) {
          failures.push({
            group: group.name,
            description: item.description,
            type: item.type,
            error: "add_service returned no results",
          });
          continue;
        }

        for (const result of results) {
          if (result.error) {
            failures.push({
              group: group.name,
              description: item.description,
              type: item.type,
              error: result.error,
            });
            continue;
          }
          if (result.partial) {
            failures.push({
              group: group.name,
              description: item.description,
              type: item.type,
              error:
                result.next_step ||
                `Missing required fields: ${(result.missing_required_fields || []).join(", ")}`,
            });
            continue;
          }
          if (result.success) {
            added += 1;
            continue;
          }
          failures.push({
            group: group.name,
            description: item.description,
            type: item.type,
            error: result.warning || JSON.stringify(result),
          });
        }
      }
    }

    if (failures.length > 0) {
      throw new Error(
        `Only ${added}/${expectedServices} services were added to the estimate.\n` +
          `  ${summarizeFailures(failures)}` +
          (failures.length > 12 ? `\n  ...and ${failures.length - 12} more` : "")
      );
    }

    const validation = await callTool(client, "validate_estimate", {
      estimate_id: estimateId,
    });
    const verdict = validation.lint_verdict || validation.status;
    if (verdict === "read-only" || verdict === "required-input") {
      throw new Error(
        `Estimate failed pre-save validation (${verdict}).\n` +
          `  ${validation.next_step || JSON.stringify(validation.lint_services || validation)}`
      );
    }

    const exported = await callTool(client, "export_estimate", {
      estimate_id: estimateId,
    });
    const url =
      exported.sharable_url ||
      exported.shareable_url ||
      exported.shareableUrl ||
      exported.url;
    if (!url) {
      throw new Error(
        `export_estimate returned unexpected payload: ${JSON.stringify(exported)}`
      );
    }

    console.log(
      JSON.stringify(
        {
          url,
          estimate_id: estimateId,
          groups: manifest.groups.length,
          services_added: added,
          services_expected: expectedServices,
          lint_verdict: verdict || "ok",
          name: manifest.name,
        },
        null,
        2
      )
    );
  } finally {
    await client.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
