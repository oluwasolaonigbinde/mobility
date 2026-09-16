import { redirect } from "next/navigation";

/** Compatibility route for the former public landing URL. */
export default function LandingCompatibilityPage() {
  redirect("/");
}
