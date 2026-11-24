import { render, screen, within } from "@testing-library/react";

import WebDesignPage from "./page";

describe("web design service page", () => {
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

    for (const [name, technology, website] of [
      ["Pantrila", "LangGraph", "https://pantrila.com/"],
      ["QTM Detailing", "Motion", "https://www.qtmdetailing.mt/"],
      ["MaltaGuns", "Tiptap", "https://www.maltaguns.com/"],
      ["Rotta", "Supabase", "https://rotta.mt/"],
      ["Malta Detailing Academy", "Next.js", "https://mda.mt/"],
      ["Jam Weddings", "Mailjet", "https://jam.mt/"],
      ["Thrust Studio", "Astro", "https://www.thruststudio.co/"],
      ["Beachaven", "React", "https://www.beachavencomplex.com/"],
      ["Motor Element", "Shopify", "https://www.motorelement.com/"],
    ] as const) {
      const project = within(screen.getByRole("article", { name }));
      expect(project.getByRole("heading", { name })).toBeVisible();
      expect(project.getByRole("img")).toBeVisible();
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
});
