import type { Metadata } from "next";
import { clashDisplay, productFontVariables, satoshi } from "@/lib/fonts";
import { THEME_BOOT_SCRIPT } from "@/lib/themes";
import { ThemeSwitcher } from "@/components/ui/theme-switcher";
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
    <html
      lang="en"
      suppressHydrationWarning
      className={`${clashDisplay.variable} ${satoshi.variable} h-full antialiased`}
      style={productFontVariables}
    >
      <body className="flex min-h-full flex-col">
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        <Providers>{children}</Providers>
        <ThemeSwitcher />
      </body>
    </html>
  );
}
