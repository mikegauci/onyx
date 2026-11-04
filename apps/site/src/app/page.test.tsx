import { render, screen } from "@testing-library/react";

import HomePage from "./page";

describe("Onyx Studio home page", () => {
  it("renders the brand, headline and a link to the platform", () => {
    render(<HomePage />);

    expect(screen.getByText("Onyx Studio")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to Onyx Platform" })).toHaveAttribute(
      "href",
      "http://localhost:3001",
    );
  });
});
