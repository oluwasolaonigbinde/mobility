import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

import provenance from "./google/provenance.json";

/**
 * The production build must never reach Google Fonts. Every retained face is
 * vendored under `src/fonts/google` and declared through `next/font/local` in
 * `src/fonts/families`; these guards fail if that regresses.
 */

const SRC = join(__dirname, "..");
const ASSETS = join(__dirname, "google");
const FAMILIES = join(__dirname, "families");

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(full, out);
    else if (/\.(ts|tsx|css)$/.test(entry.name)) out.push(full);
  }
  return out;
}

const sources = sourceFiles(SRC).filter((f) => f !== __filename);

describe("no build-time or runtime Google Fonts dependency", () => {
  it("imports no font from next/font/google", () => {
    const offenders = sources.filter((f) => /from\s+["']next\/font\/google["']/.test(readFileSync(f, "utf8")));
    expect(offenders.map((f) => relative(SRC, f))).toEqual([]);
  });

  it("references no Google font host from application code", () => {
    // Comments are stripped first: documenting an upstream URL is not a defect,
    // requesting one at build time or in the browser is.
    const offenders = sources.filter((f) =>
      /fonts\.(googleapis|gstatic)\.com/.test(
        readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*/g, ""),
      ),
    );
    expect(offenders.map((f) => relative(SRC, f))).toEqual([]);
  });
});

describe("retained font variables stay wired", () => {
  const rootLayout = readFileSync(join(SRC, "app/layout.tsx"), "utf8");
  const productFonts = readFileSync(join(SRC, "lib/fonts.ts"), "utf8");
  const landingLayout = readFileSync(join(SRC, "app/landing/layout.tsx"), "utf8");
  const landingFonts = readFileSync(join(SRC, "app/landing/fonts.ts"), "utf8");

  it.each([
    "--font-clash",
    "--font-satoshi",
    "--font-plex-mono",
    "--font-inter",
    "--font-fraunces",
    "--font-bricolage",
    "--font-archivo",
    "--font-poppins",
    "--font-big-shoulders",
  ])("the product type system still declares %s", (variable) => {
    expect(productFonts).toContain(variable);
  });

  it("the root layout applies both the local classes and the vendored variables", () => {
    expect(rootLayout).toMatch(/clashDisplay\.variable/);
    expect(rootLayout).toMatch(/satoshi\.variable/);
    expect(rootLayout).toMatch(/style=\{productFontVariables\}/);
    expect(rootLayout).toMatch(/h-full antialiased/);
  });

  it.each(["--tx-font", "--tx-mono"])("the landing type system still declares %s", (variable) => {
    expect(landingFonts).toContain(variable);
  });

  it("the landing layout applies its own variables on the tx-page wrapper", () => {
    expect(landingLayout).toMatch(/className="tx-page"/);
    expect(landingLayout).toMatch(/style=\{landingFontVariables\}/);
  });
});

describe("vendored asset provenance", () => {
  const declared = Object.values(provenance.families).flatMap((family) => family.files);
  const onDisk = readdirSync(ASSETS).filter((name) => name.endsWith(".woff2"));

  it("declares every vendored binary exactly once", () => {
    expect([...declared.map((f) => f.file)].sort()).toEqual([...onDisk].sort());
  });

  it.each(Object.entries(provenance.families))("%s records an OFL licence", (_family, family) => {
    const licence = join(ASSETS, family.licenceFile);
    expect(family.licence).toBe("SIL Open Font License 1.1");
    expect(statSync(licence).size).toBeGreaterThan(0);
    expect(readFileSync(licence, "utf8")).toContain("SIL OPEN FONT LICENSE Version 1.1");
  });

  // These hashes guard against later drift in the vendored binaries. The proof
  // that they are the approved build's bytes is external: they were taken from
  // `coverage/correction-sep8/cached-fonts` and compared face-by-face against
  // the Google baseline in `coverage/correction-fonts/face-tuple-comparison.log`.
  it.each(declared.map((f) => [f.file, f] as const))("%s matches its recorded hash and source", (_name, file) => {
    const digest = createHash("sha256").update(readFileSync(join(ASSETS, file.file))).digest("hex");
    expect(digest).toBe(file.sha256);
    expect(file.source).toMatch(/^https:\/\/fonts\.gstatic\.com\//);
    expect(file.unicodeRange).toMatch(/^U\+/);
  });
});

describe("family declarations keep the approved fallback and preload shape", () => {
  const modules = readdirSync(FAMILIES).filter((name) => name.endsWith(".ts"));

  /**
   * next/font/google emits a metric-adjusted fallback face for every family in
   * its precalculated metrics table. Big Shoulders is absent from that table, so
   * the approved output has no fallback for it; the other six each have exactly
   * one. See coverage/correction-fonts/face-tuple-comparison.log.
   */
  const EXPECTED_FALLBACKS: Record<string, number> = {
    "archivo.ts": 1,
    "big-shoulders.ts": 0,
    "bricolage-grotesque.ts": 1,
    "fraunces.ts": 1,
    "ibm-plex-mono.ts": 1,
    "inter.ts": 1,
    "poppins.ts": 1,
  };

  function calls(source: string) {
    return [...source.matchAll(/const (\w+) = localFont\(\{([\s\S]*?)\n\}\);/g)].map((match) => ({
      name: match[1] ?? "",
      body: match[2] ?? "",
    }));
  }

  it("declares one module per vendored family", () => {
    expect(modules.sort()).toEqual(Object.keys(EXPECTED_FALLBACKS).sort());
  });

  it("gives every face a globally unique const name", () => {
    // next/font derives the @font-face `font-family` from the JS const name and
    // the emitted stylesheet is global, so a duplicated name silently merges two
    // typefaces into one family. Scan every localFont declaration under src,
    // not just the family modules, because clashDisplay and satoshi share the
    // same namespace.
    const names = sources
      .filter((file) => readFileSync(file, "utf8").includes("localFont({"))
      .flatMap((file) => calls(readFileSync(file, "utf8")).map((call) => call.name));
    expect(names.length).toBeGreaterThan(0);
    expect(names).toHaveLength(new Set(names).size);
  });

  it.each(modules)("%s preloads its latin face and nothing else", (name) => {
    const preloaded = calls(readFileSync(join(FAMILIES, name), "utf8")).filter(
      (call) => !call.body.includes("preload: false"),
    );
    expect(preloaded).toHaveLength(1);
    expect(preloaded[0]?.body).toMatch(/path: "\.\.\/google\/[^"]*-latin\.woff2"/);
  });

  it.each(modules)("%s keeps its approved metric fallback, on the terminal face", (name) => {
    const source = readFileSync(join(FAMILIES, name), "utf8");
    const adjusted = calls(source)
      .filter((call) => !/adjustFontFallback: false/.test(call.body))
      .map((call) => call.name);
    expect(adjusted).toHaveLength(EXPECTED_FALLBACKS[name] ?? 1);
    const chain = /export const \w+ = \[([^\]]+)\]/.exec(source)?.[1];
    expect(chain).toBeDefined();
    const names = (chain ?? "").split(",").map((part) => part.trim());
    expect(names.length).toBeGreaterThan(0);
    for (const face of adjusted) {
      // the fallback @font-face carries no unicode-range, so it must sit last
      expect(names.at(-1)).toBe(face);
    }
  });

  it.each(Object.entries(provenance.families))(
    "%s declarations match the recorded provenance",
    (_family, family) => {
      const sourceByFile = new Map(
        modules.flatMap((name) => {
          const source = readFileSync(join(FAMILIES, name), "utf8");
          return calls(source).flatMap((call) =>
            [...call.body.matchAll(/path: "\.\.\/google\/([^"]+)"/g)].map(
              (match) => [match[1] ?? "", call.body] as const,
            ),
          );
        }),
      );
      for (const file of family.files) {
        const body = sourceByFile.get(file.file);
        expect(body, `${file.file} is not declared by any family module`).toBeDefined();
        expect(body).toContain(file.unicodeRange);
      }
    },
  );
});
