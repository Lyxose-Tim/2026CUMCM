import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function argument(name, fallback) {
  const position = process.argv.indexOf(name);
  return position >= 0 ? process.argv[position + 1] : fallback;
}


async function sha256(file) {
  const content = await fs.readFile(file);
  return crypto.createHash("sha256").update(content).digest("hex");
}


async function assertHash(file, expected) {
  const actual = await sha256(file);
  if (actual !== expected) {
    throw new Error(`Hash mismatch for ${file}: ${actual}`);
  }
}


const payloadFile = argument("--payload", ".scratch/q2_workbook/payload.json");
const destination = argument("--output", "results/result2.xlsx");
const previewDirectory = argument("--previews", ".scratch/q2_workbook/previews");
const payload = JSON.parse(await fs.readFile(payloadFile, "utf8"));
await assertHash(payload.verification_file, payload.verification_sha256);
await assertHash(payload.archive_manifest_file, payload.archive_manifest_sha256);
const verification = JSON.parse(await fs.readFile(payload.verification_file, "utf8"));
if (!verification.numerical_passed) {
  throw new Error("Formal result2.xlsx export is blocked by numerical validation");
}

const temperatureName = "\u6e29\u5ea6";
const moistureName = "\u6c34\u5206\u6d53\u5ea6";
const workbook = Workbook.create();
const temperature = workbook.worksheets.add(temperatureName);
const moisture = workbook.worksheets.add(moistureName);
const sheets = new Map([[temperatureName, temperature], [moistureName, moisture]]);
const header = [payload.template_A1, ...Array.from({ length: 21 }, (_, index) => index / 10)];

for (const sheet of sheets.values()) {
  sheet.showGridLines = false;
  sheet.getRange("A1:V1").values = [header];
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
}

for (const chunk of payload.chunks) {
  await assertHash(chunk.file, chunk.sha256);
  const matrix = JSON.parse(await fs.readFile(chunk.file, "utf8"));
  if (matrix.length !== chunk.rows || matrix.some((row) => row.length !== 22)) {
    throw new Error(`Invalid chunk dimensions: ${chunk.file}`);
  }
  const target = sheets.get(chunk.sheet);
  if (!target) throw new Error(`Unexpected sheet: ${chunk.sheet}`);
  target.getRangeByIndexes(chunk.first_excel_row - 1, 0, chunk.rows, 22).values = matrix;
}

for (const sheet of sheets.values()) {
  const used = sheet.getRange("A1:V259201");
  used.format.font = { name: "Arial", size: 10, color: "#1F2937" };
  used.format.verticalAlignment = "center";
  sheet.getRange("A1:V1").format = {
    fill: "#1F4E78",
    font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#17365D" },
  };
  sheet.getRange("A2:A259201").format.numberFormat = "0";
  sheet.getRange("B2:V259201").format.numberFormat = "0.0000";
  sheet.getRange("A1:A259201").format.columnWidth = 12;
  sheet.getRange("B1:V259201").format.columnWidth = 11;
  sheet.getRange("A1:V1").format.rowHeight = 22;
}

workbook.recalculate();
for (const sheetName of [temperatureName, moistureName]) {
  const head = await workbook.inspect({
    kind: "region", sheetId: sheetName, range: "A1:H5", maxChars: 5000,
  });
  const tail = await workbook.inspect({
    kind: "region", sheetId: sheetName, range: "A259198:H259201", maxChars: 5000,
  });
  if (!head.ndjson || !tail.ndjson) throw new Error(`Inspection failed for ${sheetName}`);
}

await fs.mkdir(previewDirectory, { recursive: true });
for (const sheetName of [temperatureName, moistureName]) {
  const preview = await workbook.render({
    sheetName, range: "A1:H12", scale: 1, format: "png",
  });
  const output = new Uint8Array(await preview.arrayBuffer());
  await fs.writeFile(path.join(previewDirectory, `${sheetName}.png`), output);
}

await fs.mkdir(path.dirname(destination), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(destination);
console.log(JSON.stringify({ output: destination, bytes: (await fs.stat(destination)).size }));
