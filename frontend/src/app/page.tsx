import { redirect } from "next/navigation";
import { getCurrentUser, roleHome } from "@/lib/auth/current-user";

export default async function RootPage() {
  const me = await getCurrentUser();
  redirect(me ? roleHome(me.user.role) : "/login");
}
