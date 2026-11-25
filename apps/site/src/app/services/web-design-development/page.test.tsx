import { render, screen, within } from "@testing-library/react";
import { ReadonlyURLSearchParams, useSearchParams } from "next/navigation";

import WebDesignPage from "./page";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useSearchParams: vi.fn(),
}));

describe("web design service page", () => {
  beforeEach(() => vi.mocked(useSearchParams).mockReturnValue(new ReadonlyURLSearchParams()));
  it("publishes all VAT-inclusive packages, selected work and an enquiry form", () => {
    render(<WebDesignPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /web design and development.*in malta/i,
    );
    const packages = within(screen.getByRole("region", { name: "Website packages" }));
    expect(packages.getByText(/all prices include vat/i)).toBeVisible();
    for (const price of ["€300", "€750", "€1,500", "€3,500"]) {
      expect(packages.getByText(price)).toBeVisible();
    }
    expect(packages.getByText(/year including vat/i)).toBeVisible();

    const clients = within(screen.getByRole("region", { name: "Clients we worked with" }));
    for (const [name, technology, website, packageName] of [
      ["Pantrila", "LangGraph", "https://pantrila.com/", "Onyx"],
      ["QTM Detailing", "Motion", "https://www.qtmdetailing.mt/", "Gold"],
      ["MaltaGuns", "Tiptap", "https://www.maltaguns.com/", "Onyx"],
      ["Rotta", "Supabase", "https://rotta.mt/", "Gold"],
      ["Malta Detailing Academy", "Next.js", "https://mda.mt/", "Gold"],
      ["Jam Weddings", "Mailjet", "https://jam.mt/", "Bronze"],
      ["Thrust Studio", "Astro", "https://www.thruststudio.co/", "Bronze"],
      ["Beachaven", "React", "https://www.beachavencomplex.com/", "Silver"],
      ["Motor Element", "Shopify", "https://www.motorelement.com/", "Gold"],
    ] as const) {
      const project = within(clients.getByRole("article", { name }));
      expect(project.getByRole("heading", { name })).toBeVisible();
      expect(project.getByRole("img")).toBeVisible();
      expect(project.getByText(packageName, { exact: true })).toBeVisible();
      for (const label of [
        `${name} screenshot — visit website (opens in a new tab)`,
        `Visit website — ${name} (opens in a new tab)`,
      ]) {
        const link = project.getByRole("link", { name: label });
        expect(link).toHaveAttribute("href", website);
        expect(link).toHaveAttribute("target", "_blank");
        expect(link).toHaveAttribute("rel", "noopener noreferrer");
      }
      const technologies = within(project.getByRole("list", { name: `${name} technologies` }));
      expect(technologies.getByText(technology)).toBeVisible();
    }
    const form = within(screen.getByRole("form", { name: "Web project enquiry" }));
    expect(form.getByRole("textbox", { name: "Project brief" })).toBeRequired();
    expect(form.getByRole("button", { name: "Send enquiry" })).toBeEnabled();
  });

  it("links back to the homepage and uses Malta's phone number for all direct contact options", () => {
    render(<WebDesignPage />);

    expect(screen.getAllByRole("link", { name: /^Studio$/ })[0]).toHaveAttribute(
      "href",
      "/#studio",
    );
    for (const [label, href] of [
      [/email us/i, "mailto:info@onyx.mt"],
      [/call us/i, "tel:+35699256511"],
      [/text us/i, "sms:+35699256511"],
      [/whatsapp/i, "https://wa.me/35699256511"],
    ] as const) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it.each([
    ["facebook", "paid_social", "website_design_300", true],
    ["facebook", "organic", "website_design_300", false],
    ["instagram", "paid_social", "website_design_300", false],
    ["facebook", "paid_social", "unknown", false],
  ])(
    "attributes only the exact Facebook campaign (%s/%s/%s)",
    (source, medium, campaign, match) => {
      const query = new ReadonlyURLSearchParams({
        utm_source: source,
        utm_medium: medium,
        utm_campaign: campaign,
      });
      vi.mocked(useSearchParams).mockReturnValue(query);
      render(<WebDesignPage />);

      const form = screen.getByRole("form", { name: "Web project enquiry" });
      const data = new FormData(form as HTMLFormElement);
      expect(data.get("campaign")).toBe(match ? "website_design_300" : null);
      const whatsApp = new URL(
        screen.getByRole("link", { name: /whatsapp/i }).getAttribute("href")!,
      );
      expect(whatsApp.origin + whatsApp.pathname).toBe("https://wa.me/35699256511");
      expect(whatsApp.searchParams.get("text")).toBe(
        match
          ? "Hi Onyx Studio! I saw your Facebook ad for websites from €300 and would like to know more."
          : null,
      );
    },
  );
});
