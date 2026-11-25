import { render, screen, within } from "@testing-library/react";

import sitemap from "@/app/sitemap";
import { newServiceLinks, servicePath } from "@/content/service-links";

import ServicePage, { generateMetadata, generateStaticParams } from "./page";

describe("Studio service pages", () => {
  it.each(newServiceLinks)(
    "links and accepts quote enquiries for $title",
    async ({ slug, title }) => {
      const props = { params: Promise.resolve({ service: slug }) };
      const path = servicePath(slug);
      expect(generateStaticParams()).toContainEqual({ service: slug });
      expect((await generateMetadata(props)).alternates?.canonical).toBe(path);
      expect(sitemap().find(({ url }) => new URL(url).pathname === path)).toBeDefined();

      render(await ServicePage(props));

      expect(screen.getByRole("heading", { level: 1 })).toBeVisible();
      expect(screen.getByRole("link", { name: "Get a quote" })).toHaveAttribute("href", "#enquiry");
      const form = within(screen.getByRole("form", { name: `${title} enquiry` }));
      expect(form.getByRole("textbox", { name: /phone number/i })).not.toBeRequired();
      expect(form.getByRole("textbox", { name: /project brief/i })).toBeRequired();
      expect(form.queryByRole("combobox", { name: /package/i })).not.toBeInTheDocument();
    },
  );

  it("uses the approved portfolio examples and links to the live projects", async () => {
    const app = render(
      await ServicePage({ params: Promise.resolve({ service: "app-development" }) }),
    );
    expect(screen.getByRole("heading", { name: "iOS and Android apps" })).toBeVisible();
    expect(screen.getByRole("link", { name: /visit Pantrila/i })).toHaveAttribute(
      "href",
      "https://pantrila.com/",
    );
    app.unmount();

    render(await ServicePage({ params: Promise.resolve({ service: "branding-graphic-design" }) }));
    expect(screen.getByRole("heading", { name: "Print design" })).toBeVisible();
    const work = within(screen.getByRole("region", { name: "Branding in use" }));
    for (const name of ["QTM Detailing", "MaltaGuns", "Pantrila"]) {
      expect(work.getByRole("heading", { name })).toBeVisible();
      expect(
        work.getByRole("link", { name: `Visit ${name} (opens in a new tab)` }),
      ).toHaveAttribute("target", "_blank");
    }
  });
});
