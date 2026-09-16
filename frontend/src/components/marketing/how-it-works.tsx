import { HOW_IT_WORKS } from "@/lib/marketing/site";
import { Reveal } from "./reveal";

/**
 * Three steps, as a hairline-ruled grid of cards.
 *
 * The step numerals use `--color-terrax-gold-ink` — the brown from the logo's own
 * terrax-green-to-brown-to-red gradient. Golden Accent itself is only 1.3:1 on this
 * ground, so the warm accent had to come from the other end of the gradient.
 */
export function HowItWorks() {
  return (
    <section id="how-it-works" className="terrax-grain bg-terrax-paper text-terrax-ink">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal>
          <p className="text-terrax-crimson-ink text-xs font-semibold tracking-[0.3em] uppercase">
            {HOW_IT_WORKS.eyebrow}
          </p>
          <h2 className="font-terrax-display mt-4 max-w-[18ch] text-[clamp(2rem,4.6vw,3.4rem)] leading-[0.95] font-extrabold tracking-tight">
            {HOW_IT_WORKS.title}
          </h2>
        </Reveal>

        <ol className="border-terrax-ink/12 bg-terrax-ink/12 relative mt-14 grid gap-px border md:grid-cols-3">
          <div
            className="pointer-events-none absolute top-[86px] left-0 hidden h-px w-full opacity-60 md:block"
            style={{
              backgroundImage:
                "repeating-linear-gradient(to right, var(--color-terrax-gold) 0 10px, transparent 10px 18px)",
            }}
            aria-hidden="true"
          />
          {HOW_IT_WORKS.steps.map((step, index) => (
            <Reveal as="li" key={step.n} delay={index * 90} className="bg-terrax-card relative p-8">
              <div className="font-terrax-display text-terrax-gold-ink text-5xl font-extrabold">
                {step.n}
              </div>
              <h3 className="font-terrax-display mt-6 text-xl font-extrabold">{step.title}</h3>
              <p className="text-terrax-ink-soft mt-2 text-sm leading-relaxed">{step.body}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
