import { copyFileSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

// MapLibre's worker imports its sibling. Next's asset emitter does not emit that
// dependency, so serve both files from this exact installed package together.
const require = createRequire(import.meta.url);
const packagePath = require.resolve("maplibre-gl/package.json");
const { version } = JSON.parse(readFileSync(packagePath, "utf8"));
if (!/^\d+\.\d+\.\d+(?:[-+][\w.-]+)?$/.test(version)) {
  throw new Error("Invalid installed MapLibre version");
}
const files = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];
const source = join(dirname(packagePath), "dist");
// Check every source before creating output; a missing dependency fails builds.
for (const file of files) {
  if (!statSync(join(source, file)).isFile()) throw new Error(`Missing MapLibre ${file}`);
}
const output = new URL(`../public/maplibre/${version}/`, import.meta.url);
mkdirSync(output, { recursive: true });
for (const file of files) copyFileSync(join(source, file), new URL(file, output));
