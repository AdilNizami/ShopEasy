from orders.domain.entities import OrderStatus

ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.PROCESSING},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def transition_order(current: str, target: OrderStatus) -> str:
    try:
        current_status = OrderStatus(current)
    except ValueError as exc:
        raise ValueError("Unknown current order status.") from exc
    if target not in ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(f"Order cannot move from {current_status} to {target}.")
    return target.value
