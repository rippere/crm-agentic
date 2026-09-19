# How to walk this map

One agent, cold, should answer "what is X" and "what else moves if I change X" from this file + the entry table + one card — without slurping `objects/`.

## The three node types

- **object** (`objects/<cluster>/<Name>.md`) — one noun (a model/table). Cite the model file; the code wins over any prose here.
- **process** (`processes/<verb>.md`) — one movement. Input → Movement → Output, numbered steps with `path:line`, `consumes`/`produces` links.
- **effects** (`effects/CONTEXT.md`) — "if you are changing X, open these cards." A catalog, not a copy of the waterfalls.

## Universes (repeat of the entry file, because it is load-bearing)

| universe | do what |
|---|---|
| live | implement and cite against it |
| leftover | touch only if that path is in scope |
| ghost | do NOT implement against it — decide to wire or drop first |

## Reading discipline

Open the entry file (`CLAUDE.md`) → the one card you need → its `See` source. That is 2-3 reads and ~2-8k tokens. Do NOT read the whole `objects/` tree; the `_index.md` and this catalog exist so you don't have to.

## Keeping it true

`status: verified` requires the date + branch/commit + `path:line` already on each card. When code and a card disagree, the code is right — fix the card the same day. `_index.md` is regenerated, not hand-drifted.
