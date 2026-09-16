import Image from "next/image";
import { CARDVERT } from "@/lib/marketing/site";
import { MEDIA } from "@/lib/marketing/media";
import { Icon } from "./icon";
import { Reveal } from "./reveal";

/**
 * The one full-dark band on the page, naming the product.
 *
 * Terrax Media is the company; Cardvert is its platform. The design page read
 * as though Cardvert were a campaign format, so the lead here says what it
 * actually is. The three cards below describe campaign shapes, not features.
 */
export function CardvertSection() {
  return (
    <section id="cardvert" className="terrax-on-dark bg-terrax-ink text-terrax-card">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <div className="grid items-end gap-10 lg:grid-cols-[1.1fr_1fr]">
          <Reveal>
            <p className="text-terrax-gold text-xs font-semibold tracking-[0.3em] uppercase">
              {CARDVERT.eyebrow}
            </p>
            <h2 className="font-terrax-display mt-4 max-w-[16ch] text-[clamp(2rem,4.6vw,3.4rem)] leading-[0.95] font-extrabold">
              {CARDVERT.title}
            </h2>
          </Reveal>
          <Reveal delay={90}>
            <p className="text-terrax-mint max-w-[52ch] text-base leading-relaxed">
              {CARDVERT.lead}
            </p>
          </Reveal>
        </div>

        <Reveal className="border-terrax-card/12 mt-12 overflow-hidden rounded-2xl border">
          <Image
            src={MEDIA.fleet.src}
            width={MEDIA.fleet.width}
            height={MEDIA.fleet.height}
            alt={MEDIA.fleet.alt}
            className="aspect-video w-full object-cover"
            loading="lazy"
          />
        </Reveal>

        <ul className="border-terrax-card/12 bg-terrax-card/12 mt-px grid gap-px border md:grid-cols-3">
          {CARDVERT.cards.map((card, index) => (
            <Reveal as="li" key={card.title} delay={index * 90} className="bg-terrax-ink p-8">
              <Icon name={card.icon} className="text-terrax-gold size-6" />
              <h3 className="font-terrax-display mt-5 text-lg font-extrabold">{card.title}</h3>
              <p className="text-terrax-mint mt-2 text-sm leading-relaxed">{card.body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
