import { fireEvent, render, screen } from "@testing-library/react";

import { Badge } from "./badge";
import { Button } from "./button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";
import { Input } from "./input";
import { Label } from "./label";
import { Separator } from "./separator";
import { Skeleton } from "./skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";

describe("base components", () => {
  it("renders a card with title and description", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Pending approvals</CardTitle>
          <CardDescription>Drafts waiting for staff review</CardDescription>
        </CardHeader>
        <CardContent>3</CardContent>
      </Card>,
    );

    expect(screen.getByText("Pending approvals")).toHaveAttribute("data-slot", "card-title");
    expect(screen.getByText("Drafts waiting for staff review").className).toContain(
      "text-muted-foreground",
    );
  });

  it("applies semantic badge variants", () => {
    render(<Badge variant="warning">Low stock</Badge>);

    const badge = screen.getByText("Low stock");
    expect(badge.className).toContain("bg-warning");
    expect(badge.className).toContain("text-warning-foreground");
  });

  it("applies the destructive button variant", () => {
    render(<Button variant="destructive">Reject</Button>);

    expect(screen.getByRole("button", { name: "Reject" }).className).toContain("bg-destructive");
  });

  it("associates a label with its input", () => {
    render(
      <>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" aria-invalid="true" />
      </>,
    );

    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("type", "email");
    expect(input).toHaveAttribute("data-slot", "input");
  });

  it("keeps decorative separators and skeletons out of the accessibility tree", () => {
    const { container } = render(
      <>
        <Separator />
        <Skeleton className="h-4 w-24" />
      </>,
    );

    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    expect(container.querySelector('[data-slot="skeleton"]')).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("shows tooltip content when the trigger receives focus", async () => {
    render(
      <Tooltip>
        <TooltipTrigger>Usage</TooltipTrigger>
        <TooltipContent>80% of this month's AI budget</TooltipContent>
      </Tooltip>,
    );

    fireEvent.focus(screen.getByRole("button", { name: "Usage" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("80% of this month's AI budget");
  });
});
