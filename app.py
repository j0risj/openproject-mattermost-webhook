import json
import logging
import os

import requests
from flask import Flask, jsonify, request

MATTERMOST_WEBHOOK_URL = os.environ.get("MATTERMOST_WEBHOOK_URL", "")
MATTERMOST_USERNAME = os.environ.get("MATTERMOST_USERNAME", "OpenProject")
MATTERMOST_ICON_URL = os.environ.get(
    "MATTERMOST_ICON_URL",
    "https://www.openproject.org/assets/images/ico/apple-touch-icon.png",
)
LISTEN_PORT = int(os.environ.get("PORT", "8080"))
OPENPROJECT_BASE_URL = os.environ.get("OPENPROJECT_BASE_URL", "").rstrip("/")
VERIFY_TOKEN = os.environ.get("OPENPROJECT_WEBHOOK_TOKEN", "")

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("op-mm-bridge")

app = Flask(__name__)

ACTION_LABELS = {
    "work_package:created": "created",
    "work_package:updated": "updated",
}


def field(wp, name):
    value = wp.get(name)
    if value is None:
        return "_(none)_"
    if isinstance(value, dict):
        return str(value.get("name", value.get("id", "_(unknown)_")))
    return str(value)


def wp_url(wp):
    if OPENPROJECT_BASE_URL:
        return "{}/work_packages/{}".format(OPENPROJECT_BASE_URL, wp.get("id", ""))
    return "_(set OPENPROJECT_BASE_URL for links)_"


def format_created(wp, actor):
    lines = [
        "**{} created a new work package**: [{}]({})".format(
            actor, wp.get("subject", "_(no subject)_"), wp_url(wp)
        ),
        "",
        "| Field | Value |",
        "|---|---|",
        "| Project | {} |".format(field(wp, "project")),
        "| Type | {} |".format(field(wp, "type")),
        "| Status | {} |".format(field(wp, "status")),
        "| Priority | {} |".format(field(wp, "priority")),
        "| Assignee | {} |".format(field(wp, "assignee")),
        "| Author | {} |".format(field(wp, "author")),
    ]
    description = (wp.get("description") or {}).get("raw")
    if description:
        excerpt = description.strip().splitlines()[0][:300]
        lines += ["", "> {}".format(excerpt)]
    return "\n".join(lines)


def format_updated(wp, actor):
    changes = []
    for key, value in (wp.get("_changes") or {}).items():
        old = value[0] if isinstance(value, (list, tuple)) and len(value) > 0 else ""
        new = value[1] if isinstance(value, (list, tuple)) and len(value) > 1 else value
        changes.append("| {} | {} | {} |".format(key, old, new))
    lines = [
        "**{} updated**: [{}]({})".format(actor, wp.get("subject", "_(no subject)_"), wp_url(wp)),
        "",
    ]
    if changes:
        lines += ["| Field | Before | After |", "|---|---|---|"] + changes
    else:
        lines += ["_(no change details in payload)_"]
    return "\n".join(lines)


def format_message(payload):
    action = payload.get("action", "")
    wp = payload.get("work_package") or {}
    actor = (payload.get("actor") or {}).get("name", "Someone")
    if action == "work_package:created":
        return format_created(wp, actor)
    if action == "work_package:updated":
        return format_updated(wp, actor)
    log.info("Ignoring action %s", action)
    return None


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if VERIFY_TOKEN:
        auth = request.headers.get("Authorization", "")
        if auth != "Bearer {}".format(VERIFY_TOKEN):
            return jsonify(error="unauthorized"), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(error="invalid JSON payload"), 400

    if not MATTERMOST_WEBHOOK_URL:
        log.error("MATTERMOST_WEBHOOK_URL is not configured")
        return jsonify(error="mattermost webhook not configured"), 500

    text = format_message(payload)
    if text is None:
        return jsonify(status="ignored"), 200

    body = {
        "text": text,
        "username": MATTERMOST_USERNAME,
        "icon_url": MATTERMOST_ICON_URL,
    }
    channel = os.environ.get("MATTERMOST_CHANNEL")
    if channel:
        body["channel"] = channel

    try:
        resp = requests.post(MATTERMOST_WEBHOOK_URL, json=body, timeout=10)
    except requests.RequestException as exc:
        log.error("Error posting to Mattermost: %s", exc)
        return jsonify(error="failed to reach mattermost"), 502

    if resp.status_code >= 400:
        log.error("Mattermost returned %s: %s", resp.status_code, resp.text[:200])
        return jsonify(error="mattermost rejected the message"), 502

    return jsonify(status="delivered"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=LISTEN_PORT)
