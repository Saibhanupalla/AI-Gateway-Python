import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Gateway — Dashboard",
  description: "Enterprise LLM Gateway admin console with analytics, user management, and governance",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
