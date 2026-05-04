"""
Bambu Lab X1C — Unexpected Shutdown Monitor (Railway / cloud version)
======================================================================
Connects to Bambu Lab's CLOUD MQTT broker using your account credentials.
Works from any machine including Railway — no local network access needed.

Setup:
  Set these environment variables (Railway → Variables tab):
    BAMBU_EMAIL         your Bambu Lab account email
    BAMBU_PASSWORD      your Bambu Lab account password
    PRINTER_SERIAL      serial number (touchscreen → Settings → Device Info)
    TELEGRAM_BOT_TOKEN  your bot token
    TELEGRAM_CHAT_ID    your personal Telegram numeric ID (@userinfobot)
    BAMBU_REGION        "us" or "eu" or "cn"  (default: "us")

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

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── config from env vars ─────────────────────────────────────────────────────
BAMBU_EMAIL        = os.environ["BAMBU_EMAIL"]
BAMBU_PASSWORD     = os.environ["BAMBU_PASSWORD"]
PRINTER_SERIAL     = os.environ["PRINTER_SERIAL"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
REGION             = os.environ.get("BAMBU_REGION", "us")

MQTT_HOST          = f"{REGION}.mqtt.bambulab.com"
MQTT_PORT          = 8883
AUTH_URL           = "https://api.bambulab.com/v1/user-service/user/login"

RECONNECT_DELAY    = 30   # seconds between reconnect attempts

# ── print states ─────────────────────────────────────────────────────────────
ACTIVE_STATES   = {"PREPARE", "RUNNING", "PAUSE"}
FINISHED_STATES = {"FINISH", "FAILED"}

# ── shared state ─────────────────────────────────────────────────────────────
_was_printing = False


# ── Bambu auth ────────────────────────────────────────────────────────────────
def bambu_login() -> tuple[str, str]:
    """Returns (mqtt_username, jwt_token). Raises on failure."""
    log.info("Authenticating with Bambu Lab cloud…")
    r = requests.post(
        AUTH_URL,
        json={"account": BAMBU_EMAIL, "password": BAMBU_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    # If the account has 2-factor auth enabled, the API returns a tfaKey
    if data.get("tfaKey"):
        raise RuntimeError(
            "Your Bambu Lab account has 2FA enabled. "
            "Disable 2FA temporarily, or create a separate Bambu account "
            "without 2FA and add the printer to it for monitoring."
        )

    token    = data["accessToken"]
    username = data["username"]          # looks like "u_xxxxxxxxxxxxxxxx"
    log.info("Logged in as %s", username)
    return username, token


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
            username, token = bambu_login()
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
