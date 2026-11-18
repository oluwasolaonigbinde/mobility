import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { evaluateAudit } from "./check_frontend_audit.mjs";

const lock = JSON.parse(readFileSync(new URL("../frontend/package-lock.json", import.meta.url)));
const before = new Date("2026-12-17T23:59:59.999Z");
const after = new Date("2026-12-18T00:00:00Z");
const advisory = {
  name: "picomatch", severity: "high", url: "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
};
const findings = [
  ["@next/eslint-plugin-next", ["fast-glob"]],
  ["@rollup/plugin-commonjs", ["picomatch", "fdir", "@rollup/pluginutils"]],
  ["@rollup/pluginutils", ["picomatch"]],
  ["@sentry/nextjs", ["@rollup/plugin-commonjs"]],
  ["@typescript-eslint/typescript-estree", ["tinyglobby"]],
  ["@vitejs/plugin-react", ["vite"]],
  ["@vitest/coverage-v8", ["vitest"]],
  ["eslint-config-next", ["@next/eslint-plugin-next", "eslint-import-resolver-typescript"]],
  ["eslint-import-resolver-typescript", ["tinyglobby"]],
  ["fast-glob", ["micromatch"]],
  ["fdir", ["picomatch"], ["@rollup/plugin-commonjs", "tinyglobby"]],
  ["micromatch", ["picomatch"]],
  ["picomatch", [advisory], ["", "@rollup/plugin-commonjs", "@rollup/pluginutils", "tinyglobby", "vite", "vitest"]],
  ["tinyglobby", ["fdir", "picomatch"]],
  ["vite", ["picomatch", "tinyglobby"]],
  ["vitest", ["picomatch", "tinyglobby"]],
];
const names = findings.map(([name]) => name);

function report() {
  return {
    auditReportVersion: 2,
    vulnerabilities: Object.fromEntries(findings.map(([name, via, containers = [""]]) => [name, {
      name, severity: "high", via: structuredClone(via),
      nodes: containers.map((parent) => `${parent ? `node_modules/${parent}/` : ""}node_modules/${name}`),
    }])),
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: names.length, critical: 0, total: names.length } },
  };
}

test("the 16 findings on the observed tooling paths are waived just before expiry", () => {
  assert.deepEqual(evaluateAudit(report(), lock, before), { waived: names, failures: [] });
});
test("the exception ends at the exact expiry instant", () => {
  assert.deepEqual(evaluateAudit(report(), lock, after), { waived: [], failures: names });
});
test("clean and lower-severity reports still pass after expiry", () => {
  const clean = report();
  clean.vulnerabilities = {};
  clean.metadata.vulnerabilities.high = clean.metadata.vulnerabilities.total = 0;
  assert.deepEqual(evaluateAudit(clean, lock, after), { waived: [], failures: [] });
  const lower = report();
  for (const entry of Object.values(lower.vulnerabilities)) entry.severity = "moderate";
  lower.vulnerabilities.picomatch.via[0].severity = "moderate";
  lower.metadata.vulnerabilities.high = 0;
  lower.metadata.vulnerabilities.moderate = names.length;
  assert.deepEqual(evaluateAudit(lower, lock, after), { waived: [], failures: [] });
});
test("another advisory blocks the entire propagated chain", () => {
  const value = report();
  value.vulnerabilities.picomatch.via.push({ ...advisory, url: "https://github.com/advisories/GHSA-other" });
  assert.deepEqual(evaluateAudit(value, lock, before).failures, names);
});
test("unrelated high and critical findings fail", () => {
  for (const severity of ["high", "critical"]) {
    const value = report();
    value.vulnerabilities.other = { name: "other", severity, nodes: ["node_modules/other"], via: [{ ...advisory, name: "other" }] };
    value.metadata.vulnerabilities[severity] += 1;
    value.metadata.vulnerabilities.total += 1;
    assert.deepEqual(evaluateAudit(value, lock, before).failures, ["other"]);
  }
});
test("a critical entry for the same advisory and its high parents fail", () => {
  const value = report();
  value.vulnerabilities.picomatch.severity = "critical";
  value.metadata.vulnerabilities.high -= 1;
  value.metadata.vulnerabilities.critical += 1;
  assert.deepEqual(evaluateAudit(value, lock, before).failures, names);
});
test("a high entry with a non-high advisory leaf and its parents fail", () => {
  const moderate = report();
  moderate.vulnerabilities.picomatch.via[0].severity = "moderate";
  assert.deepEqual(evaluateAudit(moderate, lock, before).failures, names);
  const critical = report();
  critical.vulnerabilities.picomatch.via[0].severity = "critical";
  assert.throws(() => evaluateAudit(critical, lock, before));
});
test("every reported path exists and belongs to the named package", () => {
  for (const path of ["node_modules/missing/node_modules/picomatch", "node_modules/vitest"]) {
    const value = report();
    value.vulnerabilities.picomatch.nodes.push(path);
    assert.deepEqual(evaluateAudit(value, lock, before).failures, names);
  }
});
test("only approved root declarations, dev markers and incoming edges are allowed", () => {
  for (const mutate of [
    (p) => { p["node_modules/picomatch"].dev = false; },
    (p) => { p[""].devDependencies.picomatch = "*"; },
    (p) => { p[""].devDependencies.vite = "*"; },
    (p) => { p[""].dependencies["eslint-config-next"] = "*"; },
    (p) => { p[""].optionalDependencies = { "@sentry/nextjs": "*" }; },
    (p) => { p["node_modules/next"].dependencies.picomatch = "*"; },
    (p) => { p["node_modules/next"].optionalDependencies = { ...p["node_modules/next"].optionalDependencies, tinyglobby: "*" }; },
    (p) => { p["node_modules/next"].peerDependencies = { ...p["node_modules/next"].peerDependencies, picomatch: "*" }; },
    (p) => {
      p["node_modules/@sentry/nextjs"].dependencies.other = "*";
      p["node_modules/other"] = { dependencies: { picomatch: "*" } };
    },
    (p) => { p["node_modules/@rollup/pluginutils"].dependencies = { fdir: "*" }; },
  ]) {
    const changed = structuredClone(lock);
    mutate(changed.packages);
    const { failures } = evaluateAudit(report(), changed, before);
    assert(failures.some((name) => ["picomatch", "@sentry/nextjs", "vite"].includes(name)));
  }
});
test("the real Vitest peer cycle passes, while runtime ingress or loss of its roots fails", () => {
  const value = report();
  assert.deepEqual(evaluateAudit(value, lock, before).waived, names);
  const changed = structuredClone(lock);
  changed.packages["node_modules/next"].dependencies.vitest = "*";
  assert(evaluateAudit(value, changed, before).failures.includes("@vitest/coverage-v8"));
  delete changed.packages["node_modules/next"].dependencies.vitest;
  delete changed.packages[""].devDependencies.vitest;
  delete changed.packages[""].devDependencies["@vitest/coverage-v8"];
  assert(evaluateAudit(value, changed, before).failures.includes("@vitest/coverage-v8"));
});
test("a new parent of an existing nested install blocks the exception", () => {
  const changed = structuredClone(lock);
  changed.packages["node_modules/@rollup/plugin-commonjs/node_modules/other"] = {
    optionalDependencies: { picomatch: "*" },
  };
  assert.deepEqual(evaluateAudit(report(), changed, before).failures, names);
});
test("unknown references are malformed and via cycles without the waived advisory fail", () => {
  const unknown = report();
  unknown.vulnerabilities.picomatch.via = ["missing"];
  assert.throws(() => evaluateAudit(unknown, lock, before));
  const cycle = report();
  cycle.vulnerabilities.picomatch.via = ["vite"];
  assert.deepEqual(evaluateAudit(cycle, lock, before).failures, names);
});
function withModerateBranches() {
  const value = report();
  for (const [parent, child] of [
    ["@sentry/nextjs", "@sentry/bundler-plugin-core"],
    ["@typescript-eslint/typescript-estree", "minimatch"],
    ["vitest", "@vitest/mocker"],
  ]) {
    value.vulnerabilities[parent].via.push(child);
    const nested = `node_modules/${parent}/node_modules/${child}`;
    value.vulnerabilities[child] = {
      name: child, severity: "moderate",
      nodes: [Object.hasOwn(lock.packages, nested) ? nested : `node_modules/${child}`],
      via: [{ ...advisory, name: child, severity: "moderate", url: "https://github.com/advisories/GHSA-moderate" }],
    };
    value.metadata.vulnerabilities.moderate += 1;
    value.metadata.vulnerabilities.total += 1;
  }
  value.vulnerabilities.vitest.via.push("@vitest/coverage-v8");
  return value;
}
test("moderate branches and the live vitest <-> coverage audit cycle stay waived", () => {
  assert.deepEqual(evaluateAudit(withModerateBranches(), lock, before), { waived: names, failures: [] });
});
test("a branch that becomes high with another advisory blocks its parents", () => {
  const value = withModerateBranches();
  value.vulnerabilities.minimatch.severity = "high";
  value.vulnerabilities.minimatch.via[0].severity = "high";
  value.metadata.vulnerabilities.moderate -= 1;
  value.metadata.vulnerabilities.high += 1;
  const { failures } = evaluateAudit(value, lock, before);
  assert(failures.includes("minimatch") && failures.includes("@typescript-eslint/typescript-estree"));
});
test("a moderate intermediate entry cannot hide a disqualifying cause", () => {
  const renamed = withModerateBranches();
  const changed = structuredClone(lock);
  changed.packages[renamed.vulnerabilities.minimatch.nodes[0]].name = "different-package";
  assert(evaluateAudit(renamed, changed, before).failures.includes("@typescript-eslint/typescript-estree"));
  // Unknown references, and high or critical advisories listed by a moderate entry,
  // are malformed reports even when no high entry is involved.
  const unknown = withModerateBranches();
  unknown.vulnerabilities.minimatch.via.push("missing");
  assert.throws(() => evaluateAudit(unknown, lock, after));
  const blank = withModerateBranches();
  blank.vulnerabilities["@vitest/mocker"].via = [{ name: "", url: "", severity: "moderate" }];
  assert.throws(() => evaluateAudit(blank, lock, before));
  for (const severity of ["high", "critical"]) {
    const value = withModerateBranches();
    value.vulnerabilities.minimatch.via.push(
      { ...advisory, name: "minimatch", severity, url: "https://github.com/advisories/GHSA-other" },
    );
    assert.throws(() => evaluateAudit(value, lock, before));
  }
});
test("a lower-rated branch that carries the cause or lists a missing node fails", () => {
  const value = withModerateBranches();
  const core = value.vulnerabilities["@sentry/bundler-plugin-core"];
  core.via.push("picomatch");
  const changed = structuredClone(lock);
  changed.packages[core.nodes[0]].dependencies = { ...changed.packages[core.nodes[0]].dependencies, picomatch: "*" };
  assert(evaluateAudit(value, changed, before).failures.includes("@sentry/nextjs"));
  const missing = withModerateBranches();
  missing.vulnerabilities.minimatch.nodes.push("node_modules/nowhere/node_modules/minimatch");
  assert(evaluateAudit(missing, lock, before).failures.includes("@typescript-eslint/typescript-estree"));
});
test("a lower-rated cycle member that reaches the cause blocks the waiver", () => {
  const value = report();
  value.vulnerabilities.vitest.via.push("@vitest/coverage-v8");
  value.vulnerabilities["@vitest/coverage-v8"].severity = "moderate";
  value.metadata.vulnerabilities.high -= 1;
  value.metadata.vulnerabilities.moderate += 1;
  assert(evaluateAudit(value, lock, before).failures.includes("vitest"));
});
test("advisories rated above their entry or without identity are malformed", () => {
  const anonymous = withModerateBranches();
  anonymous.vulnerabilities["@vitest/mocker"].via = [{ severity: "moderate" }];
  assert.throws(() => evaluateAudit(anonymous, lock, before));
  const standalone = {
    auditReportVersion: 2,
    vulnerabilities: { minimatch: {
      name: "minimatch", severity: "moderate", nodes: ["node_modules/minimatch"],
      via: [{ ...advisory, name: "minimatch", severity: "critical", url: "https://github.com/advisories/GHSA-critical" }],
    } },
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 1, high: 0, critical: 0, total: 1 } },
  };
  assert.throws(() => evaluateAudit(standalone, lock, after));
});
test("the advisory only counts on picomatch's own entry", () => {
  const value = report();
  value.vulnerabilities = { "@sentry/nextjs": { ...value.vulnerabilities["@sentry/nextjs"], via: [advisory] } };
  value.metadata.vulnerabilities.high = value.metadata.vulnerabilities.total = 1;
  assert.deepEqual(evaluateAudit(value, lock, before).failures, ["@sentry/nextjs"]);
});
test("an audit link must follow a real lockfile edge", () => {
  const value = report();
  value.vulnerabilities["@sentry/nextjs"].via = ["picomatch"];
  assert(evaluateAudit(value, lock, before).failures.includes("@sentry/nextjs"));
  const changed = structuredClone(lock);
  delete changed.packages["node_modules/@sentry/nextjs"].dependencies["@rollup/plugin-commonjs"];
  assert(evaluateAudit(report(), changed, before).failures.includes("@sentry/nextjs"));
});
test("malformed reports, metadata mismatches and operational errors fail closed", () => {
  for (const mutate of [
    (value) => { delete value.metadata; },
    (value) => { delete value.vulnerabilities.picomatch; },
    (value) => { value.metadata.vulnerabilities.high = 0; },
    (value) => { value.metadata.vulnerabilities.total = 0; },
    (value) => { value.error = { code: "ENETWORK" }; },
    (value) => { value.auditReportVersion = 1; },
    (value) => { value.vulnerabilities.picomatch.nodes = []; },
    (value) => { value.vulnerabilities.picomatch.via = []; },
  ]) {
    const value = report();
    mutate(value);
    assert.throws(() => evaluateAudit(value, lock, before));
  }
  assert.throws(() => evaluateAudit(report(), lock, new Date("invalid")));
});
