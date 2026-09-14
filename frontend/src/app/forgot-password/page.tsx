import type { Metadata } from "next";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { PasswordResetRequestForm } from "./request-form";

export const metadata: Metadata = { title: "Reset password", referrer: "no-referrer" };

export default function ForgotPasswordPage() {
  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-sm">
        <p className="micro text-amber mb-3">Account recovery</p>
        <h1 className="font-display text-4xl font-semibold">Reset your password</h1>
        <p className="text-muted mt-3 mb-8 text-sm">
          Enter your account email. For privacy, the response is the same whether or not an eligible
          account exists.
        </p>
        <Panel className="p-6">
          <PasswordResetRequestForm />
        </Panel>
        <p className="mt-5 text-center text-sm">
          <Link href="/login" className="text-amber hover:text-amber-soft">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
