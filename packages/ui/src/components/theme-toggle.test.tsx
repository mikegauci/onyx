import { fireEvent, render, screen } from "@testing-library/react";

import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./theme-toggle";

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
  });

  it("follows the system preference by default", () => {
    renderToggle();

    expect(screen.getByRole("group", { name: "Colour theme" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System theme" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("switches to dark, applies the class and remembers the choice", () => {
    renderToggle();

    fireEvent.click(screen.getByRole("button", { name: "Dark theme" }));

    expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("switches back to light", () => {
    renderToggle();

    fireEvent.click(screen.getByRole("button", { name: "Dark theme" }));
    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));

    expect(document.documentElement).not.toHaveClass("dark");
    expect(document.documentElement).toHaveClass("light");
  });
});
