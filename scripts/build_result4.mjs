import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
import { verifyHashRecord } from './hash_record.mjs';

const arg = (name, fallback) => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : fallback;
const digest = async p => crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const previews = arg('--previews', '.scratch/q4/workbook_previews');
await fs.mkdir(previews, { recursive: true });
if (process.argv.includes('--template-only')) {
  const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(arg('--template', '')));
  console.log((await wb.inspect({ kind: 'region', sheetId: 'Sheet1', range: 'A1:F5', maxChars: 2500 })).ndjson);
  const blob = await wb.render({ sheetName: 'Sheet1', range: 'A1:F5', scale: 1.5, format: 'png' });
  await fs.writeFile(`${previews}/template.png`, new Uint8Array(await blob.arrayBuffer()));
  process.exit(0);
}
const payload = JSON.parse(await fs.readFile(arg('--payload', '.scratch/q4/workbook_payload.json'), 'utf8'));
for (const [file, record] of [[payload.template, payload.template_hash],
  [payload.verification_file, payload.verification_hash], [payload.run_file, payload.run_hash]]) {
  await verifyHashRecord(file, record);
}
if (JSON.parse(await fs.readFile(payload.verification_file, 'utf8')).passed !== true)
  throw new Error('Q4 numerical verification failed');
for (const [file, record] of Object.entries(payload.sources)) {
  await verifyHashRecord(file, record);
}
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(payload.template));
const sheet = wb.worksheets.getItem('Sheet1');
const last = payload.rows.length + 1;
sheet.getRange(`A1:W${last}`).clear({ applyTo: 'contents' });
sheet.getRange('A1:W1').values = [payload.headers];
sheet.getRange(`A2:W${last}`).values = payload.rows;
sheet.getRange(`B2:W${last}`).format.numberFormat = '0.0000';
sheet.getRange(`A2:A${last}`).format.numberFormat = '0.0000';
sheet.getRange('B1:V1').format.numberFormat = '0.000';
sheet.getRange(`A1:W${last}`).format.font = { name: 'Microsoft YaHei', size: 10 };
sheet.getRange(`A1:A${last}`).format.columnWidth = 33;
sheet.getRange(`B1:W${last}`).format.columnWidth = 10;
sheet.getRange('A1:W1').format.rowHeight = 28;
sheet.getRange('A1:W1').format.horizontalAlignment = 'center';
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(1);
console.log((await wb.inspect({ kind: 'region', sheetId: 'Sheet1', range: 'A1:H5', maxChars: 1800 })).ndjson);
console.log((await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',
  options: { useRegex: true, maxResults: 10 }, summary: 'error scan' })).ndjson);
for (const [name, range] of [['head', 'A1:H8'], ['tail', `A${last - 5}:H${last}`]]) {
  const blob = await wb.render({ sheetName: 'Sheet1', range, scale: 1.5, format: 'png' });
  await fs.writeFile(`${previews}/${name}.png`, new Uint8Array(await blob.arrayBuffer()));
}
await fs.mkdir('results', { recursive: true });
await (await SpreadsheetFile.exportXlsx(wb)).save(payload.output);
console.log(JSON.stringify({ output: payload.output, rows: payload.rows.length, columns: 23, sha256: await digest(payload.output) }));

