import type { TourModule } from "../types";

/**
 * Module 2 — "Contacts" (shared core; builds on Module 1; all modes).
 *
 * Contacts are the foundation of everything else in NovaCRM, so this module has
 * the user create their real first contact, shows bulk CSV import + dedupe, and
 * introduces the contact AI in context: semantic ("AI") search, one-click
 * enrichment, and the AI contact brief. Real data — nothing here is a sandbox.
 *
 * Anchors are real elements on the Contacts page (data-tour selectors):
 *   - [data-tour="contacts-list"]      → the contacts table Card
 *   - [data-tour="contacts-add"]       → the "Add Contact" button
 *   - [data-tour="contacts-import"]    → the "Import CSV" button
 *   - [data-tour="contacts-ai-search"] → the semantic "AI Search" toggle
 *
 * Mode-awareness: Contacts is shared-core and visible in every mode, and each
 * step anchors a Contacts-page element (never a mode-gated nav item), so no
 * step can spotlight something a mode hides. Voice mirrors the Help page.
 */

/** DOM soft-check: is an element matching `selector` present? */
const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

/** DOM soft-check: does the contacts table have at least one data row? */
const hasContactRows = () => {
  if (typeof document === "undefined") return false;
  const table = document.querySelector('[data-tour="contacts-list"] table tbody');
  if (!table) return false;
  // A populated table has contact rows; the empty state renders a single
  // "No contacts…" row instead.
  return !/no contacts/i.test(table.textContent ?? "") && table.querySelectorAll("tr").length > 0;
};

export const module2Contacts: TourModule = {
  id: "module-2-contacts",
  title: "Contacts",
  description:
    "Build the foundation: add your first contact, import your book, and let the AI enrich and find people for you.",
  steps: [
    {
      id: "contacts-are-foundation",
      title: "Contacts are your foundation",
      whyThisExists:
        "Everything in NovaCRM hangs off contacts — deals, messages, calls, and briefs all attach to a person. Get your people in and the rest of the product lights up. This is the list you'll manage them from.",
      prerequisiteCheck: {
        label: "You've finished the home-base tour and opened Contacts.",
        verify: present('[data-tour="contacts-list"]'),
        nudge: "Open Contacts from the sidebar to follow along. (Finish Module 1 first if you skipped it.)",
      },
      anchor: { selector: '[data-tour="contacts-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Have a look at the table. On a new workspace it's empty — you're about to change that. Each contact gets an AI score (hot/warm/cold) and semantic tags automatically.",
      whatJustHappened:
        "This is your book of business. It stays in your workspace, isolated per tenant, and every column here is populated by the agents as data comes in.",
      forwardReference:
        "The contacts you add here become the people you build deals around (Pipeline, for Sales workspaces) and the subjects of AI briefs before meetings.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "add-first-contact",
      title: "Add your first contact",
      whyThisExists:
        "The fastest way to feel the product is to put a real person in it. Add someone you actually work with — this isn't a demo record.",
      prerequisiteCheck: {
        label: "You're on the Contacts page.",
        verify: present('[data-tour="contacts-add"]'),
      },
      anchor: { selector: '[data-tour="contacts-add"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click Add Contact and fill in a name (email and company help the AI). Save, and you'll see them appear in the table with a score and tags within moments.",
      whatJustHappened:
        "You just created a real contact. The scoring and tagging agents pick it up immediately — no manual categorizing.",
      forwardReference:
        "This person is now searchable from ⌘K and ready to attach to a deal or a call.",
      checkpoint: {
        confirmLabel: "Added one → Next",
        verify: hasContactRows,
        nudge: "Don't see a contact in the table yet — add one when you're ready. You can continue either way.",
      },
    },
    {
      id: "import-and-dedupe",
      title: "Import your whole book",
      whyThisExists:
        "Adding people one at a time is fine to start, but you probably have a list already. Import a CSV and NovaCRM ingests everyone at once — and flags likely duplicates so your list stays clean.",
      prerequisiteCheck: {
        label: "The Import control is in your toolbar.",
        verify: present('[data-tour="contacts-import"]'),
      },
      anchor: { selector: '[data-tour="contacts-import"]', placement: "bottom", padding: 6 },
      actionGuidance:
        "Click Import CSV and pick a file with columns name, email, company, role, status. You'll get a summary of how many imported and how many were skipped.",
      whatJustHappened:
        "Your book is in. NovaCRM watches for near-duplicate people and surfaces suggested merges up top, so importing never leaves you with two of the same contact.",
      forwardReference:
        "A clean, deduped contact list is what makes semantic search and briefs accurate — which is the next thing to try.",
      checkpoint: { confirmLabel: "Makes sense → Next" },
    },
    {
      id: "semantic-search",
      title: "Find anyone by meaning",
      whyThisExists:
        "Once you have a real book, finding the right person matters. NovaCRM's AI Search understands intent, not just keywords — describe who you're looking for in plain language and it finds them by meaning.",
      prerequisiteCheck: {
        label: "The AI Search toggle is in your toolbar.",
        verify: present('[data-tour="contacts-ai-search"]'),
      },
      anchor: { selector: '[data-tour="contacts-ai-search"]', placement: "bottom", padding: 6 },
      actionGuidance:
        "Toggle AI Search on, then type something like \"fintech exec with funding needs.\" Matches are ranked by semantic similarity, powered by embeddings of every contact.",
      whatJustHappened:
        "You just searched by meaning instead of exact text. The same embeddings drive tagging and the recommendations you'll see elsewhere.",
      forwardReference:
        "Semantic understanding of your contacts is what lets Nova (⌘K) answer questions like \"who are my warmest prospects in healthcare?\"",
      checkpoint: { confirmLabel: "Nice → Next" },
      aiTip: {
        text: "AI tip: AI Search runs on all-MiniLM-L6-v2 embeddings of your contacts. If results look thin, hit Embed All once to index everyone, then search by intent — \"decision-maker who went quiet,\" \"warm intro from a customer,\" and so on.",
        prompt: "Explain semantic (vector) contact search and give two example intent-based queries grounded in the user's book.",
      },
    },
    {
      id: "enrich-and-brief",
      title: "Let AI fill in the gaps",
      whyThisExists:
        "A bare name isn't worth much. Enrichment and briefs turn a thin contact into a rich one — so you walk into every conversation prepared, without doing the research yourself.",
      prerequisiteCheck: {
        label: "You have at least one contact to work with.",
        verify: present('[data-tour="contacts-list"]'),
      },
      anchor: { selector: '[data-tour="contacts-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Open any contact to see their detail panel. Use Enrich to have the AI fill in role, company, and signals, and generate a contact brief — a short, meeting-ready summary of who they are and where things stand.",
      whatJustHappened:
        "You've met the contact AI: enrichment, semantic search, and briefs. Together they keep your book rich and searchable with almost no manual upkeep.",
      forwardReference:
        "These enriched contacts feed straight into the next steps — Pipeline and Deals for Sales, and the messages and calls that attach to each person, which is Module 3.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: Enrich fills missing fields and refreshes the AI score from live signals; the contact brief (in the detail panel) is a one-paragraph pre-meeting summary you can pull up right before a call. Both run on Claude and never train on your data.",
        prompt: "Introduce one-click contact enrichment and the AI contact brief; note they run on Claude and are privacy-safe.",
      },
    },
  ],
};
