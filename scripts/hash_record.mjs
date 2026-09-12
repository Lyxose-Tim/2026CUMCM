import crypto from "node:crypto";
import fs from "node:fs/promises";


export async function verifyHashRecord(file, record) {
  if (!record || typeof record.hash_scheme !== "string" || typeof record.sha256 !== "string") {
    throw new Error(`Unversioned hash record: ${file}`);
  }
  const raw = await fs.readFile(file);
  let content;
  if (record.hash_scheme === "sha256-raw-v1") {
    content = raw;
  } else if (record.hash_scheme === "sha256-text-lf-v2") {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
    content = Buffer.from(text.replace(/\r\n?/g, "\n"), "utf8");
  } else {
    throw new Error(`Unsupported hash scheme ${record.hash_scheme}: ${file}`);
  }
  const actual = crypto.createHash("sha256").update(content).digest("hex");
  if (actual !== record.sha256) {
    throw new Error(`Hash mismatch: ${file}`);
  }
}
