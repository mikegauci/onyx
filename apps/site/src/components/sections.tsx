import { Button } from "@onyx/ui/components/button";

import {
  faq,
  hero,
  industries,
  modules,
  nav,
  principles,
  process,
  queueMock,
  services,
  site,
  statement,
  system,
} from "@/content/site";

import { HandoffMark } from "./handoff-mark";
import { HeroCanvas } from "./hero-canvas";
import { IndustriesSlider } from "./industries-slider";
import { LiveQueue } from "./live-queue";
import { ProcessTimeline } from "./process-timeline";
import { RevealHeading } from "./reveal-heading";
import { ServicesList } from "./services-list";
import { RotatingWord } from "./rotating-word";
import { SystemDiagram } from "./system-diagram";
import { WordReveal } from "./word-reveal";

const container = "mx-auto w-full max-w-6xl px-5 sm:px-8";
const focusRing = "outline-none focus-visible:ring-[3px] focus-visible:ring-ring/60";

function StudioLogo() {
  return (
    <span className="inline-flex shrink-0 items-center gap-2.5 font-bold tracking-tight whitespace-nowrap text-[#f4eee6]">
      <HandoffMark className="size-5 shrink-0" />
      {site.name}
    </span>
  );
}

function Eyebrow({ children, center = false }: { children: React.ReactNode; center?: boolean }) {
  return (
    <p
      className={`text-muted-foreground flex items-center gap-3 font-mono text-xs tracking-[0.2em] uppercase ${center ? "justify-center" : ""}`}
    >
      <span aria-hidden className="bg-brand h-px w-8" />
      {children}
    </p>
  );
}

export function SiteNav({ platformUrl }: { platformUrl: string }) {
  return (
    <header className="bg-background/60 fixed inset-x-0 top-0 z-40 border-b border-white/[0.06] backdrop-blur-xl">
      <nav
        aria-label="Main"
        className={`${container} flex h-20 items-center justify-between gap-4`}
      >
        <a href="#top" className={`rounded-md text-lg ${focusRing}`}>
          <StudioLogo />
        </a>
        <ul className="hidden items-center gap-1 rounded-full border border-white/10 bg-black/40 px-2 py-1.5 text-sm backdrop-blur-xl md:flex">
          {nav.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                className={`text-muted-foreground hover:text-foreground rounded-full px-3 py-1.5 transition-colors ${focusRing}`}
              >
                <span className="link-draw">{item.label}</span>
              </a>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          <a
            href={platformUrl}
            className={`text-muted-foreground hover:text-foreground hidden rounded-full px-3 py-2 text-sm sm:inline ${focusRing}`}
          >
            Sign in
          </a>
          <span data-magnetic className="magnetic inline-block">
            <Button asChild size="sm" variant="brand" className="btn-sweep rounded-full px-4">
              <a href="#contact">Start a project</a>
            </Button>
          </span>
        </div>
      </nav>
    </header>
  );
}

function QueueMock({
  label = "Illustration of the Onyx Platform approval queue",
  onLoad = true,
}: {
  label?: string;
  /** Rows animate in on page load (hero) or as they scroll into view (further down). */
  onLoad?: boolean;
}) {
  const tone: Record<string, string> = {
    "Draft ready": "bg-success/15 text-success",
    Booked: "bg-info/15 text-info",
    "Needs approval": "bg-brand/15 text-brand",
  };
  return (
    <figure aria-label={label} className="w-full">
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/50 shadow-2xl backdrop-blur-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <span className="text-muted-foreground text-xs">Approvals</span>
          <span className="text-brand flex items-center gap-1.5 text-xs">
            <span className="live-dot bg-brand size-1.5 rounded-full" /> Live
          </span>
        </div>
        {onLoad ? (
          <LiveQueue />
        ) : (
          <ul className="divide-y divide-white/10">
            {queueMock.map((row, i) => (
              <li
                key={row.text}
                className={`${onLoad ? "reveal-row" : "reveal"} flex items-center justify-between gap-3 px-4 py-3.5`}
                style={onLoad ? { animationDelay: `${900 + i * 180}ms` } : undefined}
              >
                <span className="min-w-0">
                  <span className="text-muted-foreground block text-[11px]">{row.channel}</span>
                  <span className="block truncate text-sm">“{row.text}”</span>
                </span>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${tone[row.state]}`}
                >
                  {row.state}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <figcaption className="text-muted-foreground/70 mt-2 text-[11px]">
        Illustration with fictional enquiries.
      </figcaption>
    </figure>
  );
}

export function Hero() {
  return (
    <section id="top" className="relative flex min-h-[100svh] flex-col overflow-hidden">
      <div aria-hidden className="hero-fallback absolute inset-0" />
      <HeroCanvas />
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--background)]"
      />

      <div
        className={`${container} relative flex flex-1 flex-col justify-end pt-32 pb-14 sm:pb-20`}
      >
        <div className="hero-in" style={{ animationDelay: "50ms" }}>
          <Eyebrow>{hero.eyebrow}</Eyebrow>
        </div>
        <h1 className="mt-6 text-[clamp(3rem,10vw,8.5rem)] leading-[0.92] font-light tracking-[-0.04em]">
          <span className="sr-only">
            {hero.lines.join(" ")} {hero.rotating[0]}
          </span>
          <span aria-hidden>
            {hero.lines.map((line, i) => (
              <span key={line} className="line-mask block">
                <span className="line-in block" style={{ animationDelay: `${120 + i * 110}ms` }}>
                  {line}
                </span>
              </span>
            ))}
            <span className="line-mask block">
              <span
                className="line-in block"
                style={{ animationDelay: `${120 + hero.lines.length * 110}ms` }}
              >
                <RotatingWord words={hero.rotating} />
              </span>
            </span>
          </span>
        </h1>
        <div className="mt-10 grid items-end gap-10 lg:grid-cols-[1fr_22rem]">
          <div className="hero-in max-w-xl" style={{ animationDelay: "520ms" }}>
            <p className="text-foreground/75 text-lg text-pretty sm:text-xl">{hero.body}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <span data-magnetic className="magnetic inline-block">
                <Button
                  asChild
                  size="lg"
                  variant="brand"
                  className="btn-sweep h-12 rounded-full px-7"
                >
                  <a href="#contact">{hero.primary} →</a>
                </Button>
              </span>
              <Button
                asChild
                size="lg"
                variant="ghost"
                className="text-foreground h-12 rounded-full border border-white/15 px-7"
              >
                <a href="#system">{hero.secondary}</a>
              </Button>
            </div>
          </div>
          <div className="hero-in hidden lg:block" style={{ animationDelay: "700ms" }}>
            <QueueMock />
          </div>
        </div>
      </div>
    </section>
  );
}

export function Statement() {
  return (
    <section
      id="studio"
      aria-label="What we believe"
      className={`${container} scroll-mt-24 py-28 sm:py-40`}
    >
      <Eyebrow>Onyx Studio</Eyebrow>
      <WordReveal
        text={statement}
        className="mt-8 max-w-5xl text-[clamp(1.75rem,4.2vw,3.6rem)] leading-[1.12] font-light tracking-[-0.02em]"
      />
    </section>
  );
}

function SectionHead({
  id,
  eyebrow,
  title,
  body,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body?: string;
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_24rem] lg:items-end">
      <div>
        <Eyebrow>{eyebrow}</Eyebrow>
        <RevealHeading
          id={id}
          text={title}
          className="mt-6 text-[clamp(2.2rem,5vw,4.2rem)] leading-[1.02] font-light tracking-[-0.03em] text-balance"
        />
      </div>
      {body ? <p className="text-muted-foreground text-pretty">{body}</p> : null}
    </div>
  );
}

export function System() {
  return (
    <section
      id="system"
      aria-labelledby="system-title"
      className="relative scroll-mt-24 border-y border-white/10 py-28"
    >
      <div aria-hidden className="grid-bg pointer-events-none absolute inset-0" />
      <div className={`${container} relative`}>
        <SectionHead
          id="system-title"
          eyebrow={system.eyebrow}
          title={system.title}
          body={system.body}
        />
        <div className="mt-16">
          <SystemDiagram />
          <p className="text-muted-foreground/70 mt-3 text-[11px]">
            Examples are fictional. Prices, names and stock are for illustration only.
          </p>
        </div>
        <ul className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-3">
          {system.notes.map((n, i) => (
            <li key={n.title} className="spotlight bg-background relative p-7">
              <p className="text-brand font-mono text-xs">0{i + 1}</p>
              <h3 className="mt-4 text-xl font-light">{n.title}</h3>
              <p className="text-muted-foreground mt-2 text-sm">{n.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function Services() {
  return (
    <section
      id="services"
      aria-labelledby="services-title"
      className={`${container} scroll-mt-24 py-28`}
    >
      <SectionHead
        id="services-title"
        eyebrow="What we build"
        title="Four things, done properly."
        body="Most projects combine an assistant with a couple of automations. Websites and integrations come in when they unblock the rest."
      />
      <ServicesList services={services} />
    </section>
  );
}

export function Industries() {
  return (
    <section
      id="industries"
      aria-labelledby="industries-title"
      className="scroll-mt-24 pt-28 pb-12"
    >
      <div className={container}>
        <SectionHead
          id="industries-title"
          eyebrow="Industries"
          title="Built for businesses that live on enquiries."
          body="The platform is the same for everyone; the workflows are shaped to how your trade actually sells."
        />
      </div>
      <div className="mt-14">
        <IndustriesSlider industries={industries} />
      </div>
    </section>
  );
}

export function Process() {
  return (
    <section
      id="process"
      aria-labelledby="process-title"
      className={`${container} scroll-mt-24 py-28`}
    >
      <SectionHead
        id="process-title"
        eyebrow="How we work"
        title="From first call to a system your team trusts."
      />
      <ProcessTimeline steps={process} />
    </section>
  );
}

export function Platform({ platformUrl }: { platformUrl: string }) {
  return (
    <section
      id="platform"
      aria-labelledby="platform-title"
      className="relative scroll-mt-24 overflow-hidden border-t border-white/10 py-28"
    >
      <div
        aria-hidden
        className="platform-glow pointer-events-none absolute top-20 -right-40 size-[36rem] rounded-full"
      />
      <div className={`${container} relative`}>
        <div className="grid gap-14 lg:grid-cols-[1fr_24rem] lg:items-center">
          <div>
            <Eyebrow>Onyx Platform</Eyebrow>
            <RevealHeading
              id="platform-title"
              text="Our own platform, under every project."
              className="mt-6 text-[clamp(2.2rem,5vw,4.2rem)] leading-[1.02] font-light tracking-[-0.03em] text-balance"
            />
            <p className="text-muted-foreground mt-6 max-w-xl text-pretty">
              We don&apos;t stitch together a dozen tools for each client. Every business gets its
              own secure workspace on Onyx Platform and switches on the modules it needs.
            </p>
            <a
              href={platformUrl}
              className={`text-brand mt-8 inline-flex items-center gap-2 rounded-sm text-sm underline-offset-4 hover:underline ${focusRing}`}
            >
              Sign in to Onyx Platform →
            </a>
          </div>
          <QueueMock label="Example of the approval queue in Onyx Platform" onLoad={false} />
        </div>
        <ul className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((m) => (
            <li key={m.title} className="module-card spotlight group bg-background relative p-7">
              <span
                aria-hidden
                className="module-sheen pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
              />
              <h3 className="relative text-lg font-light">{m.title}</h3>
              <p className="text-muted-foreground relative mt-2 text-sm">{m.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function Principles() {
  const items = [...principles, ...principles];
  return (
    <section aria-label="Our principles" className="overflow-hidden border-y border-white/10 py-8">
      <ul className="marquee flex w-max text-[clamp(1.25rem,2.5vw,2rem)] font-light whitespace-nowrap">
        {items.map((p, i) => (
          <li
            key={i}
            aria-hidden={i >= principles.length}
            className="flex items-center gap-12 pr-12"
          >
            {p}
            <HandoffMark className="size-4 shrink-0" />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className={`${container} scroll-mt-24 py-28`}>
      <div className="grid gap-12 lg:grid-cols-[22rem_1fr]">
        <div>
          <Eyebrow>FAQ</Eyebrow>
          <RevealHeading
            id="faq-title"
            text="Fair questions."
            className="mt-6 text-4xl font-light tracking-tight"
          />
        </div>
        <div className="border-t border-white/10">
          {faq.map((f) => (
            <details key={f.q} className="faq group border-b border-white/10">
              <summary
                className={`flex cursor-pointer list-none items-center justify-between gap-6 rounded-sm py-6 text-lg font-light ${focusRing}`}
              >
                {f.q}
                <span
                  aria-hidden
                  className="text-brand text-2xl leading-none transition-transform duration-300 group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <p className="text-muted-foreground max-w-2xl pb-6">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Contact() {
  return (
    <section
      id="contact"
      aria-labelledby="contact-title"
      className="relative scroll-mt-24 overflow-hidden py-32 sm:py-44"
    >
      <div
        aria-hidden
        className="cta-glow pointer-events-none absolute inset-x-0 bottom-0 h-full"
      />
      <div className={`${container} relative text-center`}>
        <Eyebrow center>Start a project</Eyebrow>
        <RevealHeading
          id="contact-title"
          text="Tell us how your business runs today."
          className="mx-auto mt-8 max-w-4xl text-[clamp(2.5rem,7vw,6rem)] leading-[0.98] font-light tracking-[-0.04em] text-balance"
        />
        <p className="text-muted-foreground mx-auto mt-6 max-w-xl text-pretty">
          A short email is enough: what you sell, where enquiries come from and what takes your team
          the most time. We reply within two working days.
        </p>
        <div className="mt-10 flex justify-center">
          <span data-magnetic className="magnetic inline-block">
            <Button
              asChild
              size="lg"
              variant="brand"
              className="btn-sweep h-14 rounded-full px-9 text-base"
            >
              <a href={`mailto:${site.contactEmail}`}>Email {site.contactEmail}</a>
            </Button>
          </span>
        </div>
      </div>
    </section>
  );
}

export function SiteFooter({ platformUrl }: { platformUrl: string }) {
  const year = new Date().getFullYear();
  return (
    <footer data-cursor-glow className="relative overflow-hidden border-t border-white/10">
      <div className={`${container} grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4`}>
        <div className="lg:col-span-2">
          <p className="text-lg">
            <StudioLogo />
          </p>
          <p className="text-muted-foreground mt-3 max-w-sm text-sm">{site.description}</p>
        </div>
        <div>
          <h2 className="text-muted-foreground font-mono text-xs tracking-[0.2em] uppercase">
            Explore
          </h2>
          <ul className="mt-4 space-y-2 text-sm">
            {nav.map((item) => (
              <li key={item.href}>
                <a href={item.href} className={`hover:text-brand rounded-sm ${focusRing}`}>
                  <span className="link-draw">{item.label}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-muted-foreground font-mono text-xs tracking-[0.2em] uppercase">
            Contact
          </h2>
          <ul className="mt-4 space-y-2 text-sm">
            <li>
              <a
                href={`mailto:${site.contactEmail}`}
                className={`hover:text-brand rounded-sm ${focusRing}`}
              >
                <span className="link-draw">{site.contactEmail}</span>
              </a>
            </li>
            <li>
              <a href={platformUrl} className={`hover:text-brand rounded-sm ${focusRing}`}>
                <span className="link-draw">Onyx Platform sign-in</span>
              </a>
            </li>
          </ul>
          <address className="text-muted-foreground mt-4 text-sm not-italic">
            {site.legal.name}
            {site.legal.address.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
            <span className="block">VAT {site.legal.vat}</span>
          </address>
        </div>
      </div>
      <div
        className={`${container} text-muted-foreground flex flex-wrap justify-between gap-2 border-t border-white/10 py-6 text-xs`}
      >
        <p>
          © {year} {site.name}
        </p>
        <p>This site sets no cookies and runs no analytics.</p>
      </div>
      <p
        aria-hidden
        className="footer-word pointer-events-none -mb-[0.18em] text-center text-[15vw] leading-none font-bold tracking-[-0.06em] whitespace-nowrap select-none"
      >
        {site.name}
      </p>
    </footer>
  );
}
