import { NextResponse } from "next/server";

/**
 * Scoped web-app manifest: the driver surface installs as its own app
 * ("Vantage Driver"), standalone display, scoped to /driver — while the
 * advertiser/admin portal remains a regular web app on the same origin.
 */
export function GET() {
  return NextResponse.json(
    {
      name: "Vantage Driver",
      short_name: "Vantage",
      description: "Drive, get seen, get paid — campaign tracking and earnings for drivers.",
      id: "/driver",
      start_url: "/driver",
      scope: "/driver",
      display: "standalone",
      orientation: "portrait",
      background_color: "#0a0b0e",
      theme_color: "#0a0b0e",
      icons: [
        { src: "/icons/driver-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
        { src: "/icons/driver-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        { src: "/icons/driver-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      ],
    },
    { headers: { "content-type": "application/manifest+json" } },
  );
}
