/**
 * Replaceable image slots.
 *
 * The repository holds no Terrax Media vehicle photography, so both slots ship a
 * neutral, unbranded illustration rather than a real or invented campaign. Each
 * one draws its advertising surface EMPTY, so nothing here can be mistaken for
 * an actual Terrax campaign or for another company's identity.
 *
 * To swap in a real photograph:
 *   1. Put the file in `public/marketing/terrax/` (e.g. `hero-vehicle.jpg`), sized at or
 *      near the `width`/`height` below and compressed for the web.
 *   2. Change `src`, `width` and `height` in the slot here.
 *   3. Rewrite `alt` to describe the actual photograph, dropping the word
 *      "Illustration" once it is a real photograph.
 *   4. `npm run build` — nothing else references these files.
 *
 * A slot still awaiting real artwork is identifiable without a flag: its file is
 * named `*-placeholder.svg` and its `alt` begins "Illustration of".
 */
type MediaSlot = {
  readonly src: string;
  readonly width: number;
  readonly height: number;
  readonly alt: string;
};

export const MEDIA = {
  /** Hero, 4:5 portrait, inside the cream card frame. */
  hero: {
    src: "/marketing/terrax/hero-vehicle-placeholder.svg",
    width: 1024,
    height: 1280,
    alt: "Illustration of a city street at golden hour, with an unbranded vehicle whose side advertising panel is empty.",
  },
  /** Cardvert section, 16:9 landscape, on the ink ground. */
  fleet: {
    src: "/marketing/terrax/fleet-corridor-placeholder.svg",
    width: 1280,
    height: 720,
    alt: "Illustration of a simplified street grid where three unbranded vehicles travel a shared corridor, their routes drawn as dashed lines.",
  },
} as const satisfies Record<string, MediaSlot>;
