import Image from "next/image";
import {
  CARDVERT,
  CONTACT,
  FOOTER_LEGAL,
  MAILTO,
  MISSION,
  NAV,
  PILOT_FACTS,
  PRIVACY_NOTE,
  REPORT,
  SERVICES,
  TAGLINE,
  VISION,
  WHO_WE_ARE,
} from "./content";
import { GrainField } from "./motifs";
import { Pathways } from "./pathways";
import { ScrollEffects } from "./scroll-effects";
import { SiteHeader } from "./site-header";
import { Steps } from "./steps";

/**
 * Terrax Media public landing page.
 *
 * Every claim traces to `./content.ts`, which cites its source in the brand
 * documents or the confirmed client answers. Do not add capability, scale,
 * partner or availability claims without a source there.
 */
export default function LandingPage() {
  return (
    <>
      <a className="tx-skip" href="#tx-main">
        Skip to content
      </a>

      <SiteHeader />
      <ScrollEffects />

      <main id="tx-main">
        {/* ------------------------------------------------------------ hero */}
        <section className="tx-hero">
          <div className="tx-hero__grain" aria-hidden="true">
            <GrainField />
          </div>

          <div className="tx-shell tx-shell--layered">
            <div className="tx-hero__head">
              <p className="tx-micro tx-eyebrow">Out of home · on the move</p>

              <h1 className="tx-display">
                driving <span className="tx-mark">impact</span>
                <span className="tx-display__l2">
                  <span className="tx-hot">beyond</span> locations
                </span>
              </h1>
            </div>

            <div className="tx-hero__split">
              <p className="tx-lead">
                {WHO_WE_ARE} We turn approved everyday cars into moving advertising — and pay their
                drivers for the campaign hours they work.
              </p>

              <div className="tx-hero__actions">
                <a className="tx-btn tx-btn--ink" href={MAILTO.campaign}>
                  Start a campaign
                  <span className="tx-btn__arrow" aria-hidden="true">
                    →
                  </span>
                </a>
                <a className="tx-btn tx-btn--outline" href={MAILTO.driver}>
                  Earn as a driver
                </a>
              </div>
            </div>

            <div className="tx-ticket">
              {PILOT_FACTS.map((fact) => (
                <div className="tx-ticket__item" key={fact.label}>
                  <span className="tx-ticket__value">{fact.value}</span>
                  <span className="tx-micro tx-ticket__label">{fact.label}</span>
                </div>
              ))}
              <p className="tx-micro tx-ticket__note">
                The shape of our first controlled pilot. Campaigns beyond it are quoted
                individually.
              </p>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------ what we do */}
        <section className="tx-section" id="what-we-do">
          <div className="tx-shell">
            <div className="tx-head" data-tx-reveal>
              <div className="tx-head__title">
                <p className="tx-micro tx-eyebrow">What we do</p>
                <h2 className="tx-h2">
                  a billboard stands still.
                  <br />
                  ours goes where the people are.
                </h2>
              </div>
              <p className="tx-lead tx-head__aside">{MISSION}</p>
            </div>

            <div className="tx-manifest">
              {SERVICES.map((service, index) => (
                <article className="tx-manifest__row" key={service.title} data-tx-reveal>
                  <span className="tx-manifest__n" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3 className="tx-h3">{service.title}</h3>
                  <div>
                    <p className="tx-manifest__body">{service.body}</p>
                    <span className="tx-micro tx-manifest__note">{service.note}</span>
                  </div>
                </article>
              ))}
            </div>

            <div className="tx-quotes" data-tx-reveal>
              <div className="tx-quote tx-quote--mint">
                <p className="tx-micro tx-quote__label">Our vision</p>
                <p className="tx-quote__text">{VISION}</p>
              </div>
              <div className="tx-quote tx-quote--outline">
                <p className="tx-micro tx-quote__label">Where we are today</p>
                <p className="tx-quote__text">
                  A controlled pilot in {CONTACT.city}, running printed campaigns on roadworthy cars
                  that meet our documentation and condition checks, measured end to end.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------- pathways */}
        <section className="tx-section" id="pathways">
          <div className="tx-shell">
            <div className="tx-head" data-tx-reveal>
              <div className="tx-head__title">
                <p className="tx-micro tx-eyebrow">Two sides, one campaign</p>
                <h2 className="tx-h2">every campaign pays two people attention.</h2>
              </div>
              <p className="tx-lead tx-head__aside">
                The brand that wants to be seen, and the driver who makes it happen. Pick your side.
              </p>
            </div>
            <Pathways />
          </div>
        </section>

        {/* ---------------------------------------------------- how it works */}
        <section className="tx-section" id="how-it-works">
          <div className="tx-shell">
            <div className="tx-head" data-tx-reveal>
              <div className="tx-head__title">
                <p className="tx-micro tx-eyebrow">How it works</p>
                <h2 className="tx-h2">six stops, both sides visible.</h2>
              </div>
              <p className="tx-lead tx-head__aside">
                Open any stop to see what happens for the brand and what happens for the driver at
                the same moment.
              </p>
            </div>
            <Steps />
          </div>
        </section>

        {/* --------------------------------------------------------- cardvert */}
        <section className="tx-section tx-section--dark" id="cardvert">
          <div className="tx-shell tx-cardvert">
            <div data-tx-reveal>
              <p className="tx-micro tx-eyebrow">{CARDVERT.eyebrow}</p>
              <h2 className="tx-h2">{CARDVERT.title.toLowerCase()}</h2>
              <p className="tx-lead" style={{ marginTop: "1.25rem", maxWidth: "48ch" }}>
                {CARDVERT.lead}
              </p>

              <ul className="tx-cardvert__list">
                {CARDVERT.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>

              <a className="tx-btn tx-btn--gold" href={MAILTO.driver}>
                Apply to drive
                <span className="tx-btn__arrow" aria-hidden="true">
                  →
                </span>
              </a>
              <p className="tx-micro tx-note" style={{ marginTop: "1.75rem", maxWidth: "52ch" }}>
                {CARDVERT.footnote}
              </p>
            </div>

            {/* Illustrative sketch of the earnings screen: real Cardvert
                vocabulary only — no invented rates, hours or totals. */}
            <div data-tx-reveal>
              <div className="tx-device" role="img" aria-label={CARDVERT.deviceAlt}>
                <div className="tx-device__screen" aria-hidden="true">
                  <div className="tx-micro tx-device__brand">
                    <span>Cardvert</span>
                    <span className="tx-device__live">
                      <span className="tx-device__dot" />
                      Trip running
                    </span>
                  </div>
                  <p className="tx-micro tx-device__label">This week</p>
                  <p className="tx-device__hours">
                    verified hours,
                    <br />
                    priced by zone
                  </p>
                  <div className="tx-device__rows">
                    <div className="tx-device__row">
                      <span>Base zone hours</span>
                      <b>Base rate</b>
                    </div>
                    <div className="tx-device__row tx-device__row--premium">
                      <span>Premium zone hours</span>
                      <b>Premium rate</b>
                    </div>
                    <div className="tx-device__row tx-device__row--unpaid">
                      <span>Exclusion / invalid</span>
                      <b>Not paid</b>
                    </div>
                  </div>
                  <span className="tx-device__cta">End trip</span>
                  <p className="tx-micro tx-device__caption">
                    Rates are set per campaign and shown in your offer.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------- reporting */}
        <section className="tx-section" id="reporting">
          <div className="tx-shell">
            <div className="tx-head" data-tx-reveal>
              <div className="tx-head__title">
                <p className="tx-micro tx-eyebrow">Reporting</p>
                <h2 className="tx-h2">we tell you which numbers were measured.</h2>
              </div>
              <p className="tx-lead tx-head__aside">{REPORT.lead}</p>
            </div>

            <div className="tx-report" data-tx-reveal>
              <div className="tx-report__head">
                <span
                  className="tx-logo"
                  style={{ ["--tx-logo-h" as string]: "30px" }}
                  aria-hidden="true"
                >
                  {/* Full-colour lockup, the approved form on a light ground. */}
                  <Image
                    src="/brand/terrax/terrax-logo.png"
                    alt=""
                    width={2092}
                    height={680}
                    sizes="130px"
                  />
                </span>
                <span className="tx-micro tx-report__title">{REPORT.title}</span>
              </div>

              {REPORT.rows.map((row) => (
                <div className="tx-report__row" key={row.label}>
                  <span className="tx-report__label">{row.label}</span>
                  <p className="tx-report__body">{row.body}</p>
                  <span
                    className={
                      row.kind === "Measured"
                        ? "tx-tag tx-tag--measured"
                        : "tx-tag tx-tag--modelled"
                    }
                  >
                    {row.kind}
                  </span>
                </div>
              ))}

              <p className="tx-micro tx-report__foot">{REPORT.footnote}</p>
            </div>

            <p className="tx-note" style={{ marginTop: "1.75rem", maxWidth: "70ch" }}>
              {PRIVACY_NOTE}
            </p>
          </div>
        </section>

        {/* ---------------------------------------------------------- contact */}
        <section className="tx-section tx-contact" id="contact">
          <div className="tx-shell tx-contact__inner" data-tx-reveal>
            <div>
              <p className="tx-micro tx-eyebrow" style={{ color: "inherit" }}>
                Get in touch
              </p>
              <h2 className="tx-h2">tell us where you want to be seen.</h2>
              <p>
                Send us the areas, the dates and the length of campaign you have in mind and we will
                come back with an itemised quotation. Drivers: send your vehicle details and we will
                start you on the checks.
              </p>
              <div className="tx-contact__actions">
                <a className="tx-btn tx-btn--ink" href={MAILTO.campaign}>
                  Request a quotation
                  <span className="tx-btn__arrow" aria-hidden="true">
                    →
                  </span>
                </a>
                <a className="tx-btn tx-btn--outline" href={MAILTO.driver}>
                  Apply to drive
                </a>
              </div>
            </div>

            <dl className="tx-details">
              <div>
                <dt className="tx-micro">Email</dt>
                <dd>
                  <a href={MAILTO.general}>{CONTACT.email}</a>
                </dd>
              </div>
              <div>
                <dt className="tx-micro">Web</dt>
                <dd>{CONTACT.domain}</dd>
              </div>
              <div>
                <dt className="tx-micro">Social</dt>
                <dd>{CONTACT.socialHandle}</dd>
              </div>
              <div>
                <dt className="tx-micro">Based in</dt>
                <dd>{CONTACT.city}</dd>
              </div>
            </dl>
          </div>
        </section>
      </main>

      {/* ------------------------------------------------------------ footer */}
      <footer className="tx-footer">
        <div className="tx-shell">
          <div className="tx-footer__top">
            <div>
              <span className="tx-logo" style={{ ["--tx-logo-h" as string]: "36px" }}>
                <Image
                  src="/brand/terrax/terrax-logo-white.png"
                  alt="Terrax Media"
                  width={1544}
                  height={499}
                  sizes="160px"
                />
              </span>
              <p className="tx-footer__blurb">{TAGLINE.toLowerCase()}</p>
            </div>

            <div className="tx-footer__col">
              <h3 className="tx-micro">Explore</h3>
              <ul>
                {NAV.map((item) => (
                  <li key={item.href}>
                    <a href={item.href}>{item.label}</a>
                  </li>
                ))}
              </ul>
            </div>

            <div className="tx-footer__col">
              <h3 className="tx-micro">Get in touch</h3>
              <ul>
                <li>
                  <a href={MAILTO.general}>{CONTACT.email}</a>
                </li>
                <li>
                  <span>{CONTACT.domain}</span>
                </li>
                <li>
                  <span>{CONTACT.socialHandle}</span>
                </li>
                <li>
                  <span>{CONTACT.productDomain}</span>
                </li>
                <li>
                  <a href="/login">Sign in to the platform</a>
                </li>
              </ul>
            </div>
          </div>

          <div className="tx-footer__rule" aria-hidden="true" />

          <div className="tx-micro tx-footer__bottom">
            <p>{FOOTER_LEGAL}</p>
            <p>{CONTACT.city}</p>
          </div>
        </div>
      </footer>
    </>
  );
}
