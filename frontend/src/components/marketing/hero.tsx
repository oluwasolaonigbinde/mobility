import Image from "next/image";
import { HERO, MAILTO, ROUTES } from "@/lib/marketing/site";
import { MEDIA } from "@/lib/marketing/media";
import { Icon } from "./icon";

/**
 * Opening statement: the tagline set as a three-tone display headline, the two
 * conversion paths side by side, and the campaign visual in a tilted terrax-card frame.
 *
 * Colour note — the headline's three tones are all brand values, chosen for the
 * ground they sit on: terrax-ink for the sentence, Crimson Flame for the italic word
 * (used here only, at the clamp floor of 2.6rem, where AA large applies), and
 * Battle Cat terrax-green for the closing word. Golden Accent is deliberately not used
 * as display text: at 1.3:1 on terrax-paper it would be unreadable.
 */
export function Hero() {
  return (
    <section
      id="top"
      className="mx-auto max-w-7xl overflow-hidden px-5 pt-12 pb-20 md:px-8 md:pt-20 md:pb-28"
    >
      <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
        <div>
          <span className="border-terrax-ink/15 bg-terrax-card/70 text-terrax-ink-soft inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-semibold tracking-wide uppercase">
            <span className="bg-terrax-crimson-ink size-1.5 rounded-full" aria-hidden="true" />
            {HERO.eyebrow}
          </span>

          <h1 className="font-terrax-display text-terrax-ink mt-7 text-[clamp(2.6rem,8vw,4.6rem)] leading-[0.94] font-extrabold tracking-tight">
            {HERO.headline.lead}
            <span className="text-terrax-crimson italic">{HERO.headline.accent}</span>
            {HERO.headline.tail}
            <span className="text-terrax-green">{HERO.headline.mark}</span>
          </h1>

          <p className="text-terrax-ink-soft mt-6 max-w-md text-lg leading-relaxed">{HERO.lead}</p>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <a
              href={MAILTO.campaign}
              className="font-terrax-display bg-terrax-ink text-terrax-card hover:bg-terrax-deep inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-sm font-extrabold transition-colors"
            >
              Start a Campaign
              <Icon name="arrowRight" className="size-4" />
            </a>
            <a
              href={ROUTES.driverApplication}
              className="font-terrax-display border-terrax-ink/25 text-terrax-ink hover:bg-terrax-ink/5 inline-flex items-center gap-2 rounded-full border px-7 py-3.5 text-sm font-extrabold transition-colors"
            >
              Drive &amp; Earn
            </a>
          </div>
        </div>

        <div className="relative">
          <div
            className="bg-terrax-card absolute -inset-4 -rotate-3 rounded-[2.5rem] sm:-inset-6"
            aria-hidden="true"
          />
          <div className="border-terrax-ink/15 bg-terrax-card relative rounded-[2rem] border p-1.5">
            <div className="bg-terrax-ink relative aspect-4/5 overflow-hidden rounded-[1.6rem]">
              <Image
                src={MEDIA.hero.src}
                width={MEDIA.hero.width}
                height={MEDIA.hero.height}
                alt={MEDIA.hero.alt}
                className="size-full object-cover"
                priority
              />

              {/* The route line the whole business is about, drawn over the visual. */}
              <svg
                viewBox="0 0 400 500"
                className="pointer-events-none absolute inset-0 size-full"
                aria-hidden="true"
              >
                <path
                  className="terrax-route-dash"
                  d="M42 430 C 130 400, 150 300, 230 262 S 350 190, 372 120"
                  fill="none"
                  stroke="#F2C94C"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
                <circle cx="42" cy="430" r="6" fill="#F2C94C" />
                <circle cx="230" cy="262" r="6" fill="#EE2F41" />
                <circle cx="372" cy="120" r="6" fill="#F2C94C" />
              </svg>

              <div className="terrax-float-slow border-terrax-card/15 bg-terrax-ink/85 absolute top-4 left-4 rounded-xl border px-3.5 py-2.5">
                <div className="font-terrax-display text-terrax-gold text-[9px] tracking-[0.25em] uppercase">
                  {HERO.imageCaption.eyebrow}
                </div>
                <div className="font-terrax-display text-terrax-card text-sm font-extrabold">
                  {HERO.imageCaption.title}
                </div>
              </div>

              <div className="border-terrax-card/15 bg-terrax-ink/85 absolute bottom-4 left-4 flex items-center gap-2 rounded-full border px-3.5 py-2">
                <span className="bg-terrax-gold size-2 rounded-full" aria-hidden="true" />
                <span className="text-terrax-card text-xs font-medium">{HERO.imageStatus}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
