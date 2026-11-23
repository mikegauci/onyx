import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { industryChats, systemScenarios } from "@/content/demos";
import { industries, system } from "@/content/site";

import { IndustriesSlider } from "./industries-slider";
import { SystemDiagram } from "./system-diagram";

describe("demo content", () => {
  it("has a scenario for every channel, pointing at real outputs", () => {
    for (const input of system.inputs) {
      const sc = systemScenarios[input];
      expect(sc, input).toBeDefined();
      for (const o of sc!.outputs) expect(system.outputs).toContain(o);
    }
  });

  it("has a conversation for every industry", () => {
    for (const ind of industries) expect(industryChats[ind.slug], ind.slug).toBeDefined();
  });
});

describe("SystemDiagram", () => {
  it("plays a channel's example when chosen", async () => {
    render(<SystemDiagram />);
    const phoneButtons = within(screen.getByRole("list", { name: "Channels" }));
    await act(async () => {
      fireEvent.click(phoneButtons.getByRole("button", { name: "Email" }));
    });
    expect(await screen.findByText(systemScenarios.Email!.message)).toBeInTheDocument();
    expect(phoneButtons.getByRole("button", { name: "Email" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("IndustriesSlider", () => {
  it("opens an example conversation from the card button", async () => {
    render(<IndustriesSlider industries={industries} />);
    const card = screen.getByRole("article", { name: industries[0]!.name });
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "See a conversation" }));
    });
    expect(within(card).getByRole("list", { name: "Example conversation" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Back to overview" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
