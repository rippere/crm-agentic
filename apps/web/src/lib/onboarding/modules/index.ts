import type { TourModule } from "../types";
import { module0Setup } from "./module-0-setup";
import { module1HomeBase } from "./module-1-home-base";
import { module2Contacts } from "./module-2-contacts";
import { module3InboxCalls } from "./module-3-inbox-calls";
import { moduleS1Leads } from "./module-s1-leads";
import { moduleS2Pipeline } from "./module-s2-pipeline";
import { moduleS3Outreach } from "./module-s3-outreach";
import { moduleS4Reports } from "./module-s4-reports";
import { moduleP1Tasks } from "./module-p1-tasks";
import { moduleP2Projects } from "./module-p2-projects";

export { module0Setup } from "./module-0-setup";
export { module1HomeBase } from "./module-1-home-base";
export { module2Contacts } from "./module-2-contacts";
export { module3InboxCalls } from "./module-3-inbox-calls";
export { moduleS1Leads } from "./module-s1-leads";
export { moduleS2Pipeline } from "./module-s2-pipeline";
export { moduleS3Outreach } from "./module-s3-outreach";
export { moduleS4Reports } from "./module-s4-reports";
export { moduleP1Tasks } from "./module-p1-tasks";
export { moduleP2Projects } from "./module-p2-projects";

/**
 * The full ordered onboarding curriculum: shared core (0-3), then the
 * mode-specific tracks (Sales S1-S4, PM P1-P2). Track steps are mode-gated via
 * showForModes, so a Sales workspace runs S1-S4, a PM workspace runs P1-P2, and
 * Both runs all. The Level-2 capstone (C1-C3) is added here once authored.
 *
 * Module 0 runs on the pre-shell onboarding wizard; every other module runs
 * inside the authenticated (app) shell.
 */
export const onboardingModules: TourModule[] = [
  module0Setup,
  module1HomeBase,
  module2Contacts,
  module3InboxCalls,
  // Sales track (mode = sales | both)
  moduleS1Leads,
  moduleS2Pipeline,
  moduleS3Outreach,
  moduleS4Reports,
  // PM track (mode = pm | both)
  moduleP1Tasks,
  moduleP2Projects,
];

/**
 * Modules that run inside the (app) shell, in order (shared core → Sales track →
 * PM track). Mounted by AppTour, which offers them in sequence and auto-offers
 * each on first visit to its home route. Track modules are mode-gated by their
 * steps' showForModes; AppTour skips any module that has zero steps for the
 * current workspace mode, so a Sales workspace never sees PM modules and vice versa.
 */
export const appShellModules: TourModule[] = [
  module1HomeBase,
  module2Contacts,
  module3InboxCalls,
  moduleS1Leads,
  moduleS2Pipeline,
  moduleS3Outreach,
  moduleS4Reports,
  moduleP1Tasks,
  moduleP2Projects,
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
  [moduleS1Leads.id]: "/leads",
  [moduleS2Pipeline.id]: "/pipeline",
  [moduleS3Outreach.id]: "/sequences",
  [moduleS4Reports.id]: "/reports",
  [moduleP1Tasks.id]: "/tasks",
  [moduleP2Projects.id]: "/projects",
};
