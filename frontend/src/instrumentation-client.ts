import { initializeClientMonitoring } from "@/lib/client-monitoring";
import { captureApplicationLink } from "@/lib/apply/application-link";
import { captureAdvertiserInviteLink } from "@/lib/auth/invite-link";

if (captureApplicationLink() && captureAdvertiserInviteLink()) void initializeClientMonitoring();
