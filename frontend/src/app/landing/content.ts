/**
 * Every string on the Terrax Media landing page, with its source.
 *
 * Sources (all in-repo):
 *  - BRAND  = docs/brand/terrax-media/Terrax Media Brand Guide.pdf
 *  - TAG    = docs/brand/terrax-media/Terrax Media Tagline and Others.pdf
 *  - Qnn    = docs/decisions-log.md Part 2, confirmed client answers (D18–D20)
 *
 * Nothing here may assert a capability, metric, price, partner or availability
 * that those documents do not state. Superseded proposal wording (for example
 * mileage-based driver pay) must not reappear: D18/Q5 replaced it with fixed
 * hourly base/premium zone pay.
 */

export const CONTACT = {
  /** TAG — "Official Business Email" */
  email: "terraxmediacompany@gmail.com",
  /** TAG — "Domain name" */
  domain: "terraxmedia.com",
  /** TAG — "Social Media Handle" (preserved verbatim) */
  socialHandle: "Terramedia_company",
  /** TAG — "(New-incoming)" product domain for Cardvert */
  productDomain: "Cardvert.com",
  /** Q30 — confirmed pilot city */
  city: "Abuja, Nigeria",
} as const;

function mailto(subject: string, body: string) {
  return `mailto:${CONTACT.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/** No backend exists for this page, so every conversion is a prepared email. */
export const MAILTO = {
  campaign: mailto(
    "Campaign enquiry — Terrax Media",
    [
      "Hello Terrax Media,",
      "",
      "I would like a quotation for a moving-vehicle advertising campaign.",
      "",
      "Company:",
      "Contact name:",
      "Phone:",
      "Campaign area(s):",
      "Preferred start date:",
      "Campaign length:",
      "",
      "Thank you.",
    ].join("\n"),
  ),
  driver: mailto(
    "Driver application — Cardvert",
    [
      "Hello Terrax Media,",
      "",
      "I would like to earn by carrying approved advertising on my car.",
      "",
      "Full name:",
      "Phone:",
      "City:",
      "Vehicle make / model / year:",
      "Vehicle registered in my name (yes/no):",
      "",
      "Thank you.",
    ].join("\n"),
  ),
  general: mailto(
    "Enquiry — Terrax Media",
    ["Hello Terrax Media,", "", "", "Thank you."].join("\n"),
  ),
} as const;

export const NAV = [
  { href: "#what-we-do", label: "What we do" },
  { href: "#pathways", label: "Brands & drivers" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#cardvert", label: "Cardvert" },
  { href: "#reporting", label: "Reporting" },
  { href: "#contact", label: "Contact" },
] as const;

/** TAG — the standing line, printed unnumbered beneath the three options. */
export const TAGLINE = "Driving Impact Beyond Locations";

/** BRAND §1 — "Who are we?" */
export const WHO_WE_ARE =
  "Terrax Media is a digital Out of Home advertisement (OOH/DOOH) company, amplifying brands ad reach beyond a location.";

/** BRAND §1 — Mission, verbatim intent. */
export const MISSION =
  "To drive growth for our clients through targeted advertising experiences. Provide OOH advertising solutions that maximize brand visibility by putting your product and services in the spotlight where the world would never miss it.";

/** BRAND §1 — Vision. Kept explicitly labelled as vision: the smart-screen and
 *  motorcycle/bike formats are the stated ambition, not the confirmed pilot,
 *  which runs on approved cars (Q19). */
export const VISION =
  "To be the leading smart DOOH advertising company that transforms moving ads — providing on-demand advertising anytime and anywhere, into locations and audiences unreached before, while creating a new stream of revenue for rider and driver communities.";

/** Q30 — confirmed pilot shape. Labelled as the pilot, never as scale claims. */
export const PILOT_FACTS = [
  { value: "Abuja", label: "Pilot city" },
  { value: "10", label: "Vehicles" },
  { value: "5", label: "Paying advertisers" },
  { value: "3 months", label: "Pilot length" },
] as const;

export const SERVICES = [
  {
    title: "Advertising that moves",
    body: "Your creative is produced and installed on approved cars, then it travels the city with them. One campaign runs on one vehicle at a time, so your message is never sharing the car with another brand.",
    note: "Q16 · one active campaign per vehicle",
  },
  {
    title: "Verified operations",
    body: "Campaign time is only counted when the vehicle is genuinely working: inside the campaign window, with valid GPS and real movement. Installation is photographed and approved before a single hour can earn.",
    note: "Q5, Q17 · verified hours and approved installation evidence",
  },
  {
    title: "Managed end to end",
    body: "Terrax Media coordinates printing, installation, removal and permits through approved vendors, and every one of those costs is itemised in your quotation.",
    note: "Q25 · platform-managed production",
  },
] as const;

export const BRAND_POINTS = [
  {
    title: "A quotation built for your campaign",
    body: "Every campaign is quoted individually — areas, vehicles, duration, production and permits, itemised. Prices and totals are shown VAT-inclusive, and the invoice still itemises net, VAT and gross.",
  },
  {
    title: "You approve the creative",
    body: "Upload your artwork in the platform. It is reviewed and approved before anything goes to production, so nothing is printed that you have not signed off.",
  },
  {
    title: "Choose where it matters",
    body: "Set the areas that matter to your campaign. Time inside your premium zone is priced differently from time outside it, and exclusion zones are simply not counted.",
  },
  {
    title: "Results you can read",
    body: "A Campaign Performance Analysis that separates what was verified from what was modelled — no blending the two into one flattering number.",
  },
] as const;

export const DRIVER_POINTS = [
  {
    title: "Your car keeps its job",
    body: "You drive the way you already drive. The advertising travels with you; it does not tell you where to go.",
  },
  {
    title: "Paid by the hour, not the kilometre",
    body: "You earn a set hourly amount for verified campaign time, and a higher hourly amount for time inside the campaign's premium zone. Exclusion zones and invalid time are not paid.",
  },
  {
    title: "You accept before you commit",
    body: "You receive a complete offer with its terms and decide to accept or decline. Nothing is assigned to your vehicle without you.",
  },
  {
    title: "Weekly, and explained",
    body: "Cleanly assessed earnings go into the next weekly payout batch and are transferred to your verified bank account. Anything flagged is reviewed by a person, with the reason shown and a way to dispute it.",
  },
] as const;

export const STEPS = [
  {
    n: "01",
    title: "Quotation and terms",
    brand:
      "You tell us the campaign you want. We prepare a custom quotation; there is no fixed package catalogue. Standard advertisers pay in full before printing or installation begins.",
    driver:
      "You register with your licence, vehicle registration, insurance, NIN, vehicle photos and bank details, and wait for approval.",
    source: "Q1, Q2, Q13, Q26",
  },
  {
    n: "02",
    title: "Creative and approval",
    brand:
      "You upload your artwork in the platform. Terrax Media reviews and approves or rejects it before production.",
    driver:
      "Your documents are checked by an administrator. Only approved drivers with roadworthy, eligible cars can be offered work.",
    source: "Q18, Q19",
  },
  {
    n: "03",
    title: "Matching and the offer",
    brand:
      "The system recommends eligible drivers and vehicles for your campaign areas. An administrator approves the final assignment.",
    driver:
      "You receive an offer with its complete terms. You accept or decline; the terms you accepted are recorded and cannot be changed afterwards.",
    source: "Q7, Q8",
  },
  {
    n: "04",
    title: "Production and installation",
    brand:
      "Approved vendors print and install the creative. The installation is photographed and the photo is approved before campaign hours can earn.",
    driver:
      "Your car is fitted by an approved vendor. Removal at the end of the campaign is handled the same way.",
    source: "Q17, Q25",
  },
  {
    n: "05",
    title: "On the road",
    brand:
      "Activation happens only when funding, approved creative, assigned eligible vehicles and approved installation evidence are all in place.",
    driver:
      "You open Cardvert and start your trip when you begin driving, and end it when you stop. Verified time accumulates against the campaign.",
    source: "Q10, Q15",
  },
  {
    n: "06",
    title: "Results and payout",
    brand:
      "You receive a Campaign Performance Analysis: verified operations, clearly labelled modelled exposure, and target-area coverage.",
    driver:
      "Clean earnings join the next weekly batch and are transferred automatically to your verified account.",
    source: "Q12, Q22, Q27, Q30",
  },
] as const;

export const CARDVERT = {
  eyebrow: "The driver app",
  title: "Cardvert",
  lead: "Cardvert is Terrax Media's driver app. Approved drivers use it to see the work they have been offered, run their campaign time, and understand exactly how an amount was reached.",
  points: [
    "Installs to your phone's home screen — no app store account needed for the pilot.",
    "You start and end each trip yourself, with the screen on.",
    "Campaign time is checked against the schedule and the campaign area as you drive.",
    "Your earnings screen shows the hours that counted and the rate that applied to them.",
    "If your connection drops, trips are held on the device and sent when you are back online.",
  ],
  deviceAlt:
    "Sketch of the Cardvert earnings screen: this week's verified hours priced by zone, with a row each for base zone hours, premium zone hours and unpaid exclusion or invalid time, and an End trip button.",
  /** Q10 — pilot client is the screen-on installable PWA; native background
   *  tracking is explicitly after the pilot, so it is not promised here. */
  footnote:
    "During the Abuja pilot, Cardvert runs with the screen on and driver-controlled start and end. Background tracking is planned for after the pilot.",
} as const;

export const REPORT = {
  title: "Campaign Performance Analysis",
  lead: "Standard reporting for every campaign. What was measured and what was modelled stay visually and structurally separate.",
  rows: [
    {
      label: "Verified operations",
      body: "Campaign days, verified hours, vehicles active and the routes actually driven.",
      kind: "Measured",
    },
    {
      label: "Exposure estimate",
      body: "Impression and exposure figures derived from route, time and traffic assumptions — labelled as estimated throughout.",
      kind: "Modelled",
    },
    {
      label: "Target-area coverage",
      body: "How much of your target area the campaign actually reached, against a defined measurement contract.",
      kind: "Measured",
    },
  ],
  /** Q30 — financial ROI is optional and conditional; stated as such. */
  footnote:
    "Financial ROI is optional. It appears only when you supply conversion and revenue inputs and an approved, reproducible methodology is in place.",
} as const;

/** Q11 / Q31 — the privacy boundary is a real, documented product property. */
export const PRIVACY_NOTE =
  "Route and exposure data is never treated as a person-level audience. Terrax Media's legal and compliance adviser approves privacy, consent and retention before live campaign data is used.";

export const FOOTER_LEGAL = "© 2026 Terrax Media. Cardvert is the Terrax Media driver app.";
