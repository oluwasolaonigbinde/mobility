"use client";

import { useId, useRef, useState } from "react";
import { BRAND_POINTS, DRIVER_POINTS, MAILTO } from "./content";

type Side = "brands" | "drivers";

const PANELS = {
  brands: {
    label: "For brands",
    heading: "Put your brand where the city already is.",
    body: "Your campaign travels the routes people actually drive — junctions, estates, offices, markets — instead of waiting for them at one fixed board. Terrax Media handles the quotation, production, installation and permits; you approve the creative and read the results.",
    cta: { href: MAILTO.campaign, text: "Request a quotation" },
    points: BRAND_POINTS,
  },
  drivers: {
    label: "For drivers",
    heading: "Get paid for the driving you already do.",
    body: "If your car is registered in your name and passes the vehicle checks, approved advertising can be fitted to it and you earn for the campaign hours you actually work. No extra trips, no route instructions, no cost to you for production or installation.",
    cta: { href: MAILTO.driver, text: "Apply to drive" },
    points: DRIVER_POINTS,
  },
} as const;

const ORDER: Side[] = ["brands", "drivers"];

/**
 * The two-sided proposition, as a real ARIA tablist: roving tabindex plus
 * Arrow/Home/End key handling, one focusable tab at a time.
 */
export function Pathways() {
  const [side, setSide] = useState<Side>("brands");
  const baseId = useId();
  const tabsRef = useRef<Array<HTMLButtonElement | null>>([]);

  const tabId = (value: Side) => `${baseId}-tab-${value}`;
  const panelId = (value: Side) => `${baseId}-panel-${value}`;

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const current = ORDER.indexOf(side);
    let next = current;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = current + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = current - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = ORDER.length - 1;
    else return;

    event.preventDefault();
    const targetIndex = (next + ORDER.length) % ORDER.length;
    const target = ORDER[targetIndex] ?? "brands";
    setSide(target);
    tabsRef.current[targetIndex]?.focus();
  }

  const active = PANELS[side];

  return (
    <>
      <div className="tx-tabs" role="tablist" aria-label="Who you are" onKeyDown={onKeyDown}>
        {ORDER.map((value, index) => (
          <button
            key={value}
            ref={(node) => {
              tabsRef.current[index] = node;
            }}
            type="button"
            role="tab"
            id={tabId(value)}
            className={value === "drivers" ? "tx-tab tx-tab--driver" : "tx-tab"}
            aria-selected={side === value}
            aria-controls={panelId(value)}
            tabIndex={side === value ? 0 : -1}
            onClick={() => setSide(value)}
          >
            {PANELS[value].label}
          </button>
        ))}
      </div>

      <div
        className={side === "drivers" ? "tx-panel tx-panel--driver" : "tx-panel"}
        role="tabpanel"
        id={panelId(side)}
        aria-labelledby={tabId(side)}
        tabIndex={-1}
      >
        <div className="tx-panel__intro">
          <h3>{active.heading}</h3>
          <p>{active.body}</p>
          <a className="tx-btn tx-btn--green" href={active.cta.href}>
            {active.cta.text}
            <span className="tx-btn__arrow" aria-hidden="true">
              →
            </span>
          </a>
        </div>

        <ul className="tx-panel__points">
          {active.points.map((point, index) => (
            <li key={point.title} className="tx-point">
              <span className="tx-micro tx-point__n" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h4>{point.title}</h4>
              <p>{point.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
