# Continuous integration

`ci.yml` runs for every pull request into `main` and every push to `main`.
It verifies the backend, frontend, offline AI behavior, migrations, and the
backend Docker image without contacting GigaChat.

The frontend currently has two type-checking scopes:

- `npm run typecheck:ci` is the mandatory, green baseline for selected core
  modules. New code added to this baseline must remain type-safe.
- `npm run typecheck` checks the wider legacy JavaScript UI. It is kept as a
  local debt audit until the existing `checkJs` findings are resolved.

`live-gigachat-evals.yml` is deliberately separate. It runs only on its weekly
schedule or via **Actions → Live GigaChat evals → Run workflow** and requires
the repository secret `GIGACHAT_AUTH_KEY`. It is never triggered by a commit
or pull request.
