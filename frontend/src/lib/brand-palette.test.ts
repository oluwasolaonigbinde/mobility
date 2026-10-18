import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { expect, it } from "vitest";
const css = readFileSync(path.resolve(__dirname, "../app/globals.css"), "utf8");
const colour = (name: string) => css.match(new RegExp(`--color-${name}: (#[a-f0-9]{6});`))![1]!;
function luminance(hex: string) {
  const rgb = hex
    .slice(1)
    .match(/../g)!
    .map((value) => parseInt(value, 16) / 255)
    .map((value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  return rgb[0]! * 0.2126 + rgb[1]! * 0.7152 + rgb[2]! * 0.0722;
}
function contrast(a: string, b: string) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0]! + 0.05) / (values[1]! + 0.05);
}
it("keeps ordinary text and action colours readable on the single white palette", () => {
  expect(colour("bg")).toBe("#ffffff");
  expect(colour("ink")).toBe("#0a1c09");
  for (const name of ["ink", "muted", "faint", "amber", "cyan", "green", "coral"])
    expect(contrast(colour(name), colour("panel")), name).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colour("accent-ink"), colour("amber"))).toBeGreaterThanOrEqual(4.5);
});
it("has no selectable theme registry, picker or persisted choice bootstrap", () => {
  expect(css).not.toMatch(/data-theme|ivory-ledger|broadside|dispatch|ledger|wrap/);
  expect(existsSync(path.resolve(__dirname, "themes.ts"))).toBe(false);
  expect(existsSync(path.resolve(__dirname, "../components/ui/theme-switcher.tsx"))).toBe(false);
  expect(readFileSync(path.resolve(__dirname, "../app/layout.tsx"), "utf8")).not.toMatch(
    /ThemeSwitcher|localStorage|THEME_BOOT_SCRIPT/,
  );
});
