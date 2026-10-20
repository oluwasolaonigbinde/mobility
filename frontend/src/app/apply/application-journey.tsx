"use client";
import { useEffect, useRef, useState } from "react";
import { Steps } from "@/components/ui/steps";
import { Panel } from "@/components/ui/panel";
import { takeApplicationLink } from "@/lib/apply/application-link";
import { validContinuation } from "@/lib/apply/continuation";
import type { ApplicationContinuation } from "@/lib/api/audit-batch2";
import { DriverApplicationForms, NewCodePanel } from "./application-forms";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

export type ApplicationCar = { vehicle_id: string; plate_number: string; status: string };
type Continuation = Pick<ApplicationContinuation, "step" | "state" | "changes_reason"> & {
  token: string;
  cars: ApplicationCar[];
  generation: number;
};
export function ApplicationJourney({ requestedStep }: { requestedStep?: string }) {
  const [current, setCurrent] = useState<Continuation>();
  const [checking, setChecking] = useState(requestedStep === "details" || requestedStep === "car");
  const [failed, setFailed] = useState(false);
  const link = useRef<ReturnType<typeof takeApplicationLink>>(null);
  const generation = useRef(0);
  useEffect(() => {
    let controller: AbortController | undefined;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    async function continueLink(fromHash = false) {
      const next = takeApplicationLink();
      if (next || fromHash) link.current = next;
      const selected = ++generation.current;
      controller?.abort();
      clearTimeout(expiry);
      setCurrent(undefined);
      const token = link.current?.token;
      if (!token || link.current?.invalid) {
        setChecking(false);
        setFailed(
          Boolean(link.current?.invalid || requestedStep === "details" || requestedStep === "car"),
        );
        return;
      }
      controller = new AbortController();
      const signal = controller.signal;
      setChecking(true);
      setFailed(false);
      try {
        const response = await fetch("/api/apply/onboarding/continue", {
          method: "POST",
          headers: { "content-type": "application/json" },
          cache: "no-store",
          signal,
          body: JSON.stringify({ application_access_token: token }),
        });
        if (!response.ok) throw new Error("unavailable");
        const data = validContinuation(await response.json());
        if (!data) throw new Error("unavailable");
        let cars: ApplicationCar[] = [];
        if (data.state === "car_needed" || data.state === "car_changes_needed") {
          const carResponse = await fetch("/api/apply/onboarding/vehicles", {
            method: "POST",
            headers: { "content-type": "application/json" },
            cache: "no-store",
            signal,
            body: JSON.stringify({ application_access_token: token }),
          });
          if (!carResponse.ok) throw new Error("unavailable");
          const carData = (await carResponse.json()) as { items?: ApplicationCar[] };
          if (!Array.isArray(carData.items)) throw new Error("unavailable");
          cars = carData.items;
        }
        if (generation.current !== selected || signal.aborted) return;
        if (Date.parse(data.expires_at) <= Date.now()) throw new Error("unavailable");
        setCurrent({
          token,
          step: data.step,
          state: data.state,
          changes_reason: data.changes_reason,
          cars,
          generation: selected,
        });
        setChecking(false);
        expiry = setTimeout(
          () => {
            link.current = null;
            setCurrent(undefined);
            setFailed(true);
          },
          Math.max(0, Date.parse(data.expires_at) - Date.now()),
        );
      } catch {
        if (generation.current !== selected || signal.aborted) return;
        setChecking(false);
        setFailed(true);
      }
    }
    void continueLink();
    const hashChanged = () => {
      void continueLink(true);
    };
    window.addEventListener("hashchange", hashChanged);
    return () => {
      generation.current++;
      controller?.abort();
      clearTimeout(expiry);
      window.removeEventListener("hashchange", hashChanged);
    };
  }, [requestedStep]);
  const step = current?.step ?? "apply";
  return (
    <>
      <Steps
        label="Application steps"
        columns
        items={[
          {
            key: "apply",
            title: "Apply",
            detail: "Your contact details",
            current: step === "apply",
          },
          {
            key: "details",
            title: "Your details",
            detail: "Your ID and bank details",
            current: step === "details",
          },
          {
            key: "car",
            title: "Your car",
            detail: "Your car and its papers",
            current: step === "car",
          },
        ]}
      />
      {checking ? (
        <Panel className="mt-5 p-6">
          <p role="status">Opening your application…</p>
        </Panel>
      ) : current ? (
        current.state.endsWith("_in_review") ? (
          <Panel className="mt-5 p-6">
            <h2 className="font-display text-xl font-semibold">
              {current.step === "details"
                ? "We’re checking your details"
                : "We’re checking your car"}
            </h2>
            <p className="text-ink mt-2 text-base">We’ll email you when we’ve finished.</p>
          </Panel>
        ) : (
          <>
            {current.changes_reason ? (
              <Panel className="mt-5 p-6">
                <h2 className="font-display text-xl font-semibold">Please make a change</h2>
                <p className="text-ink mt-2 text-base">{current.changes_reason}</p>
              </Panel>
            ) : null}
            {current.step === "details" ? (
              <PersonPayeeForm key={current.generation} accessToken={current.token} />
            ) : (
              <VehicleForm
                key={current.generation}
                accessToken={current.token}
                cars={current.cars}
              />
            )}
          </>
        )
      ) : failed ? (
        <Panel className="mt-5 p-6">
          <p role="alert">
            This application link isn’t available. Open the link in your latest email, or ask for a
            new one below.
          </p>
          <p className="text-muted mt-2 text-sm">
            If you’ve been approved, check your email for your account set-up link.
          </p>
          <NewCodePanel />
        </Panel>
      ) : (
        <DriverApplicationForms />
      )}
    </>
  );
}
