import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const advisory = "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm";
const expiresAfter = new Date("2026-11-05T00:00:00Z");
const reason = "No patched braces release; exposure is confined to the dev-only eslint-config-next lint chain.";
const parents = new Map([
  ["braces", "micromatch"],
  ["micromatch", "fast-glob"],
  ["fast-glob", "@next/eslint-plugin-next"],
  ["@next/eslint-plugin-next", "eslint-config-next"],
  ["eslint-config-next", ""],
]);
const severities = ["info", "low", "moderate", "high", "critical"];
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const nameAt = (path) => path.split("node_modules/").at(-1);

function installed(packages, from, name) {
  let directory = from;
  for (;;) {
    const candidate = posix.join(directory, "node_modules", name);
    if (Object.hasOwn(packages, candidate)) return candidate;
    if (!directory) return null;
    directory = posix.dirname(directory);
    if (directory === ".") directory = "";
  }
}

function lintChainOnly(lock, nodes) {
  if (!object(lock.packages) || !object(lock.packages[""])) return false;
  const packages = lock.packages;
  const incoming = new Map();
  for (const [path, entry] of Object.entries(packages)) {
    const dependencies = {
      ...entry.dependencies, ...entry.optionalDependencies, ...entry.peerDependencies,
      ...(path === "" ? entry.devDependencies : {}),
    };
    for (const name of Object.keys(dependencies)) {
      const target = installed(packages, path, name);
      if (target === null) continue;
      const edges = incoming.get(target) ?? [];
      edges.push(path);
      incoming.set(target, edges);
    }
  }
  function allowed(path, visiting = new Set()) {
    const name = nameAt(path);
    if (!parents.has(name) || packages[path]?.dev !== true || visiting.has(path)) return false;
    const previous = parents.get(name);
    const edges = incoming.get(path) ?? [];
    if (edges.length === 0) return false;
    if (previous === "") {
      const root = packages[""];
      return edges.every((parent) => parent === "")
        && Object.hasOwn(root.devDependencies ?? {}, name)
        && !Object.hasOwn(root.dependencies ?? {}, name)
        && !Object.hasOwn(root.optionalDependencies ?? {}, name)
        && !Object.hasOwn(root.peerDependencies ?? {}, name);
    }
    const next = new Set([...visiting, path]);
    return edges.every((parent) => nameAt(parent) === previous && allowed(parent, next));
  }
  return nodes.every((path) => typeof path === "string" && allowed(path));
}

export function evaluateAudit(report, lock, now = new Date()) {
  if (!object(report) || report.auditReportVersion !== 2 || report.error
      || !object(report.vulnerabilities) || !object(report.metadata?.vulnerabilities)
      || !Number.isFinite(now.getTime())) throw new Error("Invalid npm audit report or clock");
  const entries = report.vulnerabilities;
  const counts = Object.fromEntries(severities.map((severity) => [severity, 0]));
  for (const [name, item] of Object.entries(entries)) {
    if (!object(item) || item.name !== name || !severities.includes(item.severity)
        || !Array.isArray(item.via) || item.via.length === 0
        || !Array.isArray(item.nodes) || item.nodes.length === 0) {
      throw new Error("Incomplete npm audit vulnerability entry");
    }
    counts[item.severity] += 1;
  }
  for (const severity of severities) {
    if (report.metadata.vulnerabilities[severity] !== counts[severity]) {
      throw new Error("npm audit counts do not match its vulnerability entries");
    }
  }
  if (report.metadata.vulnerabilities.total !== Object.keys(entries).length) {
    throw new Error("Invalid npm audit total");
  }
  function exclusivelyExcepted(name, visiting = new Set()) {
    const item = entries[name];
    if (!item || !parents.has(name) || visiting.has(name)
        || !lintChainOnly(lock, item.nodes)) return false;
    const next = new Set([...visiting, name]);
    return item.via.every((source) => typeof source === "string"
      ? exclusivelyExcepted(source, next)
      : object(source) && source.name === "braces" && source.url === advisory
        && severities.includes(source.severity));
  }
  const waived = [];
  const failures = [];
  for (const [name, item] of Object.entries(entries)) {
    if (!["high", "critical"].includes(item.severity)) continue;
    if (now < expiresAfter && exclusivelyExcepted(name)) waived.push(name);
    else failures.push(name);
  }
  return { waived, failures };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "../frontend");
    const result = spawnSync("npm", ["audit", "--json"], {
      cwd: frontend, encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
    });
    if (result.error || result.signal || ![0, 1].includes(result.status)) {
      throw new Error("npm audit could not complete");
    }
    const report = JSON.parse(result.stdout);
    const lock = JSON.parse(readFileSync(resolve(frontend, "package-lock.json"), "utf8"));
    const { waived, failures } = evaluateAudit(report, lock);
    if (result.status === 1 && report.metadata.vulnerabilities.total === 0) {
      throw new Error("npm audit failed without a vulnerability report");
    }
    if (waived.length) console.log(`REQ-107: ${advisory}; expires 2026-11-04 UTC; ${reason} (${waived.join(", ")})`);
    if (failures.length) throw new Error(`High/critical advisories remain: ${failures.join(", ")}`);
    console.log("Frontend dependency audit passed");
  } catch (error) {
    console.error(`Frontend dependency audit failed: ${error.message}`);
    process.exitCode = 1;
  }
}
