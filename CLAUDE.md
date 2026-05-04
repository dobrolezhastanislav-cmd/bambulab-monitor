# Bambu Lab X1C — Printer Monitor

Standalone Python worker that watches the printer via Bambu Lab's cloud MQTT and sends a Telegram message when the printer disconnects unexpectedly mid-print.

## What it does
- Connects to `us.mqtt.bambulab.com:8883` using Bambu account credentials
- Tracks `gcode_state` from MQTT messages:
  - `PREPARE / RUNNING / PAUSE` → sets "was printing" flag
  - `FINISH / FAILED` → clears flag (normal end, no notification)
  - Unexpected disconnect while flag is set → sends Telegram alert
  - Disconnect while idle → silent
- Reconnects automatically every 30 seconds after any dropout

## Stack
- Python, paho-mqtt, requests
- Deployed on Railway as a **worker** (no web server)
- GitHub repo: https://github.com/dobrolezhastanislav-cmd/bambulab-monitor
- Railway project: https://railway.com/project/4da80293-08eb-40cc-9bd6-dbf811acfe78

## Files
- `printer_monitor.py` — entire logic, single file
- `requirements.txt` — paho-mqtt==1.6.1, requests==2.31.0
- `Procfile` — `worker: python printer_monitor.py`

## Environment variables (set in Railway → Variables)

User logs into Bambu Lab via Google SSO — no Bambu password exists. Use **Mode A**.

**Mode A — Token (active setup):**
| Variable | Description |
|---|---|
| `BAMBU_TOKEN` | JWT access token extracted from browser (expires ~90 days) |
| `BAMBU_USERNAME` | Bambu username from same response (e.g. `u_xxxxxxxxxxxxxxxx`) |
| `PRINTER_SERIAL` | Printer serial (touchscreen → Settings → Device Info) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | User's personal Telegram numeric ID |
| `BAMBU_REGION` | `us` (default), `eu`, or `cn` |

**Mode B — Email/password (not usable — Google SSO account).**

### How to extract the token (repeat every ~90 days)
1. Open **bambulab.com** in Chrome
2. Open DevTools → **Network** tab → check **Preserve log**
3. Log in with Google
4. In the Network tab filter by `login` — find the request to `api.bambulab.com`
5. Click it → **Response** tab → copy `accessToken` → set as `BAMBU_TOKEN`
6. Copy `username` → set as `BAMBU_USERNAME`
7. Save in Railway → service redeploys automatically

No `.env` file — all config is Railway env vars only.

## Deployment
```
cd C:\Users\stanislav.dobrolezha\printer-monitor
git add . && git commit -m "..." && git push
# Railway auto-redeploys on push
```

To redeploy manually: `railway up --detach` from the project folder.

## Known limitations
- **2FA**: if Bambu account has 2FA enabled, auth fails with a clear error message. Workaround: disable 2FA on the Bambu account.
- **Cloud dependency**: requires the printer to have Bambu cloud mode enabled (default on X1C).
- **Local MQTT not used**: the printer's local MQTT (192.168.x.x:8883) was intentionally avoided so the monitor can run on Railway (cloud), not on a local machine.

## CLI tools
- `gh` is installed at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH — use full path or open a fresh terminal)
- `railway` CLI is installed via npm; execution policy was set to RemoteSigned for current user
