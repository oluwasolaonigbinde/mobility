import type { Metadata } from "next";
import { CardvertSection } from "@/components/marketing/cardvert-section";
import { ContactBand } from "@/components/marketing/contact-band";
import { Hero } from "@/components/marketing/hero";
import { HowItWorks } from "@/components/marketing/how-it-works";
import { Pathways } from "@/components/marketing/pathways";
import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { ValueStrip } from "@/components/marketing/value-strip";
import { WhyTerrax } from "@/components/marketing/why-terrax";
import { COMPANY, META_DESCRIPTION, TAGLINE } from "@/lib/marketing/site";
import "./marketing.css";

export const metadata: Metadata = {
  title: { absolute: `${COMPANY} — ${TAGLINE}` },
  description: META_DESCRIPTION,
  applicationName: COMPANY,
};

/** Public Terrax Media front door for the Cardvert product. */
export default function HomePage() {
  return (
    <div className="terrax-site bg-terrax-paper text-terrax-ink flex min-h-screen flex-1 flex-col">
      <noscript>
        <style>{".terrax-reveal{opacity:1!important;animation:none!important}"}</style>
      </noscript>

      <a
        href="#main"
        className="font-terrax-display bg-terrax-ink text-terrax-card sr-only rounded-full px-5 py-3 text-sm font-extrabold focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-100"
      >
        Skip to content
      </a>

      <SiteHeader />

      <main id="main">
        <Hero />
        <ValueStrip />
        <HowItWorks />
        <Pathways />
        <CardvertSection />
        <WhyTerrax />
        <ContactBand />
      </main>

      <SiteFooter />
    </div>
  );
}
