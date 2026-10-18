import type { Metadata } from "next";
import { productFontVariables } from "@/lib/fonts";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Cardvert — Aggregate Mobility Measurement",
    template: "%s · Cardvert",
  },
  description:
    "Cardvert campaigns with Terrax aggregate measurement, hourly driver earnings, and fleet trust in one command center.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" style={productFontVariables}>
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
