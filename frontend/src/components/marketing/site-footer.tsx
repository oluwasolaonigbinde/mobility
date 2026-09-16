import { CONTACT, FOOTER, NAV, ROUTES } from "@/lib/marketing/site";
import { Wordmark } from "./wordmark";

/**
 * Footer: the reversed logo lockup, the same navigation as the header, and the
 * three official contact details from the brand document.
 *
 * The social handle is rendered as plain text, not a link. The brand document
 * gives the handle but no platform and no profile URL, and inventing one would
 * mean shipping a link that goes nowhere.
 */
export function SiteFooter() {
  return (
    <footer className="terrax-on-dark bg-terrax-ink text-terrax-mint">
      {/* Three columns only from `lg`. At `md` the three tracks are ~208px wide,
          which is narrower than the official email address and pushed the page
          3px into horizontal overflow at 768px. */}
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 md:px-8 lg:grid-cols-3">
        <div>
          <Wordmark variant="dark" className="h-9 w-auto" />
          <p className="mt-4 max-w-[34ch] text-sm leading-relaxed">{FOOTER.blurb}</p>
        </div>

        <nav aria-label="Footer" className="space-y-2 text-sm">
          {NAV.map((item) => (
            <a
              key={item.href}
              className="hover:text-terrax-gold block transition-colors"
              href={item.href}
            >
              {item.label}
            </a>
          ))}
          <a className="hover:text-terrax-gold block transition-colors" href={ROUTES.signIn}>
            Open Cardvert
          </a>
          <a
            className="hover:text-terrax-gold block transition-colors"
            href={ROUTES.driverApplication}
          >
            Apply to drive
          </a>
        </nav>

        <div className="space-y-2 text-sm lg:text-right">
          <a
            className="hover:text-terrax-gold block transition-colors"
            href={`mailto:${CONTACT.email}`}
          >
            {CONTACT.email}
          </a>
          <a
            className="hover:text-terrax-gold block transition-colors"
            href={CONTACT.siteUrl}
            rel="noopener"
          >
            {CONTACT.siteLabel}
          </a>
          <span className="block">{CONTACT.socialHandle}</span>
        </div>
      </div>

      <div className="border-terrax-card/10 border-t">
        <div className="text-terrax-card/70 mx-auto max-w-7xl px-5 py-5 text-xs md:px-8">
          {FOOTER.legal}
        </div>
      </div>
    </footer>
  );
}
