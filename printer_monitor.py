"""
Bambu Lab X1C — Unexpected Shutdown Monitor (Railway / cloud version)
======================================================================
Connects to Bambu Lab's CLOUD MQTT broker.
Supports two auth modes:

  Mode A — Token (for Google SSO accounts, recommended):
    BAMBU_TOKEN     JWT token extracted from browser (see CLAUDE.md for how-to)
    BAMBU_USERNAME  username from same response (looks like u_xxxxxxxxxxxxxxxx)

  Mode B — Email/password (for accounts with a Bambu password):
    BAMBU_EMAIL     your Bambu Lab account email
    BAMBU_PASSWORD  your Bambu Lab account password

  Always required:
    PRINTER_SERIAL      serial number (touchscreen → Settings → Device Info)
    TELEGRAM_BOT_TOKEN  your bot token
    TELEGRAM_CHAT_ID    your personal Telegram numeric ID (@userinfobot)
    BAMBU_REGION        "us" / "eu" / "cn"  (default: "us")

Requirements:
    pip install paho-mqtt requests
"""

import os
import json
import ssl
import time
import logging
import requests
import paho.mqtt.client as mqtt

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────────────────
PRINTER_SERIAL     = os.environ["PRINTER_SERIAL"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
REGION             = os.environ.get("BAMBU_REGION", "us")

MQTT_HOST          = f"{REGION}.mqtt.bambulab.com"
MQTT_PORT          = 8883
RECONNECT_DELAY    = 30

# ── print states ──────────────────────────────────────────────────────────────
ACTIVE_STATES   = {"PREPARE", "RUNNING", "PAUSE"}
FINISHED_STATES = {"FINISH", "FAILED"}

_was_printing = False


# ── auth ──────────────────────────────────────────────────────────────────────
def get_credentials() -> tuple[str, str]:
    """Returns (mqtt_username, jwt_token)."""

    # Mode A: token provided directly (Google SSO accounts)
    token    = os.environ.get("BAMBU_TOKEN")
    username = os.environ.get("BAMBU_USERNAME")
    if token and username:
        log.info("Using provided token for user %s", username)
        return username, token

    # Mode B: email + password login
    email    = os.environ.get("BAMBU_EMAIL")
    password = os.environ.get("BAMBU_PASSWORD")
    if email and password:
        log.info("Authenticating with email/password…")
        r = requests.post(
            "https://api.bambulab.com/v1/user-service/user/login",
            json={"account": email, "password": password},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("tfaKey"):
            raise RuntimeError("Bambu account has 2FA — disable it or use token mode.")
        log.info("Logged in as %s", data["username"])
        return data["username"], data["accessToken"]

    raise RuntimeError(
        "No auth configured. Set either BAMBU_TOKEN+BAMBU_USERNAME "
        "or BAMBU_EMAIL+BAMBU_PASSWORD."
    )


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        r.raise_for_status()
        log.info("Telegram notification sent.")
    except Exception as exc:
        log.error("Failed to send Telegram message: %s", exc)


# ── MQTT callbacks ────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        topic = f"device/{PRINTER_SERIAL}/report"
        client.subscribe(topic)
        log.info("Connected to %s, subscribed to %s", MQTT_HOST, topic)
    else:
        log.warning("MQTT connection refused, rc=%d", rc)


def on_message(client, userdata, msg):
    global _was_printing
    try:
        data  = json.loads(msg.payload)
        state = data.get("print", {}).get("gcode_state")
        if not state:
            return
        log.debug("Printer state: %s", state)
        if state in ACTIVE_STATES:
            if not _was_printing:
                log.info("Print started (%s) — watching for unexpected shutdown.", state)
            _was_printing = True
        elif state in FINISHED_STATES:
            if _was_printing:
                log.info("Print finished normally (%s).", state)
            _was_printing = False
    except Exception as exc:
        log.debug("Could not parse MQTT message: %s", exc)


def on_disconnect(client, userdata, rc):
    global _was_printing
    if rc != 0 and _was_printing:
        log.warning("Unexpected disconnect while printing — notifying.")
        send_telegram(
            "⚠️ Bambu Lab X1C відключився під час друку!\n"
            "Схоже, принтер вимкнувся несподівано. Перевір його стан."
        )
        _was_printing = False
    elif rc != 0:
        log.info("Printer disconnected while idle — no notification.")


# ── main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("Printer monitor starting. Serial: %s  Region: %s", PRINTER_SERIAL, REGION)

    while True:
        try:
            username, token = get_credentials()
        except Exception as exc:
            log.error("Auth failed: %s — retrying in %ds", exc, RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)
            continue

        client = mqtt.Client()
        client.username_pw_set(username, token)

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        client.tls_set_context(ctx)

        client.on_connect    = on_connect
        client.on_message    = on_message
        client.on_disconnect = on_disconnect

        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except Exception as exc:
            log.error("Connection error: %s", exc)

        log.info("Reconnecting in %ds…", RECONNECT_DELAY)
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
