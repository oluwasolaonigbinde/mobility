"use client";

import { useId, useState } from "react";
import { STEPS } from "./content";

/**
 * "How it works" drawn as a route: a rail with one stop per step. Each step opens to show the brand side
 * and the driver side of the same moment, which is how the two-sided model is
 * actually experienced. One step is open at a time; the first starts open so
 * the section is never a wall of closed rows.
 */
export function Steps() {
  const [openIndex, setOpenIndex] = useState(0);
  const baseId = useId();

  return (
    <div className="tx-rail">
      {STEPS.map((step, index) => {
        const expanded = openIndex === index;
        const bodyId = `${baseId}-body-${index}`;
        const triggerId = `${baseId}-trigger-${index}`;

        return (
          <div className="tx-stop" key={step.n}>
            <h3>
              <button
                type="button"
                id={triggerId}
                className="tx-stop__trigger"
                aria-expanded={expanded}
                aria-controls={bodyId}
                onClick={() => setOpenIndex(expanded ? -1 : index)}
              >
                <span className="tx-micro tx-stop__n">{step.n}</span>
                <span className="tx-stop__title">{step.title}</span>
                <span className="tx-stop__chev" aria-hidden="true">
                  ▾
                </span>
              </button>
            </h3>

            {expanded ? (
              <div className="tx-stop__body" id={bodyId} role="region" aria-labelledby={triggerId}>
                <div className="tx-side">
                  <h4 className="tx-micro">Brand side</h4>
                  <p>{step.brand}</p>
                </div>
                <div className="tx-side tx-side--driver">
                  <h4 className="tx-micro">Driver side</h4>
                  <p>{step.driver}</p>
                </div>
                <p className="tx-micro tx-stop__source">
                  Confirmed in client answers {step.source}.
                </p>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
