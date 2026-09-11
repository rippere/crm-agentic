import type { TourModule } from "../types";
import { module0Setup } from "./module-0-setup";
import { module1HomeBase } from "./module-1-home-base";

export { module0Setup } from "./module-0-setup";
export { module1HomeBase } from "./module-1-home-base";

/**
 * The full ordered onboarding curriculum. Module 0 runs on the pre-shell
 * onboarding wizard; Modules 1+ run inside the authenticated (app) shell.
 * Later modules (Contacts, Inbox & Calls, the Sales/PM tracks, the Level-2
 * capstone) are added here as they're authored.
 */
export const onboardingModules: TourModule[] = [module0Setup, module1HomeBase];

/**
 * Modules that run inside the (app) shell (dashboard, sidebar, ⌘K, etc.),
 * in the order they should be offered. Mounted by AppTour.
 */
export const appShellModules: TourModule[] = [module1HomeBase];
