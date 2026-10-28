import type { Metadata } from "next";
import { VideoStreamProvider } from "@/features/video-stream";
import { Geist_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin", "vietnamese"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "VisionKit", template: "%s | VisionKit" },
  description: "Workspace quản lý dữ liệu và pipeline computer vision.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      className={`${manrope.variable} ${geistMono.variable} h-full font-sans antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <VideoStreamProvider><TooltipProvider>{children}</TooltipProvider></VideoStreamProvider>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
