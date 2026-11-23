import { Button } from "@onyx/ui/components/button";
import { ThemeToggle } from "@onyx/ui/components/theme-toggle";

import { modules, nav, queueMock, services, site, steps, trust } from "@/content/site";

const container = "mx-auto w-full max-w-6xl px-5 sm:px-8";

function Wordmark() {
  return (
    <a
      href="#top"
      className="focus-visible:ring-ring/50 flex items-center gap-2 rounded-md font-semibold tracking-tight outline-none focus-visible:ring-[3px]"
    >
      <span aria-hidden className="bg-brand inline-block size-3 rotate-45 rounded-[3px]" />
      {site.name}
    </a>
  );
}

export function SiteNav({ platformUrl }: { platformUrl: string }) {
  return (
    <header className="sticky top-3 z-40 px-3 sm:top-4">
      <nav
        aria-label="Main"
        className="bg-background/70 supports-[backdrop-filter]:bg-background/55 mx-auto flex max-w-5xl items-center justify-between gap-3 rounded-full border py-2 pr-2 pl-5 shadow-sm backdrop-blur-xl"
      >
        <Wordmark />
        <ul className="hidden items-center gap-1 text-sm md:flex">
          {nav.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 rounded-md px-3 py-2 outline-none focus-visible:ring-[3px]"
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild size="sm" className="rounded-full">
            <a href={platformUrl}>Sign in</a>
          </Button>
        </div>
      </nav>
    </header>
  );
}

function QueueMock() {
  const tone: Record<string, string> = {
    "Draft ready": "bg-success/15 text-success",
    "Needs approval": "bg-brand/15 text-brand",
    Escalated: "bg-warning/15 text-warning",
  };
  return (
    <figure
      className="relative mx-auto mt-16 w-full max-w-4xl"
      aria-label="Illustration of the Onyx Platform approval queue"
    >
      <div
        aria-hidden
        className="hero-glow pointer-events-none absolute inset-x-0 -top-16 bottom-0 sm:-inset-x-10"
      />
      <div className="bg-card/80 relative overflow-hidden rounded-xl border text-left shadow-2xl backdrop-blur">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <span aria-hidden className="bg-muted-foreground/30 size-2.5 rounded-full" />
          <span aria-hidden className="bg-muted-foreground/30 size-2.5 rounded-full" />
          <span aria-hidden className="bg-muted-foreground/30 size-2.5 rounded-full" />
          <span className="text-muted-foreground ml-3 text-xs">Approvals · 3 waiting</span>
        </div>
        <ul className="divide-y">
          {queueMock.map((row, i) => (
            <li
              key={row.text}
              className="reveal-row grid grid-cols-[1fr_auto] items-center gap-3 px-4 py-4 sm:grid-cols-[7rem_1fr_auto] sm:px-6"
              style={{ animationDelay: `${300 + i * 150}ms` }}
            >
              <span className="text-muted-foreground hidden text-xs sm:block">{row.channel}</span>
              <span className="min-w-0">
                <span className="text-muted-foreground block text-xs sm:hidden">
                  {row.channel} · {row.who}
                </span>
                <span className="text-muted-foreground hidden text-xs sm:block">{row.who}</span>
                <span className="block truncate text-sm">“{row.text}”</span>
              </span>
              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tone[row.state]}`}>
                {row.state}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <figcaption className="text-muted-foreground mt-3 text-center text-xs">
        Illustration with fictional enquiries.
      </figcaption>
    </figure>
  );
}

export function Hero() {
  return (
    <section id="top" className={`${container} pt-20 pb-24 text-center sm:pt-28`}>
      <p className="hero-in text-muted-foreground mb-5 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs">
        <span aria-hidden className="bg-brand size-1.5 rounded-full" />
        Websites, automation and AI for businesses in {site.location}
      </p>
      <h1 className="mx-auto max-w-4xl text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
        {site.tagline}
      </h1>
      <p
        className="hero-in text-muted-foreground mx-auto mt-6 max-w-2xl text-lg text-pretty"
        style={{ animationDelay: "120ms" }}
      >
        {site.description}
      </p>
      <div
        className="hero-in mt-9 flex flex-wrap items-center justify-center gap-3"
        style={{ animationDelay: "220ms" }}
      >
        <Button asChild size="lg" variant="brand">
          <a href="#contact">Talk to us</a>
        </Button>
        <Button asChild size="lg" variant="outline">
          <a href="#how-it-works">See how it works</a>
        </Button>
      </div>
      <QueueMock />
    </section>
  );
}

function SectionHeading({
  id,
  eyebrow,
  title,
  body,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="mx-auto mb-12 max-w-2xl text-center">
      <p className="text-brand mb-3 text-sm font-medium">{eyebrow}</p>
      <h2 id={id} className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      <p className="text-muted-foreground mt-4 text-pretty">{body}</p>
    </div>
  );
}

export function Services() {
  return (
    <section
      id="services"
      aria-labelledby="services-title"
      className={`${container} scroll-mt-24 py-24`}
    >
      <SectionHeading
        id="services-title"
        eyebrow="Onyx Studio"
        title="A small studio that ships working systems"
        body="We start from how your business actually runs, then build what saves your team time. Most projects pair a service with Onyx Platform."
      />
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {services.map((s) => (
          <li key={s.title} className="reveal bg-card rounded-xl border p-6">
            <h3 className="font-medium">{s.title}</h3>
            <p className="text-muted-foreground mt-2 text-sm">{s.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-title"
      className="bg-muted/40 scroll-mt-24 border-y py-24"
    >
      <div className={container}>
        <SectionHeading
          id="how-title"
          eyebrow="How it works"
          title="From first message to after-sale, with people in control"
          body="The assistant does the legwork. Your staff decide what gets sent, and the platform keeps every step on record."
        />
        <ol className="relative grid gap-6 md:grid-cols-5 md:gap-4">
          <span
            aria-hidden
            className="beam-track absolute top-5 right-[10%] left-[10%] hidden h-px md:block"
          >
            <span className="beam" />
          </span>
          {steps.map((step, i) => (
            <li
              key={step.title}
              className="reveal relative flex gap-4 md:flex-col md:items-center md:text-center"
            >
              <span className="bg-background text-brand relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full border font-mono text-sm">
                {i + 1}
              </span>
              <span>
                <span className="block font-medium">{step.title}</span>
                <span className="text-muted-foreground mt-1 block text-sm">{step.body}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function Platform({ platformUrl }: { platformUrl: string }) {
  return (
    <section
      id="platform"
      aria-labelledby="platform-title"
      className={`${container} scroll-mt-24 py-24`}
    >
      <SectionHeading
        id="platform-title"
        eyebrow="Onyx Platform"
        title="One workspace for enquiries, customers and stock"
        body="Onyx Platform is our multi-business software. Each business gets its own workspace and turns on the modules it needs."
      />
      <ul className="grid gap-4 md:grid-cols-3">
        {modules.map((m) => (
          <li
            key={m.title}
            className={`reveal group bg-card relative overflow-hidden rounded-xl border p-6 ${m.wide ? "md:col-span-2" : ""}`}
          >
            <span
              aria-hidden
              className="card-sheen pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            />
            <h3 className="relative font-medium">{m.title}</h3>
            <p className="text-muted-foreground relative mt-2 text-sm">{m.body}</p>
          </li>
        ))}
      </ul>
      <ul
        aria-label="Our commitments"
        className="text-muted-foreground mt-12 flex flex-wrap justify-center gap-x-8 gap-y-3 text-sm"
      >
        {trust.map((t) => (
          <li key={t} className="flex items-center gap-2">
            <svg
              aria-hidden
              viewBox="0 0 16 16"
              className="text-success size-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {t}
          </li>
        ))}
      </ul>
      <p className="mt-10 text-center text-sm">
        Already a customer?{" "}
        <a
          href={platformUrl}
          className="text-brand focus-visible:ring-ring/50 rounded-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
        >
          Sign in to Onyx Platform
        </a>
      </p>
    </section>
  );
}

export function Contact() {
  return (
    <section id="contact" aria-labelledby="contact-title" className="scroll-mt-24 px-3 pb-24">
      <div className="cta-band relative mx-auto max-w-6xl overflow-hidden rounded-2xl border px-6 py-20 text-center">
        <h2
          id="contact-title"
          className="relative text-3xl font-semibold tracking-tight text-balance sm:text-4xl"
        >
          Tell us how your business runs today
        </h2>
        <p className="text-muted-foreground relative mx-auto mt-4 max-w-xl text-pretty">
          A short email is enough: what you sell, where enquiries come from, and what takes your
          team the most time. We reply within two working days.
        </p>
        <div className="relative mt-8 flex justify-center">
          <Button asChild size="lg" variant="brand">
            <a href={`mailto:${site.contactEmail}`}>Email {site.contactEmail}</a>
          </Button>
        </div>
      </div>
    </section>
  );
}

export function SiteFooter({ platformUrl }: { platformUrl: string }) {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t">
      <div className={`${container} grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4`}>
        <div className="lg:col-span-2">
          <Wordmark />
          <p className="text-muted-foreground mt-3 max-w-sm text-sm">{site.description}</p>
        </div>
        <div>
          <h2 className="text-sm font-medium">Explore</h2>
          <ul className="text-muted-foreground mt-3 space-y-2 text-sm">
            {nav.map((item) => (
              <li key={item.href}>
                <a href={item.href} className="hover:text-foreground">
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-medium">Company</h2>
          <ul className="text-muted-foreground mt-3 space-y-2 text-sm">
            <li>
              <a href={`mailto:${site.contactEmail}`} className="hover:text-foreground">
                {site.contactEmail}
              </a>
            </li>
            <li>
              <a href={platformUrl} className="hover:text-foreground">
                Onyx Platform sign-in
              </a>
            </li>
            <li>{site.location}</li>
          </ul>
        </div>
      </div>
      <div
        className={`${container} text-muted-foreground flex flex-wrap justify-between gap-2 border-t py-6 text-xs`}
      >
        <p>
          © {year} {site.name}
        </p>
        <p>This site sets no cookies and runs no analytics.</p>
      </div>
      <p
        aria-hidden
        className="text-foreground/[0.04] pointer-events-none overflow-hidden text-center text-[22vw] leading-none font-semibold tracking-tighter select-none"
      >
        onyx
      </p>
    </footer>
  );
}
