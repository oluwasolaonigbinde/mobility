import { VALUE_STRIP } from "@/lib/marketing/site";
import { Icon } from "./icon";
import { Reveal } from "./reveal";

/**
 * Four properties of the medium, sitting on a rule between the hero and the
 * first full section. Each states something true of vehicle advertising itself;
 * none is a performance figure.
 */
export function ValueStrip() {
  return (
    <section
      aria-label="What vehicle advertising offers"
      className="border-terrax-ink/10 bg-terrax-card/60 border-y"
    >
      <div className="mx-auto max-w-7xl px-5 py-10 md:px-8">
        <ul className="grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
          {VALUE_STRIP.map((item, index) => (
            <Reveal as="li" key={item.title} delay={index * 70} className="flex items-start gap-3">
              <Icon name={item.icon} className="text-terrax-crimson-ink mt-0.5 size-5 shrink-0" />
              <div className="min-w-0">
                <div className="font-terrax-display text-terrax-ink text-sm font-extrabold">
                  {item.title}
                </div>
                <p className="text-terrax-ink-soft text-sm leading-snug">{item.body}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
