import base64
import binascii
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.integrations.gmail.types import GmailPayload, GmailRawMessage
from app.models import Marketplace
from app.orders.types import CommerceEmail


class MessageTooLargeError(ValueError):
    pass


class MalformedMessageError(ValueError):
    pass


class _SafeHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "form"}:
            self._blocked_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "form"} and self._blocked_depth:
            self._blocked_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth:
            self.parts.append(data)


def _decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MalformedMessageError("Message body encoding is invalid") from exc


def _body_parts(payload: GmailPayload) -> list[tuple[str, bytes]]:
    if payload.filename or payload.body.attachment_id:
        return []
    found: list[tuple[str, bytes]] = []
    if payload.mime_type in {"text/plain", "text/html"} and payload.body.data:
        found.append((payload.mime_type, _decode(payload.body.data)))
    for part in payload.parts:
        found.extend(_body_parts(part))
    return found


def normalize_message(raw: GmailRawMessage, max_bytes: int) -> CommerceEmail:
    body_parts = _body_parts(raw.payload)
    if sum(len(body) for _, body in body_parts) > max_bytes:
        raise MessageTooLargeError("Message body exceeds the configured limit")
    text_parts: list[str] = []
    for mime_type, body in body_parts:
        decoded = body.decode("utf-8", errors="replace")
        if mime_type == "text/html":
            parser = _SafeHTMLText()
            parser.feed(decoded)
            decoded = " ".join(parser.parts)
        text_parts.append(decoded)
    headers = {header.name.lower(): header.value for header in raw.payload.headers}
    return CommerceEmail(
        provider_message_id=raw.id,
        history_id=raw.history_id,
        sent_at=datetime.fromtimestamp(int(raw.internal_date) / 1000, tz=UTC),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        text=re.sub(r"\s+", " ", " ".join(text_parts)).strip(),
    )


_ALLOWED_HOSTS = {
    Marketplace.AMAZON: ("amazon.in", "amazon.com"),
    Marketplace.FLIPKART: ("flipkart.com",),
}


def validate_marketplace_url(value: str, marketplace: Marketplace) -> str | None:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    allowed = _ALLOWED_HOSTS[marketplace]
    if not any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed):
        return None
    return value
