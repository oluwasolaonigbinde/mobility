import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { evaluateAudit } from "./check_frontend_audit.mjs";

const chain = ["braces", "micromatch", "fast-glob", "@next/eslint-plugin-next", "eslint-config-next"];
const lock = JSON.parse(readFileSync(new URL("../frontend/package-lock.json", import.meta.url)));
const before = new Date("2026-11-04T23:59:59.999Z");
const after = new Date("2026-11-05T00:00:00Z");
function report() {
  return {
    auditReportVersion: 2,
    vulnerabilities: Object.fromEntries(chain.map((name, index) => [name, {
      name, severity: "high", nodes: [`node_modules/${name}`],
      via: index ? [chain[index - 1]] : [{
        name: "braces", severity: "high",
        url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
      }],
    }])),
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 5, critical: 0, total: 5 } },
  };
}

test("only the dev-only lint chain is waived through the final expiry instant", () => {
  assert.deepEqual(evaluateAudit(report(), lock, before), { waived: chain, failures: [] });
});
test("expiry refuses every affected high finding", () => {
  assert.deepEqual(evaluateAudit(report(), lock, after), { waived: [], failures: chain });
});
test("clean and lower-severity reports still pass after expiry", () => {
  const clean = report();
  clean.vulnerabilities = {};
  clean.metadata.vulnerabilities.high = clean.metadata.vulnerabilities.total = 0;
  assert.deepEqual(evaluateAudit(clean, lock, after), { waived: [], failures: [] });
  const lower = report();
  for (const entry of Object.values(lower.vulnerabilities)) entry.severity = "moderate";
  lower.metadata.vulnerabilities.high = 0;
  lower.metadata.vulnerabilities.moderate = 5;
  assert.deepEqual(evaluateAudit(lower, lock, after), { waived: [], failures: [] });
});
test("another advisory in the same package blocks the entire propagated chain", () => {
  const value = report();
  value.vulnerabilities.braces.via.push({ name: "braces", severity: "high", url: "https://github.com/advisories/GHSA-other" });
  assert.deepEqual(evaluateAudit(value, lock, before).failures, chain);
});
test("unrelated high and critical findings fail", () => {
  for (const severity of ["high", "critical"]) {
    const value = report();
    value.vulnerabilities.other = { name: "other", severity, nodes: ["node_modules/other"], via: [{ url: "https://github.com/advisories/GHSA-other" }] };
    value.metadata.vulnerabilities[severity] += 1;
    value.metadata.vulnerabilities.total += 1;
    assert.deepEqual(evaluateAudit(value, lock, before).failures, ["other"]);
  }
});
test("production, direct and second-root exposure cannot use the waiver", () => {
  for (const mutate of [
    (value) => { value.packages["node_modules/braces"].dev = false; },
    (value) => { value.packages[""].devDependencies.braces = "3.0.3"; },
    (value) => { value.packages[""].dependencies["eslint-config-next"] = "16.3.6"; },
    (value) => { value.packages["node_modules/other"] = { dev: true, dependencies: { "fast-glob": "3.3.1" } }; },
    (value) => { value.packages["node_modules/other"] = { dev: true, optionalDependencies: { braces: "3.0.3" } }; },
    (value) => { value.packages["node_modules/other"] = { dev: true, peerDependencies: { braces: "3.0.3" } }; },
  ]) {
    const changed = structuredClone(lock);
    mutate(changed);
    assert(evaluateAudit(report(), changed, before).failures.includes("braces"));
  }
});
test("every reported node is checked including nested installs", () => {
  const value = report();
  value.vulnerabilities.braces.nodes.push("node_modules/other/node_modules/braces");
  const changed = structuredClone(lock);
  changed.packages["node_modules/other"] = { dev: true, dependencies: { braces: "3.0.3" } };
  changed.packages["node_modules/other/node_modules/braces"] = { dev: true };
  assert(evaluateAudit(value, changed, before).failures.includes("braces"));
});
test("unknown references and cycles fail closed", () => {
  for (const via of [["missing"], ["eslint-config-next"]]) {
    const value = report();
    value.vulnerabilities.braces.via = via;
    assert.deepEqual(evaluateAudit(value, lock, before).failures, chain);
  }
});
test("malformed reports, metadata mismatches and operational errors fail closed", () => {
  for (const mutate of [
    (value) => { delete value.metadata; },
    (value) => { delete value.vulnerabilities.braces; },
    (value) => { value.metadata.vulnerabilities.high = 0; },
    (value) => { value.metadata.vulnerabilities.total = 0; },
    (value) => { value.error = { code: "ENETWORK" }; },
    (value) => { value.auditReportVersion = 1; },
    (value) => { value.vulnerabilities.braces.nodes = []; },
    (value) => { value.vulnerabilities.braces.via = []; },
  ]) {
    const value = report();
    mutate(value);
    assert.throws(() => evaluateAudit(value, lock, before));
  }
  assert.throws(() => evaluateAudit(report(), lock, new Date("invalid")));
});
