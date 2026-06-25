# Evidence — delete_contact orphans linked data (refutes GDPR "deletion" claim)

**Verdict: PROVEN** — Deleting a contact does NOT delete that contact's linked data.
Deals, messages, tasks, and call_summaries SURVIVE the delete with `contact_id` set to
NULL (orphaned). The `delete_contact` docstring ("Delete a contact and all cascade-linked
records") is false.

Date: 2026-06-03
Target DB: dev docker stack `crm-local-pg` (PostgreSQL 16.13, port 5433), DB `crmdb`.
Code under review: `/tmp/crm-signup-fix`

---

## 1. The handler — what it actually does

`/tmp/crm-signup-fix/apps/api/app/routers/contacts.py`, `delete_contact` (lines 435-463):

```python
@router.delete("/workspaces/{workspace_id}/contacts/{contact_id}", status_code=204)
async def delete_contact(...):
    """Delete a contact and all cascade-linked records."""   # <-- CLAIM (false)
    ...
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact_name = contact.name or str(contact_id)
    await db.delete(contact)          # <-- ONLY deletes the contacts row
    event = ActivityEvent(... type="contact_deleted" ...)
    db.add(event)
    await db.commit()
```

The handler issues exactly one delete: `await db.delete(contact)`. It never touches deals,
messages, tasks, or call_summaries. What happens to the children is therefore decided
entirely by (a) the SQLAlchemy ORM relationship cascade settings and (b) the database FK
`ON DELETE` rules. Both are examined below; both say SET NULL.

## 2. SQLAlchemy ORM relationships — NO cascade configured

`/tmp/crm-signup-fix/apps/api/app/models/contact.py` (lines 34-37):

```python
workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="contacts")
deals:    Mapped[list["Deal"]]    = relationship("Deal",    back_populates="contact")
messages: Mapped[list["Message"]] = relationship("Message", back_populates="contact")
tasks:    Mapped[list["Task"]]    = relationship("Task",    back_populates="contact")
```

None of `deals`/`messages`/`tasks` specify `cascade=` or `passive_deletes=`. SQLAlchemy's
DEFAULT relationship cascade is `"save-update, merge"` — it does NOT include `delete`.
Consequence: on `db.delete(contact)`, the ORM's default behavior for a one-to-many with a
nullable FK is to NULL out the child FK (dependent rows are disassociated, not deleted).
The child rows are not loaded-and-deleted because no delete cascade is set. The DB-level
`ON DELETE SET NULL` then governs the actual outcome at COMMIT.

Child-side relationships confirm the same (no cascade): deal.py:33, message.py:30, task.py:32.

## 3. Database FK ON DELETE rules — all SET NULL (declared)

Migration `/tmp/crm-signup-fix/apps/api/migrations/001_unified_schema.sql`:

| child table | line | constraint |
|-------------|------|-----------|
| deals       | 49   | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |
| messages    | 112  | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |
| tasks       | 122  | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |

Docker init `/tmp/crm-signup-fix/apps/api/migrations/init_docker.sql` (this is what the dev
DB is built from) — same, plus call_summaries:

| child table     | line | constraint |
|-----------------|------|-----------|
| deals           | 56   | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |
| messages        | 121  | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |
| tasks           | 131  | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |
| call_summaries  | 163  | `contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL` |

No child FK to `contacts(id)` uses `ON DELETE CASCADE` or `ON DELETE RESTRICT`/`NO ACTION`.
So: children are neither deleted (no CASCADE) nor do they block the delete (no RESTRICT).
They are orphaned (SET NULL).

## 4. Live DB constraints — ground truth from the running database

Queried the actual running container (not the migration files):

```
$ docker exec -e PGPASSWORD=devpass crm-local-pg psql -U postgres -d crmdb -c "
SELECT tc.table_name AS child_table, kcu.column_name AS fk_column, rc.delete_rule
FROM information_schema.referential_constraints rc
JOIN information_schema.table_constraints tc  ON tc.constraint_name  = rc.constraint_name
JOIN information_schema.key_column_usage  kcu ON kcu.constraint_name = rc.constraint_name
JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = rc.constraint_name
WHERE ccu.table_name = 'contacts' ORDER BY tc.table_name;"

  child_table   | fk_column  | delete_rule
----------------+------------+-------------
 call_summaries | contact_id | SET NULL
 deals          | contact_id | SET NULL
 messages       | contact_id | SET NULL
 tasks          | contact_id | SET NULL
(4 rows)
```

Every child FK referencing `contacts` resolves to `delete_rule = SET NULL` in the live DB.

## 5. End-to-end reproduction (seed -> delete -> observe -> cleanup)

Ran the exact DB operation `delete_contact` performs (`DELETE FROM contacts WHERE id=...`)
against a namespaced AUDIT-TEST workspace seeded with one linked deal, message, task, and
call. Full transcript:

```
BEGIN
INSERT 0 1   (workspace AUDIT-TEST)
INSERT 0 1   (contact   ...0c0d17)
INSERT 0 1   (deal      ...0d0d17 -> contact ...0c0d17)
INSERT 0 1   (message   ...0e0d17 -> contact ...0c0d17)
INSERT 0 1   (task      ...0f0d17 -> contact ...0c0d17)
INSERT 0 1   (call      ...10d017 -> contact ...0c0d17)

=== BEFORE DELETE: children linked to contact ===
  kind   |                  id                  |              contact_id
---------+--------------------------------------+--------------------------------------
 deal    | 00000000-0000-0000-0000-0000000d0d17 | 00000000-0000-0000-0000-0000000c0d17
 message | 00000000-0000-0000-0000-0000000e0d17 | 00000000-0000-0000-0000-0000000c0d17
 task    | 00000000-0000-0000-0000-0000000f0d17 | 00000000-0000-0000-0000-0000000c0d17
 call    | 00000000-0000-0000-0000-00000010d017 | 00000000-0000-0000-0000-0000000c0d17
(4 rows)

DELETE 1     <-- the contact delete

=== AFTER DELETE: contact row count (expect 0) ===
 contact_rows_remaining
------------------------
                      0          <-- contact IS gone

=== AFTER DELETE: do child rows still exist, and is contact_id NULL? ===
  kind   |                  id                  | contact_id | orphaned
---------+--------------------------------------+------------+----------
 deal    | 00000000-0000-0000-0000-0000000d0d17 |            | t
 message | 00000000-0000-0000-0000-0000000e0d17 |            | t
 task    | 00000000-0000-0000-0000-0000000f0d17 |            | t
 call    | 00000000-0000-0000-0000-00000010d017 |            | t
(4 rows)        <-- ALL 4 children STILL EXIST, contact_id NULLed, orphaned=true

DELETE 1     <-- cleanup: delete TEST workspace (CASCADE on workspace_id)

=== CLEANUP VERIFY: all TEST rows gone (expect all 0) ===
 ws | deals | msgs | tasks | calls
----+-------+------+-------+-------
  0 |     0 |    0 |     0 |     0
COMMIT
```

Interpretation:
- The contact row is deleted (`contact_rows_remaining = 0`).
- The deal, message, task, and call rows are NOT deleted — they remain, now with
  `contact_id = NULL` (`orphaned = t`). This is data orphaning, the opposite of the
  documented "delete all cascade-linked records."

## 6. Cleanup confirmation — no test data left behind

```
$ docker exec ... psql ... -c "<global sweep for AUDIT-TEST artifacts>"
workspaces|0
contacts|0
deals|0
messages|0
tasks|0
call_summaries|0
```

All AUDIT-TEST artifacts removed. The reproduction also ran inside a single transaction and
deleted the parent TEST workspace (which CASCADEs on `workspace_id`) before COMMIT, so the
orphaned children created for the test were themselves cleaned up via the workspace FK.

---

## Conclusion

PROVEN by both static analysis (ORM has no delete cascade; every contact FK is
`ON DELETE SET NULL` in migrations and in the live DB) and by observed end-to-end
reproduction: deleting a contact removes only the contact row and leaves its deals,
messages, tasks, and call summaries in place as orphaned records with `contact_id = NULL`.

GDPR / "right to erasure" impact: a contact-deletion request does NOT erase the personal
data carried in the linked child rows. The deal's `contact_name`/`company`, the message's
`sender_email` + `body_plain` (email content), and task titles/descriptions persist after
the contact is "deleted." These rows are merely disassociated (FK NULLed), not removed —
so the personal data survives. The handler's docstring asserting cascade deletion is
materially incorrect.

### Severity: HIGH
- Confidentiality/compliance: residual PII (email addresses, email bodies, names, company,
  call transcripts/summaries) persists after a deletion the system reports as successful
  (HTTP 204). This refutes the GDPR-deletion claim.
- Not a blocker / not data-loss to the app; it is a compliance + data-hygiene defect
  (silent orphaning + false "deleted" signal).

### Remediation
Pick one, consistently across schema + ORM:
1. **Intended cascade delete** (if children should die with the contact): change the FKs to
   `ON DELETE CASCADE` in a migration AND set `cascade="all, delete-orphan", passive_deletes=True`
   on the `Contact.deals/messages/tasks` (and add a call_summaries relationship) — then the DB
   removes the children. Make the docstring true.
2. **Application-level erasure** (recommended for GDPR): in `delete_contact`, before
   `db.delete(contact)`, explicitly delete or scrub PII on the linked deals/messages/
   tasks/call_summaries for that `contact_id` within the same transaction, rather than
   relying on SET NULL. SET NULL silently retains the personal data and must not be used for
   a "deletion" endpoint.
3. At minimum, stop advertising cascade deletion: fix the docstring and document that
   deleting a contact orphans (does not erase) linked records.

---

## APPENDIX — Independent refutation attempt (2026-06-03, verifier pass)

A second agent re-ran every load-bearing check trying to REFUTE this finding. Result:
**finding UPHELD.** All evidence reproduces independently. Refutation angles tested and
closed below.

### A1. Re-read static evidence — confirmed verbatim
- Handler `contacts.py:435-463`: single `await db.delete(contact)` at line 454; false
  docstring at line 442. Confirmed.
- ORM `contact.py:34-37`: `deals`/`messages`/`tasks` relationships have NO `cascade=` and
  NO `passive_deletes=`. Confirmed.
- Child-model FKs all `ondelete="SET NULL"`: `deal.py:19`, `message.py:22`, `task.py:19`,
  `call_summary.py:16`. Confirmed (claim only listed migrations; the ORM column defs agree).

### A2. Refutation angle "a later migration ALTERs the FK to CASCADE" — CLOSED
Grepped every `*.sql` for any `ALTER`/`DROP CONSTRAINT`/`CASCADE`/`RESTRICT` touching
`contact_id`. Every single `contact_id` reference across all 13 migration files
(000–011 + init_docker) is `ON DELETE SET NULL`. No later override exists. Migration
line numbers in the claim (001 L49/L112/L122; init_docker L56/L121/L131/L163) match exactly.

### A3. Refutation angle "a DB trigger cascades the delete" — CLOSED
`information_schema.triggers` for contacts/deals/messages/tasks/call_summaries returns
ZERO rows. No trigger removes children.

### A4. Refutation angle "a dedicated GDPR/erasure endpoint is the real deletion path" — CLOSED
Grepped the API for `gdpr|erasure|right.to.erase|purge|anonymiz|hard.delete|scrub|redact`
— ZERO hits. The only other delete endpoints are `delete_task` (tasks.py:164) and
`delete_deal` (deals.py:429), which delete a single task/deal by its own id, not child
rows by `contact_id`. The contact-delete endpoint IS the data-deletion surface; there is
no "correct" path this finding was mistakenly measured against.

### A5. Live-DB ground truth — independently re-queried (UPHELD)
```
$ docker exec crm-local-pg psql -U postgres -d crmdb -c "<referential_constraints query>"
 call_summaries | contact_id | SET NULL
 deals          | contact_id | SET NULL
 messages       | contact_id | SET NULL
 tasks          | contact_id | SET NULL
```
PostgreSQL 16.13, DB `crmdb` on crm-local-pg:5433. Matches the claim's table exactly.

### A6. Independent end-to-end reproduction (UPHELD) — distinct test IDs, full rollback
Seeded a fresh namespaced TEST workspace (`REFUTE-AUDIT-WS`, slug `refute-audit-ws`) with a
contact + linked deal/message/task/call_summary, ran the handler's exact op
`DELETE FROM contacts WHERE id=...`, observed children, then ROLLBACK. (Note: live schema
has extra NOT-NULL `workspaces.slug` and a `deals_stage_check` allowing only
discovery/qualified/proposal/negotiation/closed_won/closed_lost — adjusted seed accordingly;
this further confirms the live DB is the real, current schema.)

Observed AFTER the contact delete:
```
 contact_rows_remaining = 0          <- contact gone
  kind   | orphaned | rows_exist | pii_sample
 --------+----------+------------+-----------------------------------------------------
  deal   |    t     |     1      |
  message|    t     |     1      | jane.refute@example.com | SENSITIVE BODY: my SSN is 000-00-0000
  task   |    t     |     1      |
  call   |    t     |     1      | TRANSCRIPT: confidential call content | SUMMARY: discussed pricing
```
All 4 children survive with `contact_id` NULLed; message still carries `sender_email` +
`body_plain`, call_summary still carries `transcript` + `summary`. PII persists verbatim
after a "successful" deletion. This independently reproduces items (5) and the PLAIN ANSWER.

### A7. Cleanup verified (no test data left behind)
Repro ran inside a transaction terminated by ROLLBACK (nothing ever committed). Post-rollback
sweep of all 6 tables for the REFUTE-AUDIT ids returns 0 across the board. Two earlier seed
attempts errored on schema constraints and auto-rolled-back (BEGIN aborted), also leaving
nothing. Zero residue.

### Minor accuracy notes (do not change the verdict)
- The claim cites only migration line numbers for the FK rules; the ORM child-column defs
  (`*.py` ondelete="SET NULL") independently corroborate, so the static case is actually
  stronger than stated.
- The original repro narrative said it "dropped the TEST workspace (CASCADE) before COMMIT";
  this independent run instead used ROLLBACK. Both leave no residue; cleanup claim holds.
- One nuance worth recording for the fix: because the message↔contact FK is SET NULL, even
  the alternate `delete_deal`/`delete_task` endpoints would not scrub message/call PII; a
  proper erasure must explicitly delete/scrub child rows by `contact_id`.

**VERIFIER VERDICT: UPHELD (high).** The finding is accurate, not overstated, not
already-mitigated, and not environment-specific (it is the declared schema + ORM behavior,
reproduced live). Deleting a contact removes only the contacts row and leaves deals,
messages (sender_email + body_plain), tasks, and call_summaries (transcript + summary) as
orphaned rows with contact_id=NULL — refuting the GDPR right-to-erasure / cascade-deletion
claim.
