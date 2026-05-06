"""Streamlit Cloud entry point. Routes to pages/ via the sidebar.

Promotes Streamlit secrets to environment variables so legacy code
(bot.config, dotenv loaders) keeps working without changes.
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

# --- Promote secrets to env vars (no-op when running locally with .env) ---
try:
    for k, v in st.secrets.items():
        if isinstance(v, (str, int, float)):
            os.environ.setdefault(k, str(v))
except Exception:
    pass  # st.secrets raises if no secrets.toml; fine for local dev with .env

# --- Page config ---
st.set_page_config(
    page_title="SMC Bot Toolkit",
    page_icon=None,
    layout="wide",
)

st.title("SMC Bot Toolkit")
st.caption(
    "A trade-review and bot-performance dashboard built on a methodology "
    "distilled from 1775 trader-video transcripts."
)

# --- Quick status check on configured secrets ---
anth_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
sb_url = bool(os.environ.get("SUPABASE_URL"))
sb_key = bool(os.environ.get("SUPABASE_KEY"))

c1, c2, c3 = st.columns(3)
c1.metric("ANTHROPIC_API_KEY", "set" if anth_set else "missing")
c2.metric("SUPABASE_URL", "set" if sb_url else "missing")
c3.metric("SUPABASE_KEY", "set" if sb_key else "missing")

st.divider()

st.header("Pages")

st.markdown(
    """
- **Trade Reviewer** — paste a trade idea and/or upload a chart screenshot.
  Claude scores it against the encoded SMC methodology (bias, P/D, FVG,
  sweep, IFVG, DOL, RR). Requires `ANTHROPIC_API_KEY`.
- **Live Performance** — equity curve, per-symbol summary, trade ledger,
  outcomes for the bot you're running. Requires `SUPABASE_URL` and
  `SUPABASE_KEY`. Until those are set, this page shows a placeholder.

Open a page from the sidebar on the left.
"""
)

with st.expander("Configure secrets"):
    st.markdown(
        """
**Locally** — create `.streamlit/secrets.toml` (gitignored) with:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
SUPABASE_URL = "https://xxx.supabase.co"
SUPABASE_KEY = "eyJ..."
```

Or use `.env` at the project root with the same keys (the app reads both).

**On Streamlit Community Cloud** — App settings → **Secrets** → paste the
TOML above. The app will redeploy automatically.
"""
    )

# Tiny footer with deploy info
sha_path = Path(".git") / "HEAD"
build = "local"
if sha_path.exists():
    build = "git"
st.caption(f"Build: {build}. Source: github.com/cappellaadrian/smc-bot-toolkit (private).")
