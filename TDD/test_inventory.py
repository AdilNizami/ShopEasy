
import pytest
from inventory import get_available_stock

def test_available_stock_excludes_reserved_items():
    # Arrange
    total_stock = 10
    reserved_stock = 3

    # Act
    available_stock = get_available_stock(total_stock, reserved_stock)

    # Assert
    assert available_stock == 7


def test_zero_available_stock():
    # Arrange
    total_stock = 10
    reserved_stock = 10

    # Act
    available_stock = get_available_stock(total_stock, reserved_stock)

    # Assert
    assert available_stock == 0


def test_negative_stock_is_rejected():
    with pytest.raises(ValueError):
        get_available_stock(-5, 0)


def test_reserved_stock_cannot_exceed_total_stock():
    with pytest.raises(ValueError):
        get_available_stock(5, 8)
        

def test_zero_total_and_zero_reserved_stock():
    assert get_available_stock(0, 0) == 0


def test_all_stock_reserved_returns_zero():
    assert get_available_stock(5, 5) == 0
