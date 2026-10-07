"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson } from "@/lib/files/onboarding-upload";
import type { components } from "@/lib/api/schema";

type Contact = components["schemas"]["DriverContactStateRead"];
type Challenge = components["schemas"]["DriverPhoneChallengeRead"];

export function PhoneVerification({ savedPhone }: { savedPhone: string }) {
  return <PhoneVerificationForPhone key={savedPhone} savedPhone={savedPhone} />;
}

function PhoneVerificationForPhone({ savedPhone }: { savedPhone: string }) {
  const router = useRouter();
  const [refreshing, startRefresh] = useTransition();
  const [contact, setContact] = useState<Contact>();
  const [challenge, setChallenge] = useState<Challenge>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const requestEpoch = useRef(0);
  const contactRead = useRef(0);
  useEffect(() => {
    let active = true;
    const read = ++contactRead.current;
    fetch("/api/driver/contact", { cache: "no-store" })
      .then(onboardingResponseJson<Contact>)
      .then((data) => {
        if (active && read === contactRead.current) setContact(data);
      })
      .catch(() => {
        if (active) setError("Couldn't load your phone status. Refresh to try again.");
      });
    return () => {
      active = false;
    };
  }, [savedPhone]);
  useEffect(
    () => () => {
      requestEpoch.current += 1;
    },
    [],
  );
  useEffect(() => {
    const hide = () => {
      if (document.visibilityState === "hidden") {
        requestEpoch.current += 1;
        setChallenge(undefined);
      }
    };
    document.addEventListener("visibilitychange", hide);
    return () => document.removeEventListener("visibilitychange", hide);
  }, []);
  useEffect(() => {
    if (!challenge) return;
    const deadline = new Date(challenge.expires_at).getTime();
    const timer = window.setTimeout(
      () => {
        setChallenge(undefined);
        setExpired(true);
      },
      Math.max(0, deadline - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [challenge]);

  async function checkStatus() {
    const read = ++contactRead.current;
    setError("");
    try {
      const next = await onboardingResponseJson<Contact>(
        await fetch("/api/driver/contact", { cache: "no-store" }),
      );
      if (read !== contactRead.current) return;
      setContact(next);
      if (
        next.phone?.verified ||
        next.challenge?.id !== challenge?.id ||
        next.challenge?.status !== "pending"
      ) {
        requestEpoch.current += 1;
        setChallenge(undefined);
      }
      router.refresh();
    } catch {
      setError("Couldn't check your phone status. Try again.");
    }
  }
  async function save(formData: FormData) {
    requestEpoch.current += 1;
    contactRead.current += 1;
    setBusy(true);
    setError("");
    setChallenge(undefined);
    setExpired(false);
    try {
      await onboardingResponseJson(
        await fetch("/api/driver/contact/phone", {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ phone: String(formData.get("phone") ?? "") }),
        }),
      );
      setContact(
        await onboardingResponseJson<Contact>(
          await fetch("/api/driver/contact", { cache: "no-store" }),
        ),
      );
      startRefresh(() => router.refresh());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your number. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function requestCode() {
    const epoch = requestEpoch.current;
    setBusy(true);
    setError("");
    setExpired(false);
    try {
      const issued = await onboardingResponseJson<Challenge>(
        await fetch("/api/driver/contact/phone-verification", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}",
        }),
      );
      if (epoch === requestEpoch.current) {
        setChallenge(issued);
        setContact((current) =>
          current
            ? {
                ...current,
                challenge: {
                  id: issued.id,
                  phone_version_id: issued.phone_version_id,
                  status: issued.status,
                  attempt_count: issued.attempt_count,
                  max_attempts: issued.max_attempts,
                  expires_at: issued.expires_at,
                  verified_at: issued.verified_at,
                },
              }
            : current,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't get a code. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel className="p-5">
      <h2 className="font-medium">Phone number</h2>
      <form action={save} className="mt-4 flex flex-col gap-3">
        <Field
          name="phone"
          label="Your phone number, including country code"
          type="tel"
          defaultValue={savedPhone}
          required
        />
        <Button type="submit" disabled={busy || refreshing}>
          {busy ? "Please wait…" : "Save phone number"}
        </Button>
      </form>
      {contact ? (
        <p className="mt-3 text-sm">
          {contact.phone?.verified
            ? "Your phone is verified."
            : contact.phone
              ? `${contact.phone.masked_phone} · Not verified yet`
              : contact.challenge
                ? "Not verified yet."
                : "Save your number before verifying it."}
        </p>
      ) : (
        <p className="text-muted mt-3 text-sm">Checking phone status…</p>
      )}
      {contact?.verification_available && !contact.phone?.verified ? (
        <Button className="mt-3" disabled={busy || refreshing || !savedPhone} onClick={requestCode}>
          Verify my phone
        </Button>
      ) : null}
      {expired || ["expired", "exhausted"].includes(contact?.challenge?.status ?? "") ? (
        <p className="text-muted mt-3 text-sm">
          Your previous code can no longer be used. Request another code.
        </p>
      ) : null}
      {contact && !contact.phone?.verified ? (
        <Button variant="ghost" className="mt-3" onClick={checkStatus}>
          Check verification status
        </Button>
      ) : null}
      {challenge ? (
        <div className="border-edge mt-4 rounded-lg border p-4" role="status">
          <p className="font-mono text-3xl tracking-widest">{challenge.code}</p>
          <p className="mt-3 text-sm">
            Send this code by WhatsApp or SMS to Terrax Media&apos;s number:{" "}
            <strong>{challenge.terrax_number}</strong>
          </p>
          <p className="text-muted mt-2 text-sm">
            Send it from your saved number. This code expires at{" "}
            {new Date(challenge.expires_at).toLocaleTimeString("en-NG", {
              timeZone: "Africa/Lagos",
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            Nigeria time (WAT). Terrax will record your message to verify your phone.
          </p>
          <Button
            variant="ghost"
            className="mt-3"
            onClick={() => {
              requestEpoch.current += 1;
              setChallenge(undefined);
              router.refresh();
            }}
          >
            Hide code
          </Button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-coral mt-3 text-sm">
          {error}
        </p>
      ) : null}
    </Panel>
  );
}
