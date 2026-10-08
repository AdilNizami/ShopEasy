from decimal import Decimal

import pytest
from inventory.domain.rules import InsufficientStock, available_quantity, ensure_available
from orders.domain.cart_rules import calculate_cart_total, updated_quantity
from orders.domain.entities import OrderStatus
from orders.domain.state import transition_order
from payments.domain.mock_provider import MockPaymentProvider, PaymentOutcome


def test_cart_quantity_is_capped_and_positive() -> None:
    assert updated_quantity(2, 3) == 5
    with pytest.raises(ValueError):
        updated_quantity(99, 1)
    with pytest.raises(ValueError):
        updated_quantity(0, 0)


def test_cart_total_uses_decimal_and_rejects_mixed_currencies() -> None:
    assert calculate_cart_total([(2, Decimal("1.25"), "USD")]) == (Decimal("2.50"), "USD")
    with pytest.raises(ValueError, match="same currency"):
        calculate_cart_total([(1, Decimal("1"), "USD"), (1, Decimal("1"), "EUR")])


def test_inventory_reservation_cannot_exceed_available_stock() -> None:
    assert available_quantity(8, 3) == 5
    ensure_available(8, 3, 5)
    with pytest.raises(InsufficientStock):
        ensure_available(8, 3, 6)


def test_order_status_transitions_are_guarded() -> None:
    assert transition_order("PENDING_PAYMENT", OrderStatus.PAID) == "PAID"
    with pytest.raises(ValueError):
        transition_order("CANCELLED", OrderStatus.PAID)


def test_mock_payment_provider_has_deterministic_outcomes() -> None:
    provider = MockPaymentProvider()
    assert provider.authorize("mock-success") is PaymentOutcome.CONFIRMED
    assert provider.authorize("mock-failure") is PaymentOutcome.FAILED
    with pytest.raises(ValueError):
        provider.authorize("card-number")
