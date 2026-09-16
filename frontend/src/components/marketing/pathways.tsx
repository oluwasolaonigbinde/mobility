import { PATHWAYS } from "@/lib/marketing/site";
import { Icon } from "./icon";
import { Reveal } from "./reveal";

/**
 * The two conversion paths, given equal weight as a split panel: brands on the
 * light ground, drivers on the terrax-deep terrax-green one. Each panel ends in its own
 * prepared email, so neither audience has to work out which CTA is theirs.
 *
 * The dark panel carries `terrax-on-dark`, which switches the focus ring to Golden
 * Accent so it stays visible against the terrax-green.
 */
export function Pathways() {
  const [brands, drivers] = PATHWAYS;

  return (
    <section aria-label="For brands and for drivers" className="bg-terrax-card">
      <div className="border-terrax-ink/12 bg-terrax-ink/12 mx-auto grid max-w-7xl gap-px border-x border-b md:grid-cols-2">
        <Reveal as="article" id={brands.id} className="bg-terrax-card px-6 py-14 md:px-12 md:py-20">
          <p className="text-terrax-crimson-ink flex items-center gap-2 text-xs font-semibold tracking-[0.3em] uppercase">
            <Icon name={brands.icon} className="size-4" /> {brands.eyebrow}
          </p>
          <h2 className="font-terrax-display text-terrax-ink mt-4 max-w-[16ch] text-[clamp(1.8rem,3.6vw,2.8rem)] leading-[0.95] font-extrabold">
            {brands.title}
          </h2>
          <ul className="text-terrax-ink-soft mt-8 space-y-4 text-sm">
            {brands.points.map((point) => (
              <li key={point} className="flex gap-3">
                <span
                  className="bg-terrax-gold-ink mt-2 size-1.5 shrink-0 rounded-full"
                  aria-hidden="true"
                />
                {point}
              </li>
            ))}
          </ul>
          <a
            href={brands.cta.href}
            className="font-terrax-display bg-terrax-ink text-terrax-card hover:bg-terrax-deep mt-9 inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-extrabold transition-colors"
          >
            {brands.cta.label}
            <Icon name="arrowRight" className="size-4" />
          </a>
        </Reveal>

        <Reveal
          as="article"
          id={drivers.id}
          delay={90}
          className="terrax-on-dark bg-terrax-deep text-terrax-card px-6 py-14 md:px-12 md:py-20"
        >
          <p className="text-terrax-gold flex items-center gap-2 text-xs font-semibold tracking-[0.3em] uppercase">
            <Icon name={drivers.icon} className="size-4" /> {drivers.eyebrow}
          </p>
          <h2 className="font-terrax-display mt-4 max-w-[16ch] text-[clamp(1.8rem,3.6vw,2.8rem)] leading-[0.95] font-extrabold">
            {drivers.title}
          </h2>
          <ul className="text-terrax-mint mt-8 space-y-4 text-sm">
            {drivers.points.map((point) => (
              <li key={point} className="flex gap-3">
                <span
                  className="bg-terrax-gold mt-2 size-1.5 shrink-0 rounded-full"
                  aria-hidden="true"
                />
                {point}
              </li>
            ))}
          </ul>
          <a
            href={drivers.cta.href}
            className="font-terrax-display bg-terrax-gold text-terrax-ink hover:bg-terrax-card mt-9 inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-extrabold transition-colors"
          >
            {drivers.cta.label}
            <Icon name="arrowRight" className="size-4" />
          </a>
        </Reveal>
      </div>
    </section>
  );
}
