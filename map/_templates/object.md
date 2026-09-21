---
type: object
cluster: {cluster}
universe: live        # live | leftover | ghost
status: stub          # stub | verified (date + commit + citations) | stale
entity: apps/api/app/models/{file}.py
---

# {Name}

{One sentence. If the product/UI word and the class/table name differ, say both.}

## Why this shape

{The load-bearing why, not a field tour.}

## Shape

- {keys, FKs, constraints, owning table}

Citations: `{path}:{line}`

## Connected to

- **owns:**
- **owned-by:**
- **joins:**
- **looks-like-but-is-not:**

## If you change this

- **Hits:** {first-order readers/writers, with path}
- **Does not hit:** {the obvious next noun that is the wrong one}

## Surfaces

| Surface | Role |
|---|---|
| {router / worker / web / agent} | {reads / writes} |

## See

- Source: `{path}`
