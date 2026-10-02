import Link from "next/link";
import { Scale, ShieldCheck } from "lucide-react";
import Logo from "./Logo";

export default function Footer() {
  return (
    <footer className="relative mt-24 overflow-hidden bg-ink text-slate-300">
      <div className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[60rem] -translate-x-1/2 rounded-full bg-brand-600/25 blur-3xl" />
      <div className="container-x relative grid gap-10 py-14 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="space-y-4">
          <Logo light />
          <p className="max-w-sm text-sm leading-relaxed text-slate-400">
            Seven AI agents turn anonymously uploaded offer letters into a verified, evidence-backed database of job-bond terms, so freshers know before they sign.
          </p>
          <p className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1.5 text-xs text-emerald-300 ring-1 ring-white/10">
            <ShieldCheck className="h-3.5 w-3.5" /> Documents are processed in memory and never stored
          </p>
        </div>
        <FooterCol title="Explore" links={[["/companies", "Companies"], ["/drives", "Upcoming drives"], ["/ask", "Ask the AI"], ["/upload", "Upload a letter"]]} />
        <FooterCol title="Project" links={[["/how-it-works", "How the agents work"], ["/how-it-works#evaluation", "Evaluation results"], ["/how-it-works#guardrails", "Guardrails"], ["/admin", "Moderator console"]]} />
        <div className="space-y-3 text-sm">
          <p className="font-semibold text-white">Not legal advice</p>
          <p className="flex gap-2 text-slate-400"><Scale className="mt-0.5 h-4 w-4 shrink-0" /> Terms are shown as reported by uploaded letters and public sources, not as claims about any company.</p>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="container-x flex flex-col gap-2 py-5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} BondCheck · Demo data is synthetic; all companies shown are fictional.</p>
          <p>Photos from Unsplash.</p>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="font-semibold text-white">{title}</p>
      <ul className="space-y-2">
        {links.map(([href, label]) => (
          <li key={href}><Link href={href} className="text-slate-400 transition hover:text-white">{label}</Link></li>
        ))}
      </ul>
    </div>
  );
}
