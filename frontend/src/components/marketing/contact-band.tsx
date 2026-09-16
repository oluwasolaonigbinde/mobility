import { CONTACT, CONTACT_BAND } from "@/lib/marketing/site";
import { Icon } from "./icon";
import { Reveal } from "./reveal";

/**
 * The closing call. Both conversion paths appear once more as prepared emails,
 * with the plain address underneath for anyone whose mail client will not open
 * a `mailto:` link.
 */
export function ContactBand() {
  return (
    <section id="contact" className="terrax-grain terrax-on-dark bg-terrax-deep text-terrax-card">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        {/* The measure belongs on the heading, not on a wrapper: `ch` resolves
            against the element's own font-size, so on a 16px wrapper 24ch is
            ~190px and the headline breaks one word per line. Every other
            section constrains its own h2, and this now matches them. */}
        <Reveal>
          <h2 className="font-terrax-display max-w-[24ch] text-[clamp(2.2rem,5.4vw,4rem)] leading-[0.95] font-extrabold tracking-tight">
            {CONTACT_BAND.title}
          </h2>
        </Reveal>

        <Reveal delay={90}>
          <p className="text-terrax-mint mt-6 max-w-[50ch] text-base leading-relaxed">
            {CONTACT_BAND.lead}
          </p>

          <div className="mt-9 flex flex-wrap gap-4">
            <a
              href={CONTACT_BAND.primary.href}
              className="font-terrax-display bg-terrax-gold text-terrax-ink hover:bg-terrax-card inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-sm font-extrabold transition-colors"
            >
              {CONTACT_BAND.primary.label}
              <Icon name="arrowRight" className="size-4" />
            </a>
            <a
              href={CONTACT_BAND.secondary.href}
              className="font-terrax-display border-terrax-card/30 text-terrax-card hover:border-terrax-gold hover:text-terrax-gold inline-flex items-center gap-2 rounded-full border px-7 py-3.5 text-sm font-extrabold transition-colors"
            >
              {CONTACT_BAND.secondary.label}
            </a>
          </div>

          <p className="text-terrax-mint mt-8 text-sm">
            {CONTACT_BAND.emailPrefix}{" "}
            <a
              className="text-terrax-gold underline underline-offset-4"
              href={`mailto:${CONTACT.email}`}
            >
              {CONTACT.email}
            </a>
          </p>
        </Reveal>
      </div>
    </section>
  );
}
