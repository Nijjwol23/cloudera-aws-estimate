#!/usr/bin/env node
/**
 * Publish an Azure Pricing Calculator shared estimate from a normalized manifest.
 *
 * Uses Playwright against https://azure.microsoft.com/pricing/calculator/
 * because Microsoft does not document a public create-estimate API (unlike AWS).
 *
 * Share links require a signed-in Microsoft account. Use --headed on first run.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const CALCULATOR_URL = "https://azure.microsoft.com/en-us/pricing/calculator/";

const REGION_LABELS = {
  eastus: "East US",
  eastus2: "East US 2",
  westus: "West US",
  westus2: "West US 2",
  centralus: "Central US",
  northcentralus: "North Central US",
  southcentralus: "South Central US",
  westcentralus: "West Central US",
  canadacentral: "Canada Central",
  canadaeast: "Canada East",
  brazilsouth: "Brazil South",
  northeurope: "North Europe",
  westeurope: "West Europe",
  uksouth: "UK South",
  ukwest: "UK West",
  francecentral: "France Central",
  germanywestcentral: "Germany West Central",
  swedencentral: "Sweden Central",
  switzerlandnorth: "Switzerland North",
  norwayeast: "Norway East",
  australiaeast: "Australia East",
  australiasoutheast: "Australia Southeast",
  southeastasia: "Southeast Asia",
  eastasia: "East Asia",
  japaneast: "Japan East",
  japanwest: "Japan West",
  koreacentral: "Korea Central",
  centralindia: "Central India",
  southindia: "South India",
  westindia: "West India",
};

function regionLabel(region) {
  return REGION_LABELS[String(region || "").toLowerCase()] || "East US";
}

function vmSizeLabel(armSku) {
  return String(armSku || "")
    .replace(/^Standard_/, "")
    .replace(/_/g, " ")
    .trim();
}

function sharedEstimateUrl(id) {
  const compact = String(id).replace(/-/g, "");
  return `https://azure.microsoft.com/en-us/pricing/calculator/?shared-estimate=${compact}`;
}

async function waitForCalculator(page) {
  await page.goto(CALCULATOR_URL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => window.pricing && window.pricing.calcIsInitialized,
    undefined,
    { timeout: 120_000 }
  );
  await page.getByPlaceholder("Search products").waitFor({ timeout: 60_000 });
}

async function searchAndAddProduct(page, query) {
  const search = page.getByPlaceholder("Search products");
  await search.click();
  await search.fill("");
  await search.fill(query);
  await page.getByRole("button", { name: "Add to estimate" }).first().click();
  await page.waitForTimeout(1200);
}

async function latestProductNameInput(page) {
  return page.locator('input[name="product-name"]').last();
}

async function configureVirtualMachine(page, service, region) {
  const label = regionLabel(region);
  const nameInput = await latestProductNameInput(page);
  await nameInput.fill(service.description || "Virtual Machine");

  await page.getByRole("combobox", { name: "Region" }).last().selectOption({ label });
  await page.getByRole("combobox", { name: "Operating system" })
    .last()
    .selectOption("linux");

  const sizeText = vmSizeLabel(service.vm_size);
  const instanceCombo = page.getByRole("combobox", { name: /Instance/i }).last();
  await instanceCombo.click();
  await page.waitForTimeout(400);
  const option = page.getByRole("option", { name: new RegExp(sizeText, "i") }).first();
  if (await option.count()) {
    await option.click();
  } else {
    await page.keyboard.type(sizeText);
    await page.waitForTimeout(400);
    await page.getByRole("option").first().click();
  }

  await page
    .getByRole("spinbutton", { name: "Virtual machines" })
    .last()
    .fill(String(Math.max(1, Math.round(service.quantity || 1))));
  await page
    .getByRole("spinbutton", { name: /Hours/i })
    .last()
    .fill(String(Math.max(1, Math.round(service.hours_per_month || 730))));
}

async function configureAks(page, service, region) {
  const label = regionLabel(region);
  const nameInput = await latestProductNameInput(page);
  await nameInput.fill(service.description || "AKS");
  const regionCombo = page.getByRole("combobox", { name: "Region" }).last();
  if (await regionCombo.count()) {
    await regionCombo.selectOption({ label });
  }
}

async function configurePostgres(page, service, region) {
  const label = regionLabel(region);
  const nameInput = await latestProductNameInput(page);
  await nameInput.fill(service.description || "PostgreSQL");
  const regionCombo = page.getByRole("combobox", { name: "Region" }).last();
  if (await regionCombo.count()) {
    await regionCombo.selectOption({ label });
  }
}

async function configureAdls(page, service, region) {
  const label = regionLabel(region);
  const nameInput = await latestProductNameInput(page);
  await nameInput.fill(service.description || "ADLS Storage");
  const regionCombo = page.getByRole("combobox", { name: "Region" }).last();
  if (await regionCombo.count()) {
    await regionCombo.selectOption({ label });
  }
  const tb = Math.max(0.1, Number(service.storage_tb || 1));
  const capacity = page.getByRole("spinbutton").last();
  if (await capacity.count()) {
    await capacity.fill(String(Math.round(tb * 1024)));
  }
}

async function addService(page, service, region, groupName) {
  const description = `${groupName} — ${service.description || service.type}`;
  const payload = { ...service, description };

  switch (service.type) {
    case "vm":
      await searchAndAddProduct(page, "Virtual Machines");
      await configureVirtualMachine(page, payload, region);
      return;
    case "aks":
      await searchAndAddProduct(page, "Azure Kubernetes Service");
      await configureAks(page, payload, region);
      return;
    case "postgres_flexible":
      await searchAndAddProduct(page, "Azure Database for PostgreSQL");
      await configurePostgres(page, payload, region);
      return;
    case "mysql_flexible":
      await searchAndAddProduct(page, "Azure Database for MySQL");
      await configurePostgres(page, payload, region);
      return;
    case "adls":
      await searchAndAddProduct(page, "Storage");
      await configureAdls(page, payload, region);
      return;
    default:
      await searchAndAddProduct(page, "Virtual Machines");
      await configureVirtualMachine(
        page,
        {
          type: "vm",
          description: payload.description,
          vm_size: "Standard_D2s_v3",
          quantity: service.quantity || 1,
          hours_per_month: service.hours_per_month || 730,
        },
        region
      );
  }
}

async function waitForShareEnabled(page, headed, loginTimeoutMs) {
  const share = page.getByRole("button", { name: "Share Estimate" });
  await share.scrollIntoViewIfNeeded();
  const deadline = Date.now() + loginTimeoutMs;
  while (Date.now() < deadline) {
    if (!(await share.isDisabled())) {
      return share;
    }
    if (!headed) {
      break;
    }
    await page.waitForTimeout(2000);
  }
  throw new Error(
    "Share Estimate is disabled. Microsoft requires sign-in to publish a share link.\n" +
      "Re-run with --create-link --headed, sign in when the browser opens, then wait for the script to finish."
  );
}

async function main() {
  const manifestPath = process.argv[2];
  const headed = process.argv.includes("--headed");
  const authStatePath =
    process.argv.find((arg) => arg.startsWith("--auth-state="))?.split("=")[1] ||
    path.join(ROOT, ".azure-calculator-auth.json");

  if (!manifestPath) {
    console.error(
      "Usage: node scripts/build_azure_estimate.mjs manifest.json [--headed] [--auth-state=path]"
    );
    process.exit(1);
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const services = manifest.groups.flatMap((group) =>
    group.services.map((service) => ({ group: group.name, service }))
  );

  let sharePayload = null;
  const browser = await chromium.launch({ headless: !headed });
  const contextOptions = fs.existsSync(authStatePath)
    ? { storageState: authStatePath }
    : {};
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();

  page.on("response", async (response) => {
    const url = response.url();
    if (
      !url.includes("/api/v2/calculator/shared-estimates") ||
      response.request().method() !== "POST"
    ) {
      return;
    }
    try {
      sharePayload = await response.json();
    } catch {
      /* ignore */
    }
  });

  try {
    await waitForCalculator(page);

    let added = 0;
    for (const { group, service } of services) {
      try {
        await addService(page, service, manifest.region, group);
        added += 1;
      } catch (error) {
        console.error(`Warning: skipped ${group} / ${service.description}: ${error.message}`);
      }
    }

    const shareButton = await waitForShareEnabled(page, headed, headed ? 600_000 : 5_000);
    await shareButton.click();
    await page.waitForTimeout(5000);

    let estimateId = sharePayload?.id;
    if (!estimateId) {
      const linkInput = page.locator('input[value*="shared-estimate"], input[value*="azure.com/e/"]');
      if (await linkInput.count()) {
        const value = await linkInput.first().inputValue();
        const match =
          value.match(/shared-estimate=([a-f0-9]+)/i) ||
          value.match(/azure\.com\/e\/([a-f0-9]+)/i);
        if (match) {
          estimateId = match[1];
        }
      }
    }

    if (!estimateId) {
      throw new Error(
        "Could not capture a share link after clicking Share Estimate. " +
          "Ensure you are signed in (--headed) and try again."
      );
    }

    if (fs.existsSync(path.dirname(authStatePath)) || authStatePath.startsWith(ROOT)) {
      await context.storageState({ path: authStatePath });
    }

    const url = sharedEstimateUrl(estimateId);
    console.log(
      JSON.stringify(
        {
          url,
          estimate_id: estimateId,
          groups: manifest.groups.length,
          services_added: added,
          services_expected: services.length,
          name: manifest.name,
          note: "Azure share links require Microsoft sign-in; re-use --auth-state for later runs.",
        },
        null,
        2
      )
    );
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
