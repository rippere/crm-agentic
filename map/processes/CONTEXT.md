# processes/ — the verbs

The six real movements in the system. Each card: Input → Movement → Output, numbered steps with `path:line`, `consumes`/`produces` object links, and Hits/Does-not-hit.

| Verb | One line | Trigger |
|---|---|---|
| `auth` | OAuth-connect Gmail/Slack → encrypted Connector | on-demand (user) |
| `ingest` | connected inbox → deduped Message rows + enrichment | on-demand + provider webhooks (no beat) |
| `enrich-score` | score/enrich Contacts, Leads, Deals | beat (hourly/nightly) + API |
| `discover` | sweep a locality → LLM-scored Leads | on-demand (no beat) |
| `outreach-send` | enroll segment + tick sequence sends (HITL-gated) | beat (every 5 min) + launch API |
| `transcribe` | uploaded audio → Whisper + Claude → CallSummary | on-demand |

Only these six are followed. Do not invent a seventh. New verb = copy `../_templates/process.md`.
