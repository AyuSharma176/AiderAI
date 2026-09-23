"""Deterministic marketplace email parsers."""

from app.orders.parsers.amazon import AmazonOrderParser
from app.orders.parsers.base import OrderEmailParser
from app.orders.parsers.flipkart import FlipkartOrderParser

PARSER_REGISTRY: tuple[OrderEmailParser, ...] = (
    AmazonOrderParser(),
    FlipkartOrderParser(),
)

__all__ = ["PARSER_REGISTRY", "AmazonOrderParser", "FlipkartOrderParser"]
