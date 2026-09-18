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
import { moduleC1Goals } from "./module-c1-goals";
import { moduleC2NovaDeep } from "./module-c2-nova-deep";
import { moduleC3Nexus } from "./module-c3-nexus";

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
export { moduleC1Goals } from "./module-c1-goals";
export { moduleC2NovaDeep } from "./module-c2-nova-deep";
export { moduleC3Nexus } from "./module-c3-nexus";

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
  // Level-2 capstone (all modes; unlocked later, NOT part of first-run)
  moduleC1Goals,
  moduleC2NovaDeep,
  moduleC3Nexus,
];

/**
 * Level-2 capstone — the "unlocked later" set (spec §2 level-2 split). These are
 * DELIBERATELY excluded from `appShellModules` and `moduleHomeRoutes`, so AppTour
 * never auto-offers them on first run and the first-run launcher chain never
 * reaches them. They are surfaced only once the user has data and habits, via a
 * separate advanced-tour entry point that starts these by id. All modes.
 */
export const capstoneModules: TourModule[] = [
  moduleC1Goals,
  moduleC2NovaDeep,
  moduleC3Nexus,
];

/**
 * Activation core — the ONLY modules auto-offered on first run. Deliberately
 * short (Home base + Contacts ≈ 9 steps, on top of Module 0's ~6) so a brand-new
 * user reaches a real payoff — a named workspace, having met Nova, and their
 * first contacts in — in one sitting. Everything heavier is deferred to
 * `level2Modules` and reached from the launcher AFTER the core is done, so
 * first-run completion isn't gated on a 30-step marathon or on data the user
 * doesn't have yet (a synced inbox, a recorded call).
 */
export const activationModules: TourModule[] = [
  module1HomeBase,
  module2Contacts,
];

/**
 * Level-2 first-run — the rest of the fundamentals (Inbox & Calls, then the
 * Sales/PM tracks). NOT auto-offered: these are surfaced by the launcher once
 * the activation core is complete, in order, one at a time ("Continue tour").
 * Module 3 lives here on purpose — its AI payoff needs a populated inbox/call,
 * which a day-one user rarely has, so it waits until the user has data. Track
 * modules are mode-gated by their steps' showForModes.
 */
export const level2Modules: TourModule[] = [
  module3InboxCalls,
  moduleS1Leads,
  moduleS2Pipeline,
  moduleS3Outreach,
  moduleS4Reports,
  moduleP1Tasks,
  moduleP2Projects,
];

/**
 * Every shell module in first-run order (activation core → level-2). Used as the
 * curriculum denominator for the progress indicator and by any consumer that
 * needs the full first-run set. AppTour auto-offers ONLY `activationModules`;
 * `level2Modules` and the capstone are launcher-gated.
 */
export const appShellModules: TourModule[] = [
  ...activationModules,
  ...level2Modules,
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
