import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import CommerceOrderStatus, Marketplace, OrderEventType
from app.orders.parsers.amazon import AmazonOrderParser
from app.orders.types import CommerceEmail, OrderItemObservation, OrderObservation

FIXTURES = Path(__file__).parents[1] / "fixtures" / "orders"


def load_fixture(name: str) -> CommerceEmail:
    return CommerceEmail.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def test_amazon_shipment_extracts_required_and_optional_facts() -> None:
    observations = AmazonOrderParser().parse(load_fixture("amazon_shipped.json"))

    assert observations == [
        OrderObservation(
            marketplace=Marketplace.AMAZON,
            marketplace_order_id="402-0000000-0000000",
            event_type=OrderEventType.SHIPPED,
            occurred_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
            status=CommerceOrderStatus.SHIPPED,
            items=[OrderItemObservation(title="USB-C charger", quantity=1)],
            marketplace_url=(
                "https://www.amazon.in/gp/your-account/order-details"
                "?orderID=402-0000000-0000000"
            ),
            tracking_number="AMZTRACK1",
            carrier="Amazon Transportation Services",
        )
    ]


def test_amazon_placed_extracts_indian_locale_total() -> None:
    observation = AmazonOrderParser().parse(load_fixture("amazon_order_placed.json"))[0]

    assert observation.total_amount == "1299.00"
    assert observation.currency == "INR"
    assert observation.status == CommerceOrderStatus.PLACED


def test_amazon_template_without_order_id_is_skipped() -> None:
    email = load_fixture("amazon_shipped.json").model_copy(
        update={"subject": "Shipped", "text": "Your item has shipped"}
    )

    assert AmazonOrderParser().parse(email) == []


def test_amazon_rejects_unrelated_sender() -> None:
    email = load_fixture("amazon_shipped.json").model_copy(
        update={"sender": "attacker@amazon.in.evil.example"}
    )

    assert not AmazonOrderParser().matches(email)
