import json
from pathlib import Path

from app.models import CommerceOrderStatus
from app.orders.parsers.flipkart import FlipkartOrderParser
from app.orders.types import CommerceEmail

FIXTURES = Path(__file__).parents[1] / "fixtures" / "orders"


def load_fixture(name: str) -> CommerceEmail:
    return CommerceEmail.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def test_flipkart_placed_extracts_items_and_total() -> None:
    observation = FlipkartOrderParser().parse(load_fixture("flipkart_order_placed.json"))[0]

    assert observation.marketplace_order_id == "OD123456789012345678"
    assert observation.items[0].title == "Wireless mouse"
    assert observation.items[0].quantity == 2
    assert observation.total_amount == "799.00"
    assert observation.status == CommerceOrderStatus.PLACED


def test_flipkart_delivered_maps_status() -> None:
    observation = FlipkartOrderParser().parse(load_fixture("flipkart_delivered.json"))[0]

    assert observation.status == CommerceOrderStatus.DELIVERED
    assert observation.delivered_at == observation.occurred_at


def test_flipkart_template_without_order_id_is_skipped() -> None:
    email = load_fixture("flipkart_delivered.json").model_copy(
        update={"subject": "Delivered", "text": "Your item was delivered"}
    )

    assert FlipkartOrderParser().parse(email) == []


def test_flipkart_rejects_unrelated_sender() -> None:
    email = load_fixture("flipkart_delivered.json").model_copy(
        update={"sender": "updates@flipkart.com.evil.example"}
    )

    assert not FlipkartOrderParser().matches(email)
