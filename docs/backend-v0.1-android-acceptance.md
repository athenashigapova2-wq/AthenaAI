# Backend v0.1 Android acceptance

This is a manual release gate, not a mocked or browser-intercepted test. Run it
against the APK candidate and the real hosted stack.

## Required runtime

- the APK is built with the public HTTPS FastAPI origin;
- Supabase Auth and database are the real test project;
- FastAPI and a Celery worker use the same Redis instance and queue;
- `LLM_PROVIDER=gigachat`;
- `AGENT_INFRASTRUCTURE_TEST_MODE=false`;
- `/health/ready` returns `status=ready`, `redis=ready`,
  `llm_provider=gigachat`, and `agent_infrastructure_test_mode=false`;
- provider, Supabase service-role, and signing credentials exist only in the
  backend/deployment secret store, never in the APK.

The bundled frontend does not need a separate web server inside the phone. A
web deployment may still be operated separately, but the APK talks directly to
FastAPI and Supabase over HTTPS.

## One pass

Use a dedicated test account and a unique meal description for each pass.

1. Launch the installed APK and log in.
2. Ask Athena to log the meal.
3. Verify that a `log_meal` confirmation card appears.
4. Verify that the meal is not visible in today's data before confirmation.
5. Confirm once and wait for completion.
6. Ask Athena what was logged today and verify the exact meal and nutritional
   values are present.
7. Ask a second, related question and verify that a real response completes.
8. Log out, close the app, reopen it, and log in again.
9. Open today's data and verify that the confirmed meal persisted exactly once.
10. Record the result below. A duplicate row, missing row, mock response,
    timeout, wrong owner data, or provider fallback is a failed pass.

## Evidence

Record no raw tokens, prompts containing personal data, or secret values.

| Pass | UTC time | APK SHA-256 | meal marker | trace/job id | one DB row | read-back | relogin persisted | result |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |
| 4 | | | | | | | | |
| 5 | | | | | | | | |
| 6 | | | | | | | | |
| 7 | | | | | | | | |
| 8 | | | | | | | | |
| 9 | | | | | | | | |
| 10 | | | | | | | | |

Backend v0.1 is accepted only when all ten rows pass on the same APK and backend
revision. Restarting or changing either artifact resets the sequence.

# Android authentication callbacks

Before building an APK, add all three exact redirect URLs to the Supabase Auth URL
allow list (`Authentication` → `URL Configuration` → `Redirect URLs`):

```text
dev.aminashigapova2.athena://auth/callback
dev.aminashigapova2.athena://auth/reset-password
dev.aminashigapova2.athena://auth/reauth-delete
```

The Android manifest accepts only the `dev.aminashigapova2.athena://auth/*`
scheme/host pair. OAuth, signup confirmation, and password recovery use PKCE;
the app exchanges the returned code before navigating. Account deletion
requires either the current password or a fresh OAuth round trip and never
treats token refresh as proof of recent user authentication.

Before release, verify these links on the physical Android test device:

1. Google login returns to the installed app and opens the authenticated home.
2. A password-reset email opens the installed app on `/reset-password`, and the
   new password works after logout.
3. Account deletion stays disabled until the current password is accepted or a
   fresh OAuth round trip returns to the app.
4. Refreshing an old session without re-entering credentials is rejected by the
   deletion endpoint.

