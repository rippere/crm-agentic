<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Editing the backend? Read the system map first

`map/routing.md` is a walkable map of `apps/api` — every model (noun), every worker/router
movement (verb), and what a change hits — so you can edit one thing without slurping the tree.
Start there, open the one card you need, follow its `See` link to source. Two ghosts flagged
(DealHealthHistory, MetricTemplate); next-step debt is in `map/_meta/findings-next-steps.md`.
(`map/CLAUDE.md` and `map/AGENTS.md` are byte-identical local twins of `routing.md`, gitignored
by the repo's CLAUDE.md/AGENTS.md policy — `routing.md` is the committed canonical entry.)
