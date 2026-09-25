import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_THEME,
  THEMES,
  THEME_BOOT_SCRIPT,
  THEME_STORAGE_KEY,
  applyTheme,
  currentTheme,
} from "./themes";

const globalsCss = readFileSync(path.resolve(__dirname, "../app/globals.css"), "utf8");
const marketingCss = readFileSync(path.resolve(__dirname, "../app/marketing.css"), "utf8");

// jsdom here runs without Node's --localstorage-file, so window.localStorage
// is absent; applyTheme's persistence branch needs a real store to assert on.
const store = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  },
});

describe("theme registry", () => {
  it("registers unique slugs and the default", () => {
    const slugs = THEMES.map((t) => t.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    expect(slugs).toContain(DEFAULT_THEME);
  });

  it("contains only the four retained directions in their new order", () => {
    expect(THEMES.map((theme) => [theme.slug, theme.name])).toEqual([
      ["ivory-ledger", "Direction 1"],
      ["broadside", "Direction 2"],
      ["dispatch", "Direction 3"],
      ["ledger", "Direction 4"],
    ]);
  });

  it("defines token blocks only for registered directions", () => {
    const blocks = [...globalsCss.matchAll(/  html\[data-theme="([^"]+)"\] \{/g)].map((match) => match[1]);
    expect(blocks).toEqual(THEMES.map((theme) => theme.slug));
  });

  it.each([
    ["ivory-ledger", "Direction 1", "light"],
    ["broadside", "Direction 2", "light"],
    ["dispatch", "Direction 3", "light"],
    ["ledger", "Direction 4", "light"],
  ])("registers %s as %s", (slug, name, colorScheme) => {
    const entry = THEMES.find((t) => t.slug === slug);
    expect(entry).toBeDefined();
    expect(entry?.name).toBe(name);
    expect(entry?.colorScheme).toBe(colorScheme);
    expect(entry?.swatches).toHaveLength(4);
  });

  // The registry and the stylesheet are two halves of one contract: a theme
  // with no token block silently renders as the default.
  it.each(THEMES.map((t) => t.slug))(
    "globals.css defines a token block for %s",
    (slug) => {
      expect(globalsCss).toContain(`html[data-theme="${slug}"] {`);
    },
  );

  // A direction is more than a palette: each one must also ship scoped rules
  // (its design language) in the unlayered section, not just a token block.
  it.each(["ivory-ledger", "broadside", "dispatch", "ledger"])(
    "%s ships a design language beyond its token block",
    (slug) => {
      const scoped = globalsCss.match(new RegExp(`html\\[data-theme="${slug}"\\]`, "g"));
      expect(scoped?.length ?? 0).toBeGreaterThan(1);
    },
  );

  it.each(THEMES.map((t) => [t.slug, t.swatches] as const))(
    "%s declares four hex swatches",
    (_slug, swatches) => {
      for (const swatch of swatches) expect(swatch).toMatch(/^#[0-9a-f]{6}$/i);
    },
  );

  it("keeps public landing tokens outside the product theme namespace", () => {
    expect(globalsCss).toContain("--color-terrax-paper");
    expect(marketingCss).toContain(".terrax-site");
    expect(marketingCss).not.toMatch(
      /--color-(?:bg|panel|raised|edge|ink|amber|cyan|green|coral):/,
    );
    expect(marketingCss).not.toContain("--font-display:");
    expect(globalsCss).toContain('html[data-theme="dispatch"] .rounded-panel.border-edge');
    expect(globalsCss).toContain('html[data-theme="ledger"] .rounded-panel.border-edge');
  });
});

describe("applyTheme / currentTheme", () => {
  beforeEach(() => {
    delete document.documentElement.dataset.theme;
    window.localStorage.clear();
  });

  it("sets the attribute and persists a non-default theme", () => {
    applyTheme("broadside");
    expect(document.documentElement.dataset.theme).toBe("broadside");
    expect(currentTheme()).toBe("broadside");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("broadside");
  });

  it("applies the default theme attribute", () => {
    applyTheme("broadside");
    applyTheme(DEFAULT_THEME);
    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
    expect(currentTheme()).toBe(DEFAULT_THEME);
  });

  it("rejects obsolete or unknown choices", () => {
    applyTheme("retired-choice");
    expect(currentTheme()).toBe(DEFAULT_THEME);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe(DEFAULT_THEME);
  });
});

describe("boot script", () => {
  it("restores a persisted theme before paint", () => {
    delete document.documentElement.dataset.theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, "broadside");
    new Function(THEME_BOOT_SCRIPT)();
    expect(document.documentElement.dataset.theme).toBe("broadside");
  });

  it("falls back before paint when storage holds a rejected direction", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "retired-choice");
    new Function(THEME_BOOT_SCRIPT)();
    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
  });
});
