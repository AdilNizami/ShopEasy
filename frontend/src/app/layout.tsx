import type { Metadata } from "next";
import "./globals.css";
import { AppProviders } from "@/components/app-providers";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: { default: "ShopEasy — Thoughtful things, chosen well", template: "%s | ShopEasy" },
  description: "Discover considered everyday goods from the ShopEasy catalog.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>
          <div className="min-h-screen">
            <div className="bg-ink px-4 py-2 text-center text-xs font-medium tracking-wide text-white">
              Thoughtful finds for everyday living <span className="mx-2 text-citrus">·</span> Account-backed carts and orders
            </div>
            <SiteHeader />
            <main>{children}</main>
            <footer className="mt-24 border-t border-line bg-white">
              <div className="container-shop flex flex-col gap-5 py-10 sm:flex-row sm:items-center sm:justify-between">
                <a href="/" className="font-display text-2xl font-bold tracking-tight">ShopEasy<span className="text-green-600">.</span></a>
                <p className="max-w-md text-sm leading-6 text-muted">A considered collection for the everyday. Product availability and prices are provided by our live catalog.</p>
                <p className="text-xs text-muted">© {new Date().getFullYear()} ShopEasy</p>
              </div>
            </footer>
          </div>
        </AppProviders>
      </body>
    </html>
  );
}
