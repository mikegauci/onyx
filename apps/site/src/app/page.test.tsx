import { render, screen, within } from "@testing-library/react";

import { industries } from "@/content/site";

import HomePage from "./page";

describe("Onyx Studio home page", () => {
  beforeEach(() => {
    render(<HomePage />);
  });

  it("renders one h1 and the main sections", () => {
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const name of [
      /every channel in/i,
      /four things/i,
      /businesses that live on enquiries/i,
      /first call to a system/i,
      /our own platform/i,
      "Frequently Asked Questions",
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

  it("shows every industry with its workflows", () => {
    expect(industries).toHaveLength(9);
    for (const industry of industries) {
      const card = screen.getByRole("article", { name: industry.name });
      expect(within(card).getAllByRole("listitem")).toHaveLength(industry.workflows.length);
    }
  });

  it("offers an email contact and in-page navigation targets", () => {
    const navigation = within(screen.getByRole("navigation", { name: "Main" }));
    const startProject = navigation.getByRole("link", { name: "Start a project" });
    const email = screen.getByRole("link", { name: "Email info@onyx.mt" });
    expect(startProject).toHaveAttribute("href", "#contact");
    expect(email).toHaveAttribute("href", "mailto:info@onyx.mt");
    expect(startProject.closest("[data-magnetic]")).toBeNull();
    expect(email.closest("[data-magnetic]")).toBeNull();
    for (const id of ["studio", "system", "industries", "process", "faq", "contact"]) {
      expect(document.getElementById(id)).not.toBeNull();
    }
  });

  it("links to the dedicated web design service from the services section", () => {
    const services = within(screen.getByRole("region", { name: /four things/i }));
    expect(
      services.getByRole("link", { name: /explore web design and development/i }),
    ).toHaveAttribute("href", "/services/web-design-development");
  });

  it("gives the headline a stable accessible name with the first rotating word", () => {
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Intelligence that works the front desk\./,
    );
  });

  it("renders the full statement text", () => {
    expect(document.getElementById("studio")?.textContent).toMatch(
      /stop slipping through the cracks/i,
    );
  });
});
