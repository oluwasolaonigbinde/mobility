import { initializeClientMonitoring } from "@/lib/client-monitoring";
import { captureApplicationLink } from "@/lib/apply/application-link";
import {
  advertiserInviteLink,
  driverAccountSetupLink,
  passwordResetLink,
} from "@/lib/auth/invite-link";

if (
  captureApplicationLink() &&
  advertiserInviteLink.capture() &&
  passwordResetLink.capture() &&
  driverAccountSetupLink.capture()
)
  void initializeClientMonitoring();
