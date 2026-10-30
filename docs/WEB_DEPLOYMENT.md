# Browser deployment

Athena's React application is shared by Android and the browser. Vercel hosts
only the static frontend; Supabase owns authentication and FastAPI verifies the
Supabase JWT on every protected backend request.

## Vercel configuration

Import the GitHub repository into Vercel and keep the repository root as the
project root. The committed `vercel.json` runs the validated Vite build and
supports direct navigation to routes such as `/login`, `/chat`, and `/profile`.

Set these variables for the Production environment:

```text
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<Supabase publishable/anon key>
VITE_AGENT_API_URL=https://<public-fastapi-origin>
```

These values are embedded in browser JavaScript. Never add
`SUPABASE_SERVICE_ROLE_KEY`, `GIGACHAT_AUTH_KEY`, database credentials, or any
other server secret to Vercel variables prefixed with `VITE_`.

## Backend and authentication configuration

After Vercel assigns the production URL, add that exact origin to
`API_CORS_ORIGINS` in `backend/.env`, for example:

```text
API_CORS_ORIGINS=https://athena.example.com,https://localhost
```

Restart API and worker after changing backend environment variables.

In Supabase Authentication URL Configuration, add the browser callbacks:

```text
https://athena.example.com/
https://athena.example.com/reset-password
https://athena.example.com/profile?reauth=account-delete
```

Keep the Android deep-link callbacks already configured. Test email/password
login, OAuth or email callback, token refresh, logout/login, chat SSE, confirmed
writes, and read-back before sharing the site with testers.

## Availability limitation

Vercel deploys only the frontend. The FastAPI URL must remain publicly
available. A tunnel to a developer laptop is suitable for a short test session,
but the site loses chat and AI functions whenever the laptop, Docker, or tunnel
stops.
