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
| Variable | Description |
|---|---|
| `BAMBU_EMAIL` | Bambu Lab account email |
| `BAMBU_PASSWORD` | Bambu Lab account password |
| `PRINTER_SERIAL` | Printer serial (touchscreen → Settings → Device Info) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | User's personal Telegram numeric ID |
| `BAMBU_REGION` | `us` (default), `eu`, or `cn` |

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
