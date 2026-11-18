import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const advisory = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf";
const expiry = "2026-12-18T00:00:00Z";
const expiresAfter = new Date(expiry);
const reason = "No patched picomatch release; exposure is confined to lint, test and build tooling.";
const devParents = new Map([
  ["eslint-config-next", [""]],
  ["@next/eslint-plugin-next", ["eslint-config-next"]],
  ["fast-glob", ["@next/eslint-plugin-next"]],
  ["micromatch", ["fast-glob"]],
  ["eslint-import-resolver-typescript", ["eslint-config-next"]],
  ["typescript-eslint", ["eslint-config-next"]],
  ["@typescript-eslint/eslint-plugin", ["typescript-eslint"]],
  ["@typescript-eslint/parser", ["typescript-eslint", "@typescript-eslint/eslint-plugin"]],
  ["@typescript-eslint/type-utils", ["@typescript-eslint/eslint-plugin"]],
  ["@typescript-eslint/utils", ["typescript-eslint", "@typescript-eslint/eslint-plugin", "@typescript-eslint/type-utils"]],
  ["@typescript-eslint/typescript-estree", ["typescript-eslint", "@typescript-eslint/parser", "@typescript-eslint/type-utils", "@typescript-eslint/utils"]],
  ["@vitejs/plugin-react", [""]],
  ["@vitest/coverage-v8", ["", "vitest"]],
  ["@vitest/mocker", ["vitest"]],
  ["vite", ["@vitejs/plugin-react", "@vitest/mocker", "vitest"]],
  ["vitest", ["", "@vitest/coverage-v8"]],
  ["tinyglobby", ["@typescript-eslint/typescript-estree", "eslint-import-resolver-typescript", "vite", "vitest"]],
  ["fdir", ["tinyglobby"]],
  ["picomatch", ["micromatch", "tinyglobby", "fdir", "vite", "vitest"]],
]);
const buildParents = new Map([
  ["@sentry/nextjs", [""]],
  ["@rollup/plugin-commonjs", ["@sentry/nextjs"]],
  ["@rollup/pluginutils", ["@rollup/plugin-commonjs"]],
  ["fdir", ["@rollup/plugin-commonjs"]],
  ["picomatch", ["@rollup/plugin-commonjs", "@rollup/pluginutils", "fdir"]],
]);
const severities = ["info", "low", "moderate", "high", "critical"];
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const packagePath = /^(?:node_modules\/(?:@[^/]+\/)?[^/]+\/)*node_modules\/((?:@[^/]+\/)?[^/]+)$/;
const nameAt = (path) => packagePath.exec(path)?.[1];

function installed(packages, from, name) {
  let directory = from;
  for (;;) {
    const candidate = posix.join(directory, "node_modules", name);
    if (posix.basename(directory) !== "node_modules" && Object.hasOwn(packages, candidate)) return candidate;
    if (!directory) return null;
    directory = posix.dirname(directory);
    if (directory === ".") directory = "";
  }
}

function toolingNodes(lock) {
  if (!object(lock?.packages) || !object(lock.packages[""])) return () => false;
  const packages = lock.packages;
  const root = packages[""];
  const fields = ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"];
  const incoming = new Map();
  for (const [path, entry] of Object.entries(packages)) {
    if (!object(entry)) return () => false;
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

  return (name, nodes) => {
    if (!nodes.every((path) => typeof path === "string" && nameAt(path) === name)) return false;

    const pending = [...nodes];
    const visited = new Set();
    const children = new Map();
    for (const path of pending) {
      if (visited.has(path)) continue;
      visited.add(path);
      const entry = Object.hasOwn(packages, path) ? packages[path] : undefined;
      const name = nameAt(path);
      if (!entry || (entry.name !== undefined && entry.name !== name)) return false;
      const dev = entry.dev === true;
      const parents = (dev ? devParents : buildParents).get(name);
      for (const parent of incoming.get(path) ?? []) {
        if (!parents?.includes(parent === "" ? "" : nameAt(parent))) return false;
        if (parent === "") {
          const field = dev ? "devDependencies" : "dependencies";
          if (path !== `node_modules/${name}` || !Object.hasOwn(root[field] ?? {}, name)
              || fields.some((other) => other !== field && Object.hasOwn(root[other] ?? {}, name))) return false;
        } else {
          if ((packages[parent].dev === true) !== dev) return false;
          pending.push(parent);
        }
        const edges = children.get(parent) ?? [];
        edges.push(path);
        children.set(parent, edges);
      }
    }

    // A peer cycle is valid only if each ancestor is reachable from a permitted root.
    const reachable = new Set([""]);
    for (const parent of reachable) {
      for (const child of children.get(parent) ?? []) reachable.add(child);
    }
    return reachable.size === visited.size + 1;
  };
}

export function evaluateAudit(report, lock, now = new Date()) {
  if (!object(report) || report.auditReportVersion !== 2 || report.error
      || !object(report.vulnerabilities) || !object(report.metadata?.vulnerabilities)
      || !(now instanceof Date) || !Number.isFinite(now.getTime())) throw new Error("Invalid npm audit report or clock");
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
  // An advisory without identity, or one rated above the entry that lists it, is a malformed
  // report. (npm can rate an entry below entries it references, so only own advisories count.)
  const rank = (severity) => severities.indexOf(severity);
  for (const item of Object.values(entries)) {
    for (const source of item.via) {
      if (typeof source === "string") {
        if (!Object.hasOwn(entries, source)) throw new Error("Unknown npm audit vulnerability reference");
        continue;
      }
      if (!object(source) || typeof source.name !== "string" || !source.name
          || typeof source.url !== "string" || !source.url
          || !severities.includes(source.severity) || rank(source.severity) > rank(item.severity)) {
        throw new Error("Inconsistent npm audit vulnerability entry");
      }
    }
  }
  let allowedNodes;
  const belowHigh = (severity) => severities.indexOf(severity) < severities.indexOf("high");
  // Each audit `via` link must be a real lockfile dependency edge between the two entries'
  // installed nodes, so a report cannot attach a cause from another dependency tree.
  const packages = object(lock?.packages) ? lock.packages : {};
  const realNodes = (name, nodes) => nodes.every((path) => typeof path === "string"
    && Object.hasOwn(packages, path) && nameAt(path) === name
    && object(packages[path]) && (packages[path].name === undefined || packages[path].name === name));
  function linked(parent, child) {
    return entries[parent].nodes.some((from) => {
      const entry = packages[from];
      if (!object(entry)) return false;
      const dependencies = { ...entry.dependencies, ...entry.optionalDependencies, ...entry.peerDependencies };
      return Object.hasOwn(dependencies, child)
        && entries[child].nodes.includes(installed(packages, from, child));
    });
  }
  // Returns whether an entry carries the waived advisory, or null when it disqualifies.
  // The only high-severity cause allowed anywhere in the closure is the advisory on
  // picomatch's own entry. An entry that carries it must be rated high and sit on the
  // allowlisted tooling paths; lower-severity branches only need real installed nodes,
  // since they never fail this gate. A revisited entry (npm reports peer cycles such as
  // vitest <-> @vitest/coverage-v8) adds no cause; its first visit is checked in full.
  const waivedLeaf = (source) => object(source) && source.name === "picomatch"
    && source.url === advisory && source.severity === "high";
  // Every entry whose closure reaches the waived advisory, cycles included.
  const reaches = new Set(entries.picomatch?.via.some(waivedLeaf) ? ["picomatch"] : []);
  for (let grew = true; grew;) {
    grew = false;
    for (const [name, item] of Object.entries(entries)) {
      if (!reaches.has(name) && item.via.some((source) => typeof source === "string" && reaches.has(source))) {
        reaches.add(name);
        grew = true;
      }
    }
  }
  function carriesWaivedCause(name, visiting = new Set()) {
    if (!Object.hasOwn(entries, name)) return null;
    if (visiting.has(name)) return false;
    const item = entries[name];
    if (item.severity === "critical" || !realNodes(name, item.nodes)) return null;
    const next = new Set([...visiting, name]);
    let carries = false;
    for (const source of item.via) {
      if (typeof source === "string") {
        if (!Object.hasOwn(entries, source) || !linked(name, source)) return null;
        const child = carriesWaivedCause(source, next);
        if (child === null) return null;
        carries ||= child;
      } else {
        if (!object(source) || !severities.includes(source.severity)) return null;
        if (belowHigh(source.severity)) continue;
        if (name !== "picomatch" || !waivedLeaf(source)) return null;
        carries = true;
      }
    }
    if (reaches.has(name) && (item.severity !== "high"
        || !(allowedNodes ??= toolingNodes(lock))(name, item.nodes))) return null;
    return carries;
  }
  const waived = [];
  const failures = [];
  for (const [name, item] of Object.entries(entries)) {
    if (!["high", "critical"].includes(item.severity)) continue;
    if (now < expiresAfter && carriesWaivedCause(name) === true) waived.push(name);
    else failures.push(name);
  }
  return { waived, failures };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "../frontend");
    const result = spawnSync("npm", ["audit", "--json"], {
      cwd: frontend, shell: process.platform === "win32", encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
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
    if (waived.length) console.log(`REQ-332: ${advisory}; expires ${expiry}; ${reason} (${waived.join(", ")})`);
    if (failures.length) throw new Error(`High/critical advisories remain: ${failures.join(", ")}`);
    console.log("Frontend dependency audit passed");
  } catch (error) {
    console.error(`Frontend dependency audit failed: ${error.message}`);
    process.exitCode = 1;
  }
}
