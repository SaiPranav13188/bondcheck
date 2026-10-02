"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, Upload, X } from "lucide-react";
import Logo from "./Logo";

const LINKS = [
  { href: "/companies", label: "Companies" },
  { href: "/ask", label: "Ask AI" },
  { href: "/drives", label: "Drives & alerts" },
  { href: "/how-it-works", label: "How it works" },
];

export default function Navbar() {
  const path = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [openFor, setOpenFor] = useState<string | null>(null);
  const open = openFor === path; // navigating closes the menu

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  // Pages whose hero is a dark photo: use light text until the bar turns opaque.
  const onDark = !scrolled && !open && ["/companies", "/upload", "/drives", "/how-it-works"].some((p) => path.startsWith(p));

  return (
    <header className={`sticky top-0 z-50 transition-all duration-300 ${scrolled ? "glass shadow-[0_8px_30px_-12px_rgba(15,23,42,0.18)]" : "bg-transparent"}`}>
      <nav className="container-x flex h-16 items-center justify-between gap-4">
        <Link href="/" aria-label="BondCheck home"><Logo light={onDark} /></Link>
        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => {
            const active = path.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href} className={`relative rounded-full px-3.5 py-2 text-sm font-medium transition-colors ${onDark ? (active ? "text-white" : "text-white/75 hover:text-white") : active ? "text-brand-700" : "text-ink-2 hover:text-ink"}`}>
                {active && <motion.span layoutId="nav-pill" className={`absolute inset-0 rounded-full ${onDark ? "bg-white/15 ring-1 ring-white/20" : "bg-brand-50 ring-1 ring-brand-100"}`} transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
                <span className="relative">{l.label}</span>
              </Link>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <Link href="/upload" className={`group hidden items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:-translate-y-0.5 hover:bg-brand-700 sm:inline-flex ${onDark ? "bg-white text-ink! hover:text-white!" : "bg-ink"}`}>
            <Upload className="h-4 w-4 transition group-hover:-translate-y-0.5" /> Upload letter
          </Link>
          <button onClick={() => setOpenFor(open ? null : path)} className={`grid h-10 w-10 place-items-center rounded-full md:hidden ${onDark ? "text-white" : "text-ink"}`} aria-label="Menu">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </nav>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-line bg-white md:hidden">
            <div className="container-x flex flex-col py-3">
              {[...LINKS, { href: "/upload", label: "Upload letter" }, { href: "/admin", label: "Moderator" }].map((l) => (
                <Link key={l.href} href={l.href} className="rounded-xl px-3 py-3 text-base font-medium text-ink-2 hover:bg-canvas">{l.label}</Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
