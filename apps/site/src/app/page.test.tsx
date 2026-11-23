import { render, screen, within } from "@testing-library/react";

import HomePage from "./page";

describe("Onyx Studio home page", () => {
  beforeEach(() => {
    render(<HomePage />);
  });

  it("renders one h1 and every section", () => {
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const name of [
      /ships working systems/i,
      /first message to after-sale/i,
      /one workspace/i,
      /how your business runs/i,
    ]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("links every sign-in CTA to the platform", () => {
    const signIns = screen.getAllByRole("link", { name: /sign in/i });
    expect(signIns.length).toBeGreaterThanOrEqual(2);
    for (const link of signIns) expect(link).toHaveAttribute("href", "http://localhost:3001");
  });

  it("shows the five workflow steps in order", () => {
    const list = screen.getByRole("heading", { name: /first message/i }).closest("section")!;
    const steps = within(list)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(steps).toHaveLength(5);
    expect(steps[0]).toMatch(/Enquiry/);
    expect(steps[4]).toMatch(/Fulfilment/);
  });

  it("offers an email contact and in-page navigation targets", () => {
    expect(screen.getAllByRole("link", { name: /hello@onyx\.mt/i })[0]).toHaveAttribute(
      "href",
      "mailto:hello@onyx.mt",
    );
    for (const id of ["services", "how-it-works", "platform", "contact"]) {
      expect(document.getElementById(id)).not.toBeNull();
    }
  });
});
