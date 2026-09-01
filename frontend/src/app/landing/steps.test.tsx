import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Steps } from "./steps";
import { STEPS } from "./content";

describe("Steps", () => {
  it("renders every step with the first one open", () => {
    render(<Steps />);

    const triggers = screen.getAllByRole("button");
    expect(triggers).toHaveLength(STEPS.length);
    expect(triggers[0]).toHaveAttribute("aria-expanded", "true");
    expect(triggers[1]).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByRole("region")).toHaveLength(1);
  });

  it("shows both sides of the open step", () => {
    render(<Steps />);
    const region = screen.getByRole("region");
    expect(region).toHaveTextContent("Brand side");
    expect(region).toHaveTextContent("Driver side");
    expect(region).toHaveTextContent(STEPS[0]!.brand);
    expect(region).toHaveTextContent(STEPS[0]!.driver);
  });

  it("opens another step and closes the previous one", async () => {
    const user = userEvent.setup();
    render(<Steps />);

    await user.click(screen.getByRole("button", { name: new RegExp(STEPS[2]!.title, "i") }));

    const triggers = screen.getAllByRole("button");
    expect(triggers[0]).toHaveAttribute("aria-expanded", "false");
    expect(triggers[2]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region")).toHaveTextContent(STEPS[2]!.driver);
  });

  it("collapses the open step when its own trigger is pressed again", async () => {
    const user = userEvent.setup();
    render(<Steps />);

    await user.click(screen.getByRole("button", { name: new RegExp(STEPS[0]!.title, "i") }));

    expect(screen.getAllByRole("button")[0]).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("wires each trigger to the panel it controls", async () => {
    const user = userEvent.setup();
    render(<Steps />);

    await user.click(screen.getByRole("button", { name: new RegExp(STEPS[1]!.title, "i") }));

    const trigger = screen.getAllByRole("button")[1]!;
    const region = screen.getByRole("region");
    expect(region.id).toBe(trigger.getAttribute("aria-controls"));
    expect(region.getAttribute("aria-labelledby")).toBe(trigger.id);
  });
});
