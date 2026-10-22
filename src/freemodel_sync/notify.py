"""Best-effort notifications when the primary model changes.

Notifications are strictly optional: every failure (missing environment
variables, network errors, non-2xx responses, ...) is logged and swallowed so
that a sync never fails because a chat message or webhook could not be sent.
Secrets (Telegram bot tokens, full webhook URLs) are never written to logs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

import httpx

from .models import Selection

logger = logging.getLogger(__name__)

DEFAULT_TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_TELEGRAM_CHAT_ENV = "TELEGRAM_CHAT_ID"
DEFAULT_WEBHOOK_URL_ENV = "FREEMODEL_SYNC_WEBHOOK_URL"


def _new_key(selection: Selection) -> str:
    """Return the stable ``provider|model`` key of the selection's primary."""

    return f"{selection.provider}|{selection.primary.model.id}"


def _fallback_ids(selection: Selection) -> List[str]:
    return [fallback.model.id for fallback in selection.fallbacks]


def build_message(old_key: Optional[str], selection: Selection) -> str:
    """Build the human-readable switch message used by every channel."""

    old = old_key or "none"
    fallbacks = ", ".join(_fallback_ids(selection))
    return (
        f"freemodel-sync: primary model changed: {old} -> {_new_key(selection)}; "
        f"fallbacks: {fallbacks}"
    )


def _hostname(url: str) -> str:
    """Return just the host of *url* so logs never contain tokens or paths."""

    try:
        return urlsplit(url).hostname or "webhook"
    except ValueError:  # pragma: no cover - defensive
        return "webhook"


def _post_json(client: httpx.Client, url: str, payload: Dict[str, Any]) -> None:
    """POST *payload* as JSON and raise on an obvious HTTP error status."""

    response = client.post(url, json=payload)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status >= 400:
        raise RuntimeError(f"HTTP {status}")


def _send_telegram(
    client: httpx.Client,
    config: Mapping[str, Any],
    text: str,
    *,
    dry_run: bool,
) -> bool:
    """Send *text* through Telegram; return ``True`` when it was handled."""

    token_env = str(config.get("bot_token_env") or DEFAULT_TELEGRAM_TOKEN_ENV)
    chat_env = str(config.get("chat_id_env") or DEFAULT_TELEGRAM_CHAT_ENV)
    token = os.environ.get(token_env)
    chat_id = os.environ.get(chat_env)
    missing = [name for name, value in ((token_env, token), (chat_env, chat_id)) if not value]
    if missing:
        logger.info("telegram notification skipped: missing %s", ", ".join(missing))
        return False
    if dry_run:
        logger.info("telegram notification skipped (dry run)")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        _post_json(client, url, {"chat_id": chat_id, "text": text})
    except Exception as exc:  # noqa: BLE001 - notifications must never raise
        # Only the exception type: httpx messages can embed the tokenized URL.
        logger.warning("telegram notification failed: %s", type(exc).__name__)
        return False
    return True


def _send_webhook(
    client: httpx.Client,
    config: Mapping[str, Any],
    payload: Dict[str, Any],
    *,
    dry_run: bool,
) -> bool:
    """Send *payload* to the configured webhook; return ``True`` when handled."""

    url = config.get("url")
    if not url:
        env_name = str(config.get("url_env") or DEFAULT_WEBHOOK_URL_ENV)
        url = os.environ.get(env_name)
    if not url:
        logger.info("webhook notification skipped: no URL configured")
        return False
    url = str(url)
    if dry_run:
        logger.info("webhook notification skipped (dry run)")
        return False

    try:
        _post_json(client, url, payload)
    except Exception as exc:  # noqa: BLE001 - notifications must never raise
        logger.warning(
            "webhook notification to %s failed: %s",
            _hostname(url),
            type(exc).__name__,
        )
        return False
    return True


def notify_switch(
    old_key: Optional[str],
    new_selection: Optional[Selection],
    *,
    telegram: Optional[Mapping[str, Any]] = None,
    webhook: Optional[Mapping[str, Any]] = None,
    client: Optional[httpx.Client] = None,
    dry_run: bool = False,
) -> List[str]:
    """Notify configured channels that the primary model changed.

    Args:
        old_key: previous ``"<provider>|<model id>"`` key, or ``None``.
        new_selection: the newly selected primary/fallback set.
        telegram: optional mapping with ``bot_token_env`` / ``chat_id_env``.
        webhook: optional mapping with ``url_env`` and/or ``url``.
        client: optional ``httpx.Client`` (injected in tests).
        dry_run: when true, only log what would be sent; no HTTP request is
            made and no channel is reported as notified.

    Returns:
        The names of the channels that were successfully notified.
    """

    if new_selection is None:
        logger.info("notification skipped: no selection")
        return []

    text = build_message(old_key, new_selection)
    payload = {
        "event": "primary_changed",
        "old": old_key,
        "new": _new_key(new_selection),
        "fallbacks": _fallback_ids(new_selection),
        "text": text,
    }

    channels: List[str] = []
    owns_client = client is None and not dry_run
    active_client = client
    if owns_client:
        active_client = httpx.Client(timeout=10.0)

    try:
        if isinstance(telegram, Mapping) and telegram.get("enabled", True) is not False:
            if _send_telegram(active_client, telegram, text, dry_run=dry_run):
                channels.append("telegram")
        if isinstance(webhook, Mapping) and webhook.get("enabled", True) is not False:
            if _send_webhook(active_client, webhook, payload, dry_run=dry_run):
                channels.append("webhook")
    finally:
        if owns_client and active_client is not None:
            try:
                active_client.close()
            except Exception:  # pragma: no cover - defensive
                pass

    return channels
