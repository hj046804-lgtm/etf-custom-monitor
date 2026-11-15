# ETF Custom Monitor
A separate Streamlit dashboard with editable ETF watchlist and scheduled Telegram alerts.
Original repo is unchanged.

## Streamlit secrets
GITHUB_REPO = "hj046804-lgtm/etf-custom-monitor"
GITHUB_TOKEN = "YOUR_FINE_GRAINED_TOKEN_WITH_CONTENTS_READ_WRITE_FOR_NEW_REPO"
ADMIN_PASSWORD = "YOUR_PRIVATE_PASSWORD"

## GitHub Actions secrets
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (reuse values from existing project).

## Deploy
Streamlit Community Cloud > New app > select this repo, main, app.py.
Set Streamlit secrets before opening the app. Do not commit tokens or passwords.

## Signals
Same strategy as original: VIX <22 OR 10y yield <= prior 10-day average,
AND >=3 of 4 technical conditions (RSI rebound, MACD cross, volume >=120% of previous 20d average, Bollinger lower-band reentry).
Scheduled 23:30 UTC Monday-Friday (after US market close); free scheduler can delay/skip runs.
No automated trades. Yahoo data may be delayed or incomplete.
