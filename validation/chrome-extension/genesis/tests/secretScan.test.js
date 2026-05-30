// Tests from PITFALLS.md Pitfall 4 - Implementation block
// Scans all JS files for API key patterns - zero matches required

import { readFileSync, readdirSync, statSync } from "fs";
import { join, resolve } from "path";
import { fileURLToPath } from "url";
import { dirname } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const API_KEY_PATTERN = /[A-Za-z0-9_\-]{32,}/g;
const EXCLUDED_FILES = ["secretScan.test.js", "storage.test.js", "ruleManager.test.js", "domainUtils.test.js"];

function collectJsFiles(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      results.push(...collectJsFiles(full));
    } else if (entry.endsWith(".js") && !EXCLUDED_FILES.includes(entry)) {
      results.push(full);
    }
  }
  return results;
}

describe("secret scan - no API keys in bundle", () => {
  const srcDir = resolve(__dirname, "../src");
  const files = collectJsFiles(srcDir);

  test("src/ contains at least one JS file to scan", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  for (const file of files) {
    test(`${file} contains no string matching API key pattern (32+ alphanumeric chars)`, () => {
      const content = readFileSync(file, "utf8");
      const lines = content.split("\n");
      for (const line of lines) {
        if (line.trim().startsWith("//")) continue;
        const matches = line.match(API_KEY_PATTERN);
        if (matches) {
          // Allow import paths and URLs
          const suspicious = matches.filter(m => !m.includes("/") && !m.includes("."));
          expect(suspicious).toHaveLength(0);
        }
      }
    });
  }
});
