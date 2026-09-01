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

  it.each([
    ["terra-grain", "Direction 7", "dark"],
    ["coverage", "Direction 8", "light"],
    ["broadside", "Direction 9", "light"],
  ])("registers %s as %s", (slug, name, colorScheme) => {
    const entry = THEMES.find((t) => t.slug === slug);
    expect(entry).toBeDefined();
    expect(entry?.name).toBe(name);
    expect(entry?.colorScheme).toBe(colorScheme);
    expect(entry?.swatches).toHaveLength(4);
  });

  // The registry and the stylesheet are two halves of one contract: a theme
  // with no token block silently renders as the default.
  it.each(THEMES.filter((t) => t.slug !== DEFAULT_THEME).map((t) => t.slug))(
    "globals.css defines a token block for %s",
    (slug) => {
      expect(globalsCss).toContain(`html[data-theme="${slug}"] {`);
    },
  );

  // A direction is more than a palette: each one must also ship scoped rules
  // (its design language) in the unlayered section, not just a token block.
  it.each(["terra-grain", "coverage", "broadside"])(
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
});

describe("applyTheme / currentTheme", () => {
  beforeEach(() => {
    delete document.documentElement.dataset.theme;
    window.localStorage.clear();
  });

  it("sets the attribute and persists a non-default theme", () => {
    applyTheme("terra-grain");
    expect(document.documentElement.dataset.theme).toBe("terra-grain");
    expect(currentTheme()).toBe("terra-grain");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("terra-grain");
  });

  it("clears the attribute for the default theme", () => {
    applyTheme("terra-grain");
    applyTheme(DEFAULT_THEME);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(currentTheme()).toBe(DEFAULT_THEME);
  });
});

describe("boot script", () => {
  it("restores a persisted theme before paint", () => {
    delete document.documentElement.dataset.theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, "terra-grain");
    new Function(THEME_BOOT_SCRIPT)();
    expect(document.documentElement.dataset.theme).toBe("terra-grain");
  });
});
