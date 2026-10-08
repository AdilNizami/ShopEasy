from decimal import Decimal

MAX_CART_ITEM_QUANTITY = 99


def updated_quantity(existing: int, requested: int) -> int:
    if existing < 0 or requested < 1:
        raise ValueError("Cart quantities must be positive.")
    quantity = existing + requested
    if quantity > MAX_CART_ITEM_QUANTITY:
        raise ValueError(f"A product quantity cannot exceed {MAX_CART_ITEM_QUANTITY}.")
    return quantity


def calculate_cart_total(items: list[tuple[int, Decimal, str]]) -> tuple[Decimal, str | None]:
    currencies = {currency for _, _, currency in items}
    if len(currencies) > 1:
        raise ValueError("All cart products must use the same currency.")
    total = sum((amount * quantity for quantity, amount, _ in items), Decimal("0"))
    return total, next(iter(currencies), None)
