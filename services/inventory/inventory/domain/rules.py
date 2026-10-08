class InsufficientStock(ValueError):
    pass


def available_quantity(on_hand: int, reserved: int) -> int:
    if on_hand < 0 or reserved < 0 or reserved > on_hand:
        raise ValueError("Stock counts are inconsistent.")
    return on_hand - reserved


def ensure_available(on_hand: int, reserved: int, requested: int) -> None:
    if requested < 1:
        raise ValueError("Requested quantity must be positive.")
    if requested > available_quantity(on_hand, reserved):
        raise InsufficientStock("Insufficient stock.")
