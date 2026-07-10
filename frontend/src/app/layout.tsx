import type { Metadata } from "next";
import { clashDisplay, satoshi, plexMono } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Vantage — Urban Attention, Measured",
    template: "%s · Vantage",
  },
  description:
    "The measurable mobility advertising & attribution network. Campaigns, live analytics, driver earnings and fraud control in one command center.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${clashDisplay.variable} ${satoshi.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
