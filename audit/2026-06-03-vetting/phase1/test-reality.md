# NovaCRM Audit — Phase 1: Test Reality (API + Web)

Agent: test-reality | Date: 2026-06-03 | Worktree: /tmp/crm-signup-fix (branch fix/signup-confirm-redirect)
HEAD: 429da2f  (includes 85077f4 'chore: update PROGRESS.md — Phase 8 complete, 324 tests pass')

## Verdict on the "324 tests pass" claim

TRUE for the Python/API suite. Observed exactly 324 passed, 0 failed, 0 errors, 0 skipped, exit code 0.
Reproduced twice (1.91s and 1.63s). 324 collected == 324 passed; per-file counts sum to 324; no skips/xfails/xpasses/deselects.
The claim is API-only. It does NOT cover the web e2e smoke spec, which is separate and currently 7/9 (2 failing — selector bugs, not product crashes).

## Environment
- Python venv: /mnt/external/Projects/crm-agentic/apps/api/.venv (Python 3.11.15)
- DB fully MOCKED via tests/conftest.py (AsyncMock); root conftest.py injects test env vars with os.environ.setdefault.
- Therefore Postgres/Redis are NOT actually exercised by the unit suite (started crm-local-pg:5433 + crm-redis:6379 anyway; not required).
- Command: cd /tmp/crm-signup-fix/apps/api && /mnt/external/Projects/crm-agentic/apps/api/.venv/bin/python -m pytest tests/ --tb=short -q

## API result (exact)
- passed: 324
- failed: 0
- errors: 0
- skipped: 0
- summary line: `324 passed, 2 warnings in 1.91s`  (exit 0)
- 2 warnings are benign: starlette python_multipart PendingDeprecation; pydantic protected-namespace 'model_used'.

## Web build
- pnpm 10.33.0 / node v25.2.1. node_modules present.
- `pnpm build` (demo env) => BUILD_EXIT=0. 21 routes compiled. Only benign recharts width/height warnings during static gen.

## Web e2e smoke (e2e/smoke.spec.ts)
- Designed for LOCAL demo server: playwright.config webServer runs 'npm run start' with NEXT_PUBLIC_DEMO_MODE=true, baseURL http://localhost:3000.
- NOT designed for https://www.riphere.com (relative routes + demo auth-bypass + seeded demo data). Actions are read-only (goto/fill/click), but prod would mismatch, so ran it as configured (local demo).
- Result: 7 passed, 2 failed (12.7s).
  - FAIL dashboard loads with KPI cards: fallback locator [class*=font-mono].first() resolves to a HIDDEN <p>'Agentic Intelligence' -> toBeVisible fails. Brittle selector; dashboard itself renders.
  - FAIL contacts page search filters results: strict-mode violation — getByPlaceholder(/search/i).or(getByRole('searchbox')) now matches 2 inputs (global nav search + page search). .fill() errors. Test-selector bug, not product crash.

## Prod reachability (read-only GET, non-destructive)
- https://www.riphere.com  GET / -> 200, /dashboard -> 200, /contacts -> 200, /login -> 200. Server: railway-edge / Next.js (x-nextjs-prerender HIT).

## The 324 source
- PROGRESS.md:40 — '...324 tests pass (up from 318)' (Phase 8).

============================================================================
## Full pytest output — last 100 lines (verbose run)
============================================================================
tests/test_services.py::test_score_clarity_happy_path PASSED             [ 73%]
tests/test_services.py::test_score_clarity_clamps_score_to_0_100 PASSED  [ 74%]
tests/test_services.py::test_score_clarity_invalid_json_returns_default PASSED [ 74%]
tests/test_services.py::test_score_clarity_empty_content_returns_default PASSED [ 74%]
tests/test_services.py::test_score_clarity_truncates_long_rationale PASSED [ 75%]
tests/test_slack_interactions.py::test_verify_signature_no_signing_secret_returns_false PASSED [ 75%]
tests/test_slack_interactions.py::test_verify_signature_stale_timestamp_returns_false PASSED [ 75%]
tests/test_slack_interactions.py::test_verify_signature_valid_hmac PASSED [ 75%]
tests/test_slack_interactions.py::test_slack_interactions_invalid_signature_returns_403 PASSED [ 76%]
tests/test_slack_interactions.py::test_slack_interactions_empty_payload_returns_ok PASSED [ 76%]
tests/test_slack_interactions.py::test_slack_interactions_no_actions_returns_ok PASSED [ 76%]
tests/test_slack_interactions.py::test_slack_interactions_unknown_action_returns_ok PASSED [ 77%]
tests/test_slack_interactions.py::test_slack_interactions_event_not_found_returns_ok PASSED [ 77%]
tests/test_slack_interactions.py::test_slack_interactions_hitl_dismiss PASSED [ 77%]
tests/test_slack_interactions.py::test_slack_interactions_hitl_approve_no_connector PASSED [ 78%]
tests/test_slack_interactions.py::test_slack_interactions_hitl_approve_happy_path PASSED [ 78%]
tests/test_slack_interactions.py::test_slack_interactions_hitl_approve_gmail_error PASSED [ 78%]
tests/test_slack_interactions.py::test_slack_interactions_dismiss_posts_to_response_url PASSED [ 79%]
tests/test_slack_interactions.py::test_slack_interactions_approve_posts_success_to_response_url PASSED [ 79%]
tests/test_slack_interactions.py::test_slack_interactions_approve_updates_contact_last_activity PASSED [ 79%]
tests/test_slack_interactions.py::test_slack_client_update_message_calls_chat_update PASSED [ 79%]
tests/test_slack_interactions.py::test_slack_client_ack_response_url_posts_json PASSED [ 80%]
tests/test_slack_router.py::test_slack_auth_url_returns_url PASSED       [ 80%]
tests/test_slack_router.py::test_slack_auth_url_wrong_workspace_returns_403 PASSED [ 80%]
tests/test_slack_router.py::test_slack_callback_invalid_state_returns_400 PASSED [ 81%]
tests/test_slack_router.py::test_slack_callback_token_exchange_fails_returns_400 PASSED [ 81%]
tests/test_slack_router.py::test_slack_callback_no_user_token_returns_400 PASSED [ 81%]
tests/test_slack_router.py::test_slack_callback_happy_path_new_connector PASSED [ 82%]
tests/test_slack_router.py::test_slack_callback_updates_existing_connector PASSED [ 82%]
tests/test_slack_router.py::test_slack_callback_no_profile_email_uses_fallback PASSED [ 82%]
tests/test_slack_router.py::test_slack_sync_wrong_workspace_returns_403 PASSED [ 83%]
tests/test_slack_router.py::test_slack_sync_no_connector_returns_404 PASSED [ 83%]
tests/test_slack_router.py::test_slack_sync_happy_path PASSED            [ 83%]
tests/test_slack_router.py::test_slack_events_url_verification_challenge PASSED [ 83%]
tests/test_slack_router.py::test_slack_events_event_callback_triggers_ingest PASSED [ 84%]
tests/test_slack_router.py::test_slack_events_bad_signature_returns_401 PASSED [ 84%]
tests/test_tasks.py::test_list_tasks_empty PASSED                        [ 84%]
tests/test_tasks.py::test_list_tasks_returns_tasks PASSED                [ 85%]
tests/test_tasks.py::test_list_tasks_wrong_workspace_returns_403 PASSED  [ 85%]
tests/test_tasks.py::test_create_task_returns_201 PASSED                 [ 85%]
tests/test_tasks.py::test_create_task_missing_title_returns_422 PASSED   [ 86%]
tests/test_tasks.py::test_create_task_wrong_workspace_returns_403 PASSED [ 86%]
tests/test_tasks.py::test_update_task_commits PASSED                     [ 86%]
tests/test_tasks.py::test_update_task_not_found_returns_404 PASSED       [ 87%]
tests/test_tasks.py::test_update_task_wrong_workspace_returns_403 PASSED [ 87%]
tests/test_tasks.py::test_update_task_all_fields PASSED                  [ 87%]
tests/test_tasks.py::test_delete_task_returns_204 PASSED                 [ 87%]
tests/test_tasks.py::test_delete_task_not_found_returns_404 PASSED       [ 88%]
tests/test_tasks.py::test_delete_task_wrong_workspace_returns_403 PASSED [ 88%]
tests/test_workers.py::test_compute_score_base_lead_is_50_warm PASSED    [ 88%]
tests/test_workers.py::test_compute_score_customer_bonus PASSED          [ 89%]
tests/test_workers.py::test_compute_score_prospect_bonus PASSED          [ 89%]
tests/test_workers.py::test_compute_score_churned_penalty PASSED         [ 89%]
tests/test_workers.py::test_compute_score_deal_count_bonus PASSED        [ 90%]
tests/test_workers.py::test_compute_score_revenue_above_50k PASSED       [ 90%]
tests/test_workers.py::test_compute_score_revenue_10k_to_50k PASSED      [ 90%]
tests/test_workers.py::test_compute_score_hot_label_at_70_plus PASSED    [ 91%]
tests/test_workers.py::test_compute_score_all_bonuses_clamped_at_100 PASSED [ 91%]
tests/test_workers.py::test_compute_score_zero_revenue_no_revenue_signal PASSED [ 91%]
tests/test_workers.py::test_decode_body_plain_text PASSED                [ 91%]
tests/test_workers.py::test_decode_body_html_mime_returns_empty PASSED   [ 92%]
tests/test_workers.py::test_decode_body_no_data_field_returns_empty PASSED [ 92%]
tests/test_workers.py::test_decode_body_empty_payload_returns_empty PASSED [ 92%]
tests/test_workers.py::test_decode_body_multipart_finds_first_plain PASSED [ 93%]
tests/test_workers.py::test_decode_body_nested_multipart PASSED          [ 93%]
tests/test_workers.py::test_decode_body_unicode_content PASSED           [ 93%]
tests/test_workers.py::test_compute_win_probability_discovery_base PASSED [ 94%]
tests/test_workers.py::test_compute_win_probability_qualified_stage PASSED [ 94%]
tests/test_workers.py::test_compute_win_probability_proposal_stage PASSED [ 94%]
tests/test_workers.py::test_compute_win_probability_negotiation_stage PASSED [ 95%]
tests/test_workers.py::test_compute_win_probability_high_value_bonus PASSED [ 95%]
tests/test_workers.py::test_compute_win_probability_stale_deal_penalty PASSED [ 95%]
tests/test_workers.py::test_compute_win_probability_no_updated_at_no_staleness PASSED [ 95%]
tests/test_workers.py::test_compute_win_probability_clamped_at_95 PASSED [ 96%]
tests/test_workers.py::test_compute_win_probability_clamped_at_0 PASSED  [ 96%]
tests/test_workers.py::test_draft_email_plain_json_response PASSED       [ 96%]
tests/test_workers.py::test_draft_email_strips_json_markdown_fence PASSED [ 97%]
tests/test_workers.py::test_draft_email_strips_plain_markdown_fence PASSED [ 97%]
tests/test_workspaces.py::test_get_workspace_returns_workspace PASSED    [ 97%]
tests/test_workspaces.py::test_get_workspace_not_found_returns_404 PASSED [ 98%]
tests/test_workspaces.py::test_get_workspace_wrong_workspace_returns_403 PASSED [ 98%]
tests/test_workspaces.py::test_patch_workspace_updates_name PASSED       [ 98%]
tests/test_workspaces.py::test_patch_workspace_updates_mode PASSED       [ 99%]
tests/test_workspaces.py::test_patch_workspace_not_found_returns_404 PASSED [ 99%]
tests/test_workspaces.py::test_patch_workspace_wrong_workspace_returns_403 PASSED [ 99%]
tests/test_workspaces.py::test_post_workspace_creates_and_binds_user PASSED [100%]

=============================== warnings summary ===============================
../../../../mnt/external/Projects/crm-agentic/apps/api/.venv/lib/python3.11/site-packages/starlette/formparsers.py:12
  /mnt/external/Projects/crm-agentic/apps/api/.venv/lib/python3.11/site-packages/starlette/formparsers.py:12: PendingDeprecationWarning: Please use `import python_multipart` instead.
    import multipart

../../../../mnt/external/Projects/crm-agentic/apps/api/.venv/lib/python3.11/site-packages/pydantic/_internal/_fields.py:132
  /mnt/external/Projects/crm-agentic/apps/api/.venv/lib/python3.11/site-packages/pydantic/_internal/_fields.py:132: UserWarning: Field "model_used" in ScoreClarityResponse has conflict with protected namespace "model_".
  
  You may be able to resolve this warning by setting `model_config['protected_namespaces'] = ()`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 324 passed, 2 warnings in 1.63s ========================
