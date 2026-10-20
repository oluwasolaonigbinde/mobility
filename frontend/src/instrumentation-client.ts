import { initializeClientMonitoring } from "@/lib/client-monitoring";
import { captureApplicationLink } from "@/lib/apply/application-link";

if (captureApplicationLink()) void initializeClientMonitoring();
