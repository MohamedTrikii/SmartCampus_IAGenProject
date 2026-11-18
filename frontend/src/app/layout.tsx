import type { ReactNode } from "react";
import Header from "@/components/Header";
import "./globals.css";

export const metadata = {
  title: "SmartCampus AI — Orientation IIT / ISB",
  description: "Assistant d'orientation universitaire en français, tunisien et Arabizi",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <Header />
        {children}
      </body>
    </html>
  );
}
