import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ApiProvider } from "@/lib/api-context";
import { ProjectProvider } from "@/lib/project-context";
import { Nav } from "@/components/Nav";
import { GlobalEvents } from "@/components/GlobalEvents";

const sans = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
});

const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata = {
  title: "SUTH — Synthetic User Test Harness",
  description: "Drive a real browser with an LLM-backed persona and score the transcript.",
};

// Without this, Next statically prerenders this layout at build time — and
// specific.hcl env vars (API_URL included) aren't available during the
// build phase, only once the container is actually running. Forcing dynamic
// rendering makes the process.env.API_URL read below happen per-request.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Read at request time (Server Component), not baked in at build — build-time
  // code can't see specific.hcl env vars (DATABASE_URL, API_URL, ...).
  const apiBaseUrl = process.env.API_URL ?? "http://localhost:3001";

  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <ApiProvider apiBaseUrl={apiBaseUrl}>
          <ProjectProvider>
            <GlobalEvents />
            <Nav />
            <main className="page">{children}</main>
          </ProjectProvider>
        </ApiProvider>
      </body>
    </html>
  );
}
