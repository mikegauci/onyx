import { render, screen } from "@testing-library/react";

import { Button } from "./button";

describe("Button", () => {
  it("renders an accessible button with default variant classes", () => {
    render(<Button>Save</Button>);

    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("data-slot", "button");
    expect(button.className).toContain("bg-primary");
  });

  it("renders its child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="/dashboard">Open</a>
      </Button>,
    );

    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/dashboard");
  });
});
