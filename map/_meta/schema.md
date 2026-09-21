# Schema — the rules of this map

The closed set of node types in this System map, the labels they carry, and the naming they follow. When practice and this file disagree, reconcile the same day — schema drift is how maps rot.

## Node types

| `type:` | Lives at | Carries |
|---|---|---|
| object | `objects/<cluster>/<Name>.md` | one noun: a model/table. Shape, connections, change-impact. Source of truth is the code, never this card. |
| process | `processes/<verb>.md` | one movement: Input → Movement → Output, numbered steps with `path:line`, consumes/produces. |
| index | `objects/_index.md` | one line per noun (generated-by-hand-once, then kept in sync). Never a card body. |
| effects | `effects/CONTEXT.md` | change-impact catalog: "changing X → open these cards". Points; never copies waterfalls. |

## Labels that make it queryable

`type`, `cluster` (crm-core | comms | lead-engine | sequences | intelligence | tenancy), `universe`, `status`.
Process cards additionally carry `consumes:` / `produces:` — object names that draw the verb→noun graph.

### Universes

| `universe:` | Meaning |
|---|---|
| **live** | In force. Implement and cite against these. |
| **leftover** | Still present, no longer the main path. Touch only if that path is in scope. |
| **ghost** | Named or filed, not wired (stubs, dead types, docs of functions that do not exist). Do not implement against these. |

### Status

`verified` requires a date, a branch/commit, and `path:line` citations. `stale` is allowed and honest. A confident wrong citation is not.

## Naming

- Object cards: Title Case filename matching the product noun (`Deal.md`, `LeadSegment.md`). Declared here, held everywhere.
- Process cards: kebab-case verb (`enrich-score.md`).
- `_meta/` holds the rules (this file). `_index.md` and any generated map are rebuilt, never hand-drifted.
- **Entry twins (repo-specific):** this repo gitignores `CLAUDE.md` **and** `AGENTS.md` at every depth (secrets policy), so `map/CLAUDE.md`/`map/AGENTS.md` do not commit. `map/routing.md` is the **committed canonical entry**; edit it, then regenerate the local twins with `cp routing.md CLAUDE.md && cp routing.md AGENTS.md`. (Inverts ICM's usual "edit CLAUDE.md" rule for this repo only.)
