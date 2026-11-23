import {
  Contact,
  Faq,
  Hero,
  Industries,
  Platform,
  Principles,
  Process,
  Services,
  SiteFooter,
  SiteNav,
  Statement,
  System,
} from "@/components/sections";
import { SmoothScroll } from "@/components/smooth-scroll";
import { siteEnv } from "@/lib/env";

export default function HomePage() {
  const { platformUrl } = siteEnv();

  return (
    <>
      <SmoothScroll />
      <a
        href="#main"
        className="bg-background focus:ring-ring/50 sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:ring-[3px]"
      >
        Skip to content
      </a>
      <SiteNav platformUrl={platformUrl} />
      <main id="main" className="overflow-x-clip">
        <Hero />
        <Statement />
        <System />
        <Services />
        <Industries />
        <Process />
        <Principles />
        <Platform platformUrl={platformUrl} />
        <Faq />
        <Contact />
      </main>
      <SiteFooter platformUrl={platformUrl} />
    </>
  );
}
