import { NextResponse } from "next/server";

/**
 * Scoped web-app manifest: the driver surface installs as its own app
 * ("Cardvert Driver"), standalone display, scoped to /driver — while the
 * advertiser/admin portal remains a regular web app on the same origin.
 */
export function GET() {
  return NextResponse.json(
    {
      name: "Cardvert Driver",
      short_name: "Cardvert",
      description: "Track campaigns and review hourly earnings backed by aggregate measurement.",
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
