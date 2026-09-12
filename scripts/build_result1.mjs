import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
import { verifyHashRecord } from './hash_record.mjs';

const payloadPath = process.argv[2] ?? '.scratch/q1_workbook_payload.json';
const outputPath = process.argv[3] ?? 'results/result1.xlsx';
const payload = JSON.parse(await fs.readFile(payloadPath, 'utf8'));
await verifyHashRecord(payload.verification_file, payload.verification_hash);
await verifyHashRecord(payload.archive_manifest_file, payload.archive_manifest_hash);
const verification = JSON.parse(await fs.readFile(payload.verification_file,'utf8'));
if (!verification.numerical_passed) throw new Error('Numerical validation blocks formal export');
if (payload.worksheets.length !== 2) throw new Error('Expected two sheets');
const workbook = Workbook.create();
const previewDir = path.dirname(payloadPath);
for (const [index, source] of payload.worksheets.entries()) {
  if (source.values.length !== 1801 || source.values.some(r => r.length !== 22)) throw new Error('Wrong output shape');
  const sheet = workbook.worksheets.add(source.name);
  sheet.getRange('A1:V1801').values = source.values;
  sheet.getRange('A1:V1801').format.font = {name:'Microsoft YaHei',size:10};
  sheet.getRange('A1:V1801').format.rowHeight = 18;
  sheet.getRange('A1:A1801').format.columnWidth = 34;
  sheet.getRange('B1:V1801').format.columnWidth = 11;
  sheet.getRange('B2:V1801').setNumberFormat('0.0000');
  sheet.getRange('A2:A1801').setNumberFormat('0');
  sheet.getRange('A1:V1').format = {fill:'#EEF2F6',font:{name:'Microsoft YaHei',size:10,bold:true},rowHeight:25};
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  const inspected = await workbook.inspect({kind:'table',range:`'${source.name}'!A1:D4`,include:'values',tableMaxRows:4,tableMaxCols:4,maxChars:1500});
  console.log(inspected.ndjson);
  const preview = await workbook.render({sheetName:source.name,range:'A1:H10',scale:1.5,format:'png'});
  await fs.writeFile(path.join(previewDir,`result1_sheet_${index}.png`),new Uint8Array(await preview.arrayBuffer()));
}
const errors = await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1500});
console.log(errors.ndjson);
await fs.mkdir(path.dirname(outputPath),{recursive:true});
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(outputPath);
console.log(`Saved ${outputPath}`);
