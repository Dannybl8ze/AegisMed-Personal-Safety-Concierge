import type { Metadata, Viewport } from "next";
import { Figtree, Urbanist } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

// Urbanist carries the display type (light, geometric); Figtree carries body text.
const urbanist = Urbanist({
  variable: "--font-urbanist",
  subsets: ["latin"],
  display: "swap",
});

const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AegisMed - Caregiver Safety Concierge Portal",
  description:
    "Review medication requests, resolve safety alerts and audit caregiver override decisions.",
};

export const viewport: Viewport = {
  themeColor: "#eef1f4",
  colorScheme: "light",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${urbanist.variable} ${figtree.variable} h-full antialiased`}>
      <body className="min-h-full">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
