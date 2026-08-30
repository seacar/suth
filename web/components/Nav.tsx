"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { HeaderProjectSelect } from "@/components/HeaderProjectSelect";

const WORKFLOW_LINKS = [
  { href: "/run", label: "Run" },
  { href: "/history", label: "History" },
  { href: "/compare", label: "Compare" },
];

const CONFIG_LINKS = [
  { href: "/projects", label: "Projects" },
  { href: "/personas", label: "Personas" },
];

function NavLinks({
  pathname,
  onNavigate,
}: {
  pathname: string | null;
  onNavigate?: () => void;
}) {
  return (
    <>
      {WORKFLOW_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={pathname?.startsWith(link.href) ? "nav-link active" : "nav-link"}
          onClick={onNavigate}
        >
          {link.label}
        </Link>
      ))}
      <span className="nav-pipe" aria-hidden="true" />
      {CONFIG_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={pathname?.startsWith(link.href) ? "nav-link active" : "nav-link"}
          onClick={onNavigate}
        >
          {link.label}
        </Link>
      ))}
    </>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/run" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark" aria-hidden="true">
            S
          </span>
          <span className="brand-name">suth</span>
        </Link>

        <nav className="topbar-nav" aria-label="Primary">
          <NavLinks pathname={pathname} />
        </nav>

        <div className="topbar-end">
          <HeaderProjectSelect />
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      {open ? (
        <nav id="mobile-nav" className="mobile-nav" aria-label="Primary">
          <NavLinks pathname={pathname} onNavigate={() => setOpen(false)} />
        </nav>
      ) : null}
    </header>
  );
}
