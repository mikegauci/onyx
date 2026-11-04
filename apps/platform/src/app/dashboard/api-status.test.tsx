import { render, screen } from "@testing-library/react";

import { ApiStatus } from "./api-status";

describe("ApiStatus", () => {
  it("shows ok with service version", () => {
    render(<ApiStatus health={{ state: "ok", service: "onyx-api", version: "0.1.0" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("API: ok");
    expect(screen.getByRole("status")).toHaveTextContent("onyx-api v0.1.0");
  });

  it("shows unreachable with the reason", () => {
    render(<ApiStatus health={{ state: "unreachable", reason: "No response" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("API: unreachable");
    expect(screen.getByRole("status")).toHaveTextContent("No response");
  });
});
