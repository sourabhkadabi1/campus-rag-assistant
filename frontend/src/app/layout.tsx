import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/lib/context";
import { Header } from "@/components/Header";
import { ProfileModal } from "@/components/ProfileModal";
import { UpgradeModal } from "@/components/UpgradeModal";
import { PdfViewerModal } from "@/components/PdfViewerModal";

export const metadata: Metadata = {
  title: "PESU Academy AI; College RAG Assistant",
  description:
    "Grounded, syllabus-aligned AI assistant for college students with exact textbook citations, deep reasoning, and instant summaries.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AppProvider>
          <div className="flex flex-col min-h-screen">
            <Header />
            <main className="flex-1 flex flex-col">{children}</main>
          </div>
          <ProfileModal />
          <UpgradeModal />
          <PdfViewerModal />
        </AppProvider>
      </body>
    </html>
  );
}
