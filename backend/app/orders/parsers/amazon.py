from email.utils import parseaddr

from app.models import CommerceOrderStatus, Marketplace, OrderEventType
from app.orders.parsers.base import (
    first_match,
    normalize_amount,
    parse_items,
    validate_marketplace_url,
)
from app.orders.types import CommerceEmail, OrderItemObservation, OrderObservation


class AmazonOrderParser:
    name = "amazon"
    version = "1"

    def matches(self, email: CommerceEmail) -> bool:
        address = parseaddr(email.sender)[1].lower()
        domain = address.rpartition("@")[2]
        return domain in {"amazon.in", "amazon.com"} or domain.endswith(
            (".amazon.in", ".amazon.com")
        )

    def parse(self, email: CommerceEmail) -> list[OrderObservation]:
        if not self.matches(email):
            return []
        content = f"{email.subject} {email.text}"
        order_id = first_match(r"\b(\d{3}-\d{7}-\d{7})\b", content)
        event = self._event(content)
        if not order_id or event is None:
            return []
        url = first_match(r"(https://[^\s<>]+)", email.text)
        items = [
            OrderItemObservation(title=title, quantity=quantity)
            for title, quantity in parse_items(email.text)
        ]
        amount = first_match(r"(?:Total|Order total):\s*(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", content)
        tracking = first_match(r"Tracking (?:ID|number):\s*([A-Za-z0-9-]+)", content)
        carrier = first_match(r"Carrier:\s*(.+?)(?=\s+https://|$)", content)
        status = CommerceOrderStatus(event.value)
        return [
            OrderObservation(
                marketplace=Marketplace.AMAZON,
                marketplace_order_id=order_id,
                event_type=event,
                occurred_at=email.sent_at,
                status=status,
                items=items,
                currency="INR" if amount else None,
                total_amount=normalize_amount(amount),
                delivered_at=(
                    email.sent_at if status == CommerceOrderStatus.DELIVERED else None
                ),
                tracking_number=tracking,
                carrier=carrier,
                marketplace_url=(
                    validate_marketplace_url(url, Marketplace.AMAZON) if url else None
                ),
            )
        ]

    @staticmethod
    def _event(content: str) -> OrderEventType | None:
        lowered = content.lower()
        mappings = (
            ("cancel", OrderEventType.CANCELLED),
            ("out for delivery", OrderEventType.OUT_FOR_DELIVERY),
            ("delivered", OrderEventType.DELIVERED),
            ("shipped", OrderEventType.SHIPPED),
            ("confirmed", OrderEventType.PLACED),
        )
        return next((event for marker, event in mappings if marker in lowered), None)
