import { WHY } from "@/lib/marketing/site";
import { Icon } from "./icon";
import { Reveal } from "./reveal";

/** Why the model works, as four rule-topped statements about how cities move. */
export function WhyTerrax() {
  return (
    <section aria-labelledby="why-heading" className="terrax-grain bg-terrax-paper text-terrax-ink">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal>
          <p className="text-terrax-crimson-ink text-xs font-semibold tracking-[0.3em] uppercase">
            {WHY.eyebrow}
          </p>
          <h2
            id="why-heading"
            className="font-terrax-display mt-4 max-w-[20ch] text-[clamp(2rem,4.6vw,3.4rem)] leading-[0.95] font-extrabold tracking-tight"
          >
            {WHY.title}
          </h2>
        </Reveal>

        <ul className="mt-14 grid gap-x-12 gap-y-10 sm:grid-cols-2">
          {WHY.items.map((item, index) => (
            <Reveal
              as="li"
              key={item.title}
              delay={index * 80}
              className="border-terrax-ink/15 border-t pt-6"
            >
              <Icon name={item.icon} className="text-terrax-gold-ink size-5" />
              <h3 className="font-terrax-display mt-4 max-w-[24ch] text-xl font-extrabold">
                {item.title}
              </h3>
              <p className="text-terrax-ink-soft mt-2 max-w-[46ch] text-sm leading-relaxed">
                {item.body}
              </p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
