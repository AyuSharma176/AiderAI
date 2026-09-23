import base64

import pytest

from app.integrations.gmail.types import GmailRawMessage
from app.models import Marketplace
from app.orders.parsers.base import (
    MalformedMessageError,
    MessageTooLargeError,
    normalize_message,
    validate_marketplace_url,
)


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def raw_message(payload: dict) -> GmailRawMessage:
    return GmailRawMessage.model_validate(
        {
            "id": "m1",
            "historyId": "10",
            "internalDate": "1758715200000",
            "payload": {
                "headers": [
                    {"name": "From", "value": "shipment@amazon.in"},
                    {"name": "Subject", "value": "Order update"},
                ],
                **payload,
            },
        }
    )


def test_normalizer_rejects_oversized_message() -> None:
    raw = raw_message({"mimeType": "text/plain", "body": {"data": encoded(b"x" * 101)}})

    with pytest.raises(MessageTooLargeError):
        normalize_message(raw, max_bytes=100)


def test_normalizer_strips_scripts_and_ignores_attachments() -> None:
    raw = raw_message(
        {
            "mimeType": "multipart/mixed",
            "body": {},
            "parts": [
                {
                    "mimeType": "text/html",
                    "filename": "",
                    "body": {
                        "data": encoded(b"<script>steal()</script><p>Order A-1</p>")
                    },
                },
                {
                    "mimeType": "text/plain",
                    "filename": "secret.txt",
                    "body": {"data": encoded(b"attachment secret")},
                },
            ],
        }
    )

    email = normalize_message(raw, max_bytes=1000)

    assert "steal" not in email.text
    assert "Order A-1" in email.text
    assert "secret" not in email.text


def test_normalizer_rejects_malformed_base64() -> None:
    raw = raw_message({"mimeType": "text/plain", "body": {"data": "!!!!"}})

    with pytest.raises(MalformedMessageError):
        normalize_message(raw, max_bytes=1000)


@pytest.mark.parametrize(
    ("value", "marketplace", "expected"),
    [
        ("https://www.amazon.in/gp/order-details", Marketplace.AMAZON, True),
        ("https://flipkart.com/order_details", Marketplace.FLIPKART, True),
        ("http://amazon.in/order", Marketplace.AMAZON, False),
        ("https://amazon.in.evil.example/order", Marketplace.AMAZON, False),
        ("https://evilflipkart.com/order", Marketplace.FLIPKART, False),
    ],
)
def test_marketplace_url_validation_is_exact(
    value: str, marketplace: Marketplace, expected: bool
) -> None:
    assert (validate_marketplace_url(value, marketplace) is not None) is expected
