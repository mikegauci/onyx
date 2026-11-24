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

    for (const name of ["Pantrila", "QTM Detailing", "MaltaGuns"]) {
      expect(screen.getByRole("heading", { name })).toBeVisible();
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
