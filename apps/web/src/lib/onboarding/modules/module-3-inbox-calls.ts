import type { TourModule } from "../types";

/**
 * Module 3 — "Inbox & Calls" (shared core; builds on Module 2; all modes).
 *
 * With contacts in place, this module connects the conversations around them:
 * the synced inbox (Gmail/Slack, connected back in Module 0) and call
 * recordings. It introduces the message + call AI in context: sentiment,
 * auto-extraction of tasks and contacts from messages, and call summaries with
 * action items.
 *
 * The module spans two pages. Steps 1-2 anchor the Inbox; steps 3-4 anchor
 * Calls, and their guidance tells the user to open Calls from the sidebar. The
 * engine polls for anchors, so each step's spotlight attaches when the user is
 * on the matching page and the popover centers otherwise — the non-blocking
 * coach-mark model.
 *
 * Anchors (data-tour selectors on the real pages):
 *   - [data-tour="inbox-list"]    → the message list Card (Inbox)
 *   - [data-tour="inbox-triage"]  → the "AI Triage" button (Inbox)
 *   - [data-tour="calls-upload"]  → the "Log a Call" button (Calls)
 *   - [data-tour="calls-list"]    → the call list Card (Calls)
 *
 * Mode-awareness: Inbox and Calls are shared-core (visible in every mode) and
 * every step anchors a page element, never a mode-gated nav item. Voice mirrors
 * the Help page.
 */

/** DOM soft-check: is an element matching `selector` present? */
const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const module3InboxCalls: TourModule = {
  id: "module-3-inbox-calls",
  title: "Inbox & Calls",
  description:
    "Connect the conversations: your synced inbox and your call recordings, with AI that turns both into tasks and summaries.",
  steps: [
    {
      id: "inbox-synced",
      title: "Your inbox, already synced",
      whyThisExists:
        "The tools you connected during setup feed this inbox automatically. Gmail and Slack messages land here tied to the right contacts — so the conversations and the people they're about live in one place.",
      prerequisiteCheck: {
        label: "You've added contacts and opened the Inbox.",
        verify: present('[data-tour="inbox-list"]'),
        nudge: "Open Inbox from the sidebar to follow along. (Connect Gmail/Slack in Connectors if you skipped it in setup.)",
      },
      anchor: { selector: '[data-tour="inbox-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Scan the list. Open any message to see its detail panel — NovaCRM has already read it and attached it to the matching contact.",
      whatJustHappened:
        "Your messages are ingesting on their own. Nothing to file or forward — connected tools stream straight into your workspace.",
      forwardReference:
        "Every message here is raw material for the AI in the next step, and for the contact records you built in Module 2.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "inbox-ai",
      title: "AI triages your inbox",
      whyThisExists:
        "An inbox is only useful if it turns into action. NovaCRM reads every message for sentiment, then pulls out the tasks and contacts hiding inside — so nothing important slips through.",
      prerequisiteCheck: {
        label: "The AI Triage control is in your inbox toolbar.",
        verify: present('[data-tour="inbox-triage"]'),
      },
      anchor: { selector: '[data-tour="inbox-triage"]', placement: "bottom", padding: 6 },
      actionGuidance:
        "Click AI Triage. NovaCRM scores each message's sentiment, flags what needs a reply, and auto-extracts action items and any new contacts it finds.",
      whatJustHappened:
        "Your inbox just became a to-do list. A cooling relationship shows up as negative sentiment on the contact, and extracted tasks are ready to work.",
      forwardReference:
        "Those extracted tasks surface in Tasks (in PM and Both workspaces) and against the contact they came from — the same tasks you'll manage later.",
      checkpoint: {
        confirmLabel: "Triaged → Next",
        verify: present('[data-tour="inbox-triage"]'),
      },
      aiTip: {
        text: "AI tip: triage runs sentiment on every message and extracts tasks + contacts using Claude. Draft reply (in a message's detail panel) writes a context-aware response you approve before anything sends — high-stakes actions always wait for you.",
        prompt: "Explain inbox sentiment scoring and auto-extraction of tasks/contacts; note draft-reply is human-approved before sending.",
      },
    },
    {
      id: "log-a-call",
      title: "Log a call",
      whyThisExists:
        "The most valuable context often lives in a conversation nobody wrote down. Upload a recording and NovaCRM transcribes it and mines it for you — so a call becomes searchable, structured data.",
      prerequisiteCheck: {
        label: "Open Calls from the sidebar to reach this step.",
        verify: present('[data-tour="calls-upload"]'),
        nudge: "Head to Calls in the sidebar (Intelligence group) to try this — the popover will follow you there.",
      },
      anchor: { selector: '[data-tour="calls-upload"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click Log a Call and upload an audio file (add a title and attendees to help). It's transcribed with Whisper, then analyzed — you'll see it move from transcribing to done.",
      whatJustHappened:
        "You turned a recording into a record. The transcript is searchable and attached to your workspace like any other data.",
      forwardReference:
        "Once transcription finishes, the AI summary and action items appear — that's the last step.",
      checkpoint: {
        confirmLabel: "Uploaded / got it → Next",
        verify: present('[data-tour="calls-list"]'),
        nudge: "No call yet — that's fine, you can upload one anytime. Continuing.",
      },
    },
    {
      id: "call-summary",
      title: "AI summarizes the call",
      whyThisExists:
        "You shouldn't have to re-listen to an hour-long call to remember what was agreed. NovaCRM extracts the summary, the action items, and the sentiment so the outcome is captured the moment the call is processed.",
      prerequisiteCheck: {
        label: "You're on the Calls page.",
        verify: present('[data-tour="calls-list"]'),
      },
      anchor: { selector: '[data-tour="calls-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Open a processed call to see its transcript, a concise AI summary, and extracted action items — objections, commitments, and next steps pulled out for you.",
      whatJustHappened:
        "You've met the conversation AI: inbox sentiment and extraction, plus call summaries with action items. Your messages and calls now turn themselves into structured, actionable records.",
      forwardReference:
        "Action items from calls become tasks against the right contact — feeding the same Tasks view your triaged inbox does. From here, your workspace runs on real data.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: calls are transcribed with Whisper and summarized with Claude — summary, action items, and sentiment. Action items can become tasks on the linked contact, so a call turns directly into follow-up without you typing it up.",
        prompt: "Explain the call summary + action-item extraction (Whisper + Claude) and how action items become tasks on a contact.",
      },
    },
  ],
};
