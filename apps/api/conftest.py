"""Root-level conftest: inject mock env vars before any app module is imported.

This file is processed by pytest BEFORE tests/conftest.py, so env vars are
present when app.config.Settings() runs at import time.
"""

import os

_TEST_ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/testdb",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret-at-least-32-chars-long",
    "SECRET_KEY": "test-secret-key-at-least-32-chars-long",
    "ANTHROPIC_API_KEY": "sk-ant-test000000000000000000000000000000000000000000000",
    "REDIS_URL": "redis://localhost:6379/0",
    "FRONTEND_URL": "http://localhost:3000",
    "API_URL": "http://localhost:8000",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "SLACK_CLIENT_ID": "test-slack-client-id",
    "SLACK_CLIENT_SECRET": "test-slack-client-secret",
    "SLACK_SIGNING_SECRET": "test-slack-signing-secret",
    "HUNTER_API_KEY": "",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
