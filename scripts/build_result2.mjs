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

const payloadFile = argument("--payload", ".scratch/q2_workbook/payload.json");
const previewDirectory = argument("--previews", ".scratch/q2_workbook/previews");
if (!process.argv.includes("--preview-only")) {
  throw new Error("Use q2.export: the Artifact Tool stage is intentionally bounded to a rendered format blueprint");
}
const payload = JSON.parse(await fs.readFile(payloadFile, "utf8"));
if (await sha256(payload.verification_file) !== payload.verification_sha256) {
  throw new Error("Q2 verification hash mismatch");
}
if (await sha256(payload.archive_manifest_file) !== payload.archive_manifest_sha256) {
  throw new Error("Q2 archive manifest hash mismatch");
}

const names = ["\u6e29\u5ea6", "\u6c34\u5206\u6d53\u5ea6"];
const workbook = Workbook.create();
const sheets = new Map(names.map((name) => [name, workbook.worksheets.add(name)]));
const header = [payload.template_A1, ...Array.from({ length: 21 }, (_, index) => index / 10)];
for (const sheet of sheets.values()) {
  sheet.showGridLines = false;
  sheet.getRange("A1:V1").values = [header];
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
}
for (const sheetName of names) {
  const chunk = payload.chunks.find((item) => item.sheet === sheetName);
  if (await sha256(chunk.file) !== chunk.sha256) throw new Error(`Chunk hash mismatch: ${chunk.file}`);
  const sample = JSON.parse(await fs.readFile(chunk.file, "utf8")).slice(0, 11);
  sheets.get(sheetName).getRange("A2:V12").values = sample;
}
for (const sheet of sheets.values()) {
  sheet.getRange("A1:V12").format.font = { name: "Arial", size: 10, color: "#1F2937" };
  sheet.getRange("A1:V1").format = {
    fill: "#1F4E78",
    font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center", verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#17365D" },
  };
  sheet.getRange("A2:A12").format.numberFormat = "0";
  sheet.getRange("B2:V12").format.numberFormat = "0.0000";
  sheet.getRange("A1:A12").format.columnWidth = 12;
  sheet.getRange("B1:V12").format.columnWidth = 11;
}
workbook.recalculate();
await fs.mkdir(previewDirectory, { recursive: true });
for (const sheetName of names) {
  const inspection = await workbook.inspect({kind: "region", sheetId: sheetName, range: "A1:H12", maxChars: 5000});
  if (!inspection.ndjson) throw new Error(`Inspection failed for ${sheetName}`);
  const preview = await workbook.render({sheetName, range: "A1:H12", scale: 1, format: "png"});
  await fs.writeFile(path.join(previewDirectory, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const blueprint = await SpreadsheetFile.exportXlsx(workbook);
await blueprint.save(path.join(previewDirectory, "artifact_blueprint.xlsx"));
console.log(JSON.stringify({ artifact_tool_blueprint: true, rows_per_sheet: 12 }));
