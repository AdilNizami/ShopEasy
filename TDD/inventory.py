

def get_available_stock(total_stock, reserved_stock):
    if total_stock < 0 or reserved_stock < 0:
        raise ValueError("Stock quantities cannot be negative")

    if reserved_stock > total_stock:
        raise ValueError("Reserved stock cannot exceed total stock")

    return total_stock - reserved_stock
