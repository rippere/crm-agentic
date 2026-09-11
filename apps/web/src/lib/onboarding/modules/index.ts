import type { TourModule } from "../types";
import { module0Setup } from "./module-0-setup";
import { module1HomeBase } from "./module-1-home-base";
import { module2Contacts } from "./module-2-contacts";
import { module3InboxCalls } from "./module-3-inbox-calls";

export { module0Setup } from "./module-0-setup";
export { module1HomeBase } from "./module-1-home-base";
export { module2Contacts } from "./module-2-contacts";
export { module3InboxCalls } from "./module-3-inbox-calls";

/**
 * The full ordered onboarding curriculum. Module 0 runs on the pre-shell
 * onboarding wizard; Modules 1+ run inside the authenticated (app) shell.
 * Later modules (the Sales/PM tracks, the Level-2 capstone) are added here as
 * they're authored.
 */
export const onboardingModules: TourModule[] = [
  module0Setup,
  module1HomeBase,
  module2Contacts,
  module3InboxCalls,
];

/**
 * Modules that run inside the (app) shell, in order. Mounted by AppTour, which
 * offers them in sequence and auto-offers each on first visit to its home route.
 */
export const appShellModules: TourModule[] = [
  module1HomeBase,
  module2Contacts,
  module3InboxCalls,
];

/**
 * The route each shell module is auto-offered on (first visit, if unseen). Used
 * by AppTour only — the engine stays route-agnostic. Modules that span pages are
 * keyed to their first page (the popover follows the user as they navigate).
 */
export const moduleHomeRoutes: Record<string, string> = {
  [module1HomeBase.id]: "/dashboard",
  [module2Contacts.id]: "/contacts",
  [module3InboxCalls.id]: "/inbox",
};
