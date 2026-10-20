import type { Metadata } from "next";
import { productFontVariables } from "@/lib/fonts";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Cardvert · Terrax Media",
    template: "%s · Cardvert",
  },
  description: "Manage your vehicle advertising campaigns and driving jobs with Terrax Media.",
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
