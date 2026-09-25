/**
 * Theme registry — one entry per selectable visual direction.
 *
 * Mechanics: every theme is a set of CSS custom-property overrides scoped to
 * `html[data-theme="<slug>"]` in globals.css. Components never branch on the
 * theme; they wear token classes and the variables re-map underneath them.
 * The default is Ivory Ledger; all four retained directions use an attribute.
 */
export interface ThemeMeta {
  slug: string;
  name: string;
  tagline: string;
  colorScheme: "light" | "dark";
  /** Representative swatches for the switcher UI: [bg, panel, accent, secondary] */
  swatches: [string, string, string, string];
}

export const DEFAULT_THEME = "ivory-ledger";
export const THEME_STORAGE_KEY = "cardvert-theme";

export const THEMES: ThemeMeta[] = [
  {
    slug: "ivory-ledger",
    name: "Direction 1",
    tagline: "",
    colorScheme: "light",
    swatches: ["#efe9d8", "#fbf8f0", "#a63d17", "#1e5f5a"],
  },
  {
    slug: "broadside",
    name: "Direction 2",
    tagline: "",
    colorScheme: "light",
    swatches: ["#efeee1", "#e4e2cf", "#9c352f", "#0b1f07"],
  },
  {
    slug: "dispatch",
    name: "Direction 3",
    tagline: "",
    colorScheme: "light",
    swatches: ["#f5f3ee", "#ffffff", "#8a5a10", "#0e2f14"],
  },
  {
    slug: "ledger",
    name: "Direction 4",
    tagline: "",
    colorScheme: "light",
    swatches: ["#eeeae0", "#faf8f3", "#0f5c55", "#256f1a"],
  },
];

export function applyTheme(slug: string) {
  const root = document.documentElement;
  const selected = THEMES.some((theme) => theme.slug === slug) ? slug : DEFAULT_THEME;
  root.dataset.theme = selected;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, selected);
  } catch {
    /* storage unavailable (private mode) — theme still applies for the session */
  }
}

export function currentTheme(): string {
  const slug = document.documentElement.dataset.theme;
  return THEMES.some((theme) => theme.slug === slug) ? slug! : DEFAULT_THEME;
}

/**
 * Inline boot script for the root layout: applies the persisted theme before
 * first paint so a non-default theme never flashes dark. Must stay ES5-safe
 * and self-contained (it is serialized into the HTML).
 */
export const THEME_BOOT_SCRIPT = `(function(){var t=${JSON.stringify(DEFAULT_THEME)};try{var s=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});if(${JSON.stringify(THEMES.map((theme) => theme.slug))}.indexOf(s)!==-1)t=s;}catch(e){}document.documentElement.dataset.theme=t;})();`;
