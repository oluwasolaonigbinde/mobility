/**
 * Every string the Terrax Media company website renders, with its source.
 *
 * Sources:
 *  - GUIDE   docs/brand/terrax-media/Terrax Media Brand Guide.pdf
 *  - TAG     docs/brand/terrax-media/Terrax Media Tagline and Others.pdf
 *  - PRODUCT docs/product-requirements.md — the owner-approved product claim set,
 *            traced to the D18 Q1–Q34 confirmed client answers.
 *  - PAGE    the owner-supplied design page, kept verbatim where it asserts nothing
 *            beyond the brand documents.
 *
 * Rules for editing this file:
 *  1. No customer, partner, statistic, testimonial, award, coverage figure or
 *     campaign result may appear here. None exist in any source.
 *  2. No claim that results are "measurable". The approved reporting model keeps
 *     verified operations and modelled exposure structurally separate, so a blanket
 *     measurability claim would misstate it.
 *  3. Every new sentence needs a source tag above it.
 */

/** TAG — "Brand Name; Terrax Media" */
export const COMPANY = "Terrax Media";

/** TAG — "Product/App Name; Cardvert" */
export const PRODUCT = "Cardvert";

export const CONTACT = {
  /** TAG — "Official Business Email" */
  email: "terraxmediacompany@gmail.com",
  /** TAG — "Domain name; Terraxmedia.com" */
  siteUrl: "https://terraxmedia.com",
  /** TAG — displayed form of the domain */
  siteLabel: "terraxmedia.com",
  /**
   * TAG — "Social Media Handle; Terramedia_company", reproduced verbatim.
   *
   * The brand document spells it without the "x" of "Terrax". No platform or
   * profile URL is given anywhere in the brand materials, so this renders as
   * plain text: linking it would mean inventing a destination.
   */
  socialHandle: "@Terramedia_company",
} as const;

/** TAG — tagline option 3, the line the page is built around. */
export const TAGLINE = "Transforming City Movement into Brand Impact";

/**
 * GUIDE §1 "Who are we?", condensed for a meta description. It states what the
 * company is and the two audiences it serves, and nothing more.
 */
export const META_DESCRIPTION =
  "Terrax Media is an out-of-home advertising company that turns everyday city journeys into real-world brand visibility — and lets drivers earn from the miles they already drive.";

function mailto(subject: string, body: readonly string[]) {
  const query = new URLSearchParams({ subject, body: body.join("\n") });
  return `mailto:${CONTACT.email}?${query.toString().replace(/\+/g, "%20")}`;
}

/** Product entry points. Advertiser organisations remain operator-provisioned,
 * so prospective brands contact Terrax while drivers may apply directly. */
export const ROUTES = {
  driverApplication: "/apply",
  signIn: "/login",
} as const;

export const MAILTO = {
  campaign: mailto("Campaign enquiry — Terrax Media", [
    "Hello Terrax Media,",
    "",
    "I would like to discuss a vehicle advertising campaign.",
    "",
    "Company:",
    "Contact name:",
    "Phone:",
    "Campaign area(s):",
    "Preferred start date:",
    "Campaign length:",
    "",
    "Thank you.",
  ]),
} as const;

export type NavItem = { readonly href: string; readonly label: string };

/** Every entry is an in-page anchor; each `href` must match a section id. */
export const NAV: readonly NavItem[] = [
  { href: "#how-it-works", label: "How It Works" },
  { href: "#for-brands", label: "For Brands" },
  { href: "#for-drivers", label: "For Drivers" },
  { href: "#cardvert", label: "Cardvert" },
  { href: "#contact", label: "Contact" },
] as const;

export const HERO = {
  /** PAGE — positioning line, no capability claim. */
  eyebrow: "Vehicle advertising, reimagined",
  /** TAG — the tagline, set as the headline. */
  headline: {
    lead: "Transforming city ",
    accent: "movement",
    tail: " into brand ",
    mark: "impact",
  },
  /** PAGE — restates the two-sided model. GUIDE §1 vision states the driver revenue side. */
  lead: "Terrax Media turns everyday journeys into advertising opportunities — helping brands own the streets while drivers earn from the miles they already drive.",
  /**
   * Labels for the hero visual. They name the FORMAT and the medium, never a
   * campaign that is running: the visual is an illustration with an empty
   * advertising panel, so "live campaign" would assert a Terrax campaign that
   * does not exist. GUIDE §1 — vehicles carrying advertising across the city.
   */
  imageCaption: { eyebrow: "Campaign format", title: "Full vehicle wrap" },
  imageStatus: "Routes across the city",
} as const;

export type ValueItem = { readonly icon: IconName; readonly title: string; readonly body: string };

/** PAGE — properties of the medium itself. None is a performance claim. */
export const VALUE_STRIP: readonly ValueItem[] = [
  {
    icon: "mapPin",
    title: "City-wide visibility",
    body: "Presence across the routes people live on.",
  },
  {
    icon: "radar",
    title: "Real-world exposure",
    body: "Brands seen in physical, everyday context.",
  },
  {
    icon: "car",
    title: "Driver-powered",
    /** PRODUCT — driver approval and vehicle checks are a real product property. */
    body: "Campaigns carried by approved drivers.",
  },
  {
    icon: "scaling",
    title: "Flexible coverage",
    body: "One vehicle or a coordinated fleet.",
  },
];

export type Step = { readonly n: string; readonly title: string; readonly body: string };

export const HOW_IT_WORKS = {
  eyebrow: "How it works",
  title: "Three steps from brief to street",
  steps: [
    {
      n: "01",
      title: "Plan the campaign",
      /** PRODUCT STEPS 01 — quotation is built per campaign; areas and vehicles are chosen. */
      body: "Define the audience, the areas, the vehicles and the length of the campaign.",
    },
    {
      n: "02",
      title: "Activate the fleet",
      /** PRODUCT STEPS 03 — matching to eligible approved drivers, confirmed by an administrator. */
      body: "Match the campaign with approved drivers and eligible vehicles.",
    },
    {
      n: "03",
      /**
       * Retitled from the design page's "Move and measure". The approved
       * reporting model separates verified operations from modelled exposure,
       * so the promise here is a report, not a measurement capability.
       */
      title: "Move and report",
      /** PRODUCT REPORT — a Campaign Performance Analysis is standard for every campaign. */
      body: "The campaign travels the city with its vehicles, and you receive a campaign report when it ends.",
    },
  ] as const satisfies readonly Step[],
} as const;

export type Pathway = {
  readonly id: string;
  readonly icon: IconName;
  readonly eyebrow: string;
  readonly title: string;
  readonly points: readonly string[];
  readonly cta: { readonly label: string; readonly href: string };
};

/** The two conversion paths the page exists to separate. */
export const PATHWAYS: readonly [Pathway, Pathway] = [
  {
    id: "for-brands",
    icon: "building",
    eyebrow: "For Brands",
    title: "Extend campaigns beyond the screen",
    points: [
      "Extend campaigns beyond digital screens",
      "Build repeated visibility across real city routes",
      "Create location-aware brand experiences",
    ],
    cta: { label: "Advertise With Terrax", href: MAILTO.campaign },
  },
  {
    id: "for-drivers",
    icon: "users",
    eyebrow: "For Drivers",
    title: "Earn from the miles you already drive",
    points: [
      /** PRODUCT DRIVER_POINTS — the advertising travels with the driver's own driving. */
      "Turn regular journeys into additional income",
      "Access advertising opportunities suited to your vehicle",
      "Participate without changing everyday driving habits",
    ],
    cta: { label: "Become a Driver Partner", href: ROUTES.driverApplication },
  },
];

export const CARDVERT = {
  eyebrow: PRODUCT,
  title: "Cardvert puts brands in motion",
  /**
   * PRODUCT — Cardvert is the Terrax Media platform and driver app, not a
   * separate company or a campaign format. The design page framed it as the
   * campaign product; this states what it actually is.
   */
  lead: "Cardvert is the Terrax Media platform. Brands plan a campaign in it, approved drivers run their campaign time through it, and a single vehicle or a coordinated fleet becomes part of the streets, neighbourhoods and daily journeys that shape attention.",
  imageAlt:
    "Illustration of three unbranded vehicles travelling a shared city corridor, with their routes drawn as dashed lines across a simplified street grid.",
  cards: [
    {
      icon: "car",
      title: "Full vehicle campaigns",
      body: "A complete wrap turns a single vehicle into a moving brand statement.",
    },
    {
      icon: "layers",
      title: "Targeted fleet activations",
      body: "Coordinated vehicles working the same corridors for concentrated presence.",
    },
    {
      icon: "route",
      title: "Location-focused visibility",
      /** PRODUCT BRAND_POINTS — campaign areas are set per campaign. */
      body: "Campaigns shaped around the areas that matter to your audience.",
    },
  ],
} as const;

export const WHY = {
  eyebrow: `Why ${COMPANY}`,
  title: "A model built on the way cities already move",
  items: [
    {
      icon: "repeat",
      title: "Movement creates repeated exposure",
      body: "Vehicles travel the same routes daily, building familiarity over time.",
    },
    {
      icon: "mapPin",
      title: "Audiences met in the physical world",
      body: "Campaigns appear where attention is already directed — the street.",
    },
    {
      icon: "scaling",
      title: "Flexible for different business sizes",
      body: "Coverage can start small and expand as a campaign proves itself.",
    },
    {
      icon: "users",
      title: "Value on both sides",
      body: "Advertisers gain presence while drivers earn from their journeys.",
    },
  ],
} as const;

export const CONTACT_BAND = {
  title: "Ready to put your brand in motion?",
  lead: "Tell us about your campaign or your vehicle, and we'll take it from there.",
  primary: { label: "Launch a Campaign", href: MAILTO.campaign },
  secondary: { label: "Join as a Driver", href: ROUTES.driverApplication },
  emailPrefix: "Or email us directly at",
} as const;

export const FOOTER = {
  /**
   * GUIDE §1 — what the company is. The design page said "measurable brand
   * visibility"; "measurable" is removed, because the approved reporting model
   * does not support a blanket measurability claim.
   */
  blurb: `${COMPANY} is an out-of-home advertising company transforming city movement into real-world brand visibility.`,
  /** PRODUCT FOOTER_LEGAL — the relationship between the two names. */
  legal: `© ${new Date().getFullYear()} ${COMPANY}. ${PRODUCT} is the ${COMPANY} platform.`,
} as const;

export type IconName =
  | "arrowRight"
  | "building"
  | "car"
  | "layers"
  | "mapPin"
  | "menu"
  | "radar"
  | "repeat"
  | "route"
  | "scaling"
  | "users"
  | "close";
