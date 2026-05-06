# Deploy to Streamlit Community Cloud

The multi-page app at `streamlit_app.py` is designed to deploy directly
to Streamlit Community Cloud. Free, private GitHub repo OK, automatic
HTTPS, redeploys on git push.

## One-time setup

1. Push the repo to GitHub (a `gh` CLI script in this repo creates the
   private repo and the initial push — see `Push to GitHub` below).
2. Sign in at https://share.streamlit.io with the same GitHub account.
3. Click **New app** → pick the repo → branch `main` → main file
   `streamlit_app.py`.
4. **Advanced settings → Secrets** → paste the contents of
   `.streamlit/secrets.toml.example`, replacing the placeholders with
   your real values:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."

   # Optional today; required when you wire up the bot.
   SUPABASE_URL = ""
   SUPABASE_KEY = ""
   ```

5. Click **Deploy**.

The first deploy takes ~3-5 minutes (Streamlit installs deps from
`requirements.txt` and starts the app). Once live you'll get a URL like
`https://smc-bot-toolkit-xxxx.streamlit.app`.

## Updating the app

`git push` to main → Streamlit auto-redeploys in ~30 seconds.

## Updating secrets

App settings → **Secrets** → edit → save → app reboots automatically.

## Local dev with secrets

For local dev, either:

- Put values in `.env` at the repo root (gitignored), or
- Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
  (also gitignored).

Both are read at startup. Streamlit secrets take precedence over `.env`.

## Push to GitHub (first time)

From the `live_bot/` directory:

```bash
gh repo create smc-bot-toolkit --private --source=. --remote=origin --push
```

This creates a new private GitHub repo named `smc-bot-toolkit` under
your authenticated `gh` account, sets it as `origin`, and pushes the
default branch.

If the repo name is taken, swap to e.g. `smc-bot-toolkit-2026`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| App shows "ANTHROPIC_API_KEY not set" | Re-check Secrets tab; values must be quoted strings in TOML |
| `ModuleNotFoundError: No module named 'bot'` | The Live Performance page needs the package; run `pip install -e .` works locally; on Cloud, `requirements.txt` should not require `-e .` (it doesn't) |
| Repo is too big to push (>100 MB file) | We gitignored `*.parquet` already. Run `git ls-files | xargs ls -la | sort -k5 -n | tail` to find offenders |
| 404 on the page URL | Ensure the page file is in `pages/` and the leading number prefix is unique |
