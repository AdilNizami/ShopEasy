from enum import StrEnum


class PaymentOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class MockPaymentProvider:
    """Deterministic provider used only by the local learning application."""

    def authorize(self, payment_method_token: str) -> PaymentOutcome:
        if payment_method_token == "mock-success":
            return PaymentOutcome.CONFIRMED
        if payment_method_token == "mock-failure":
            return PaymentOutcome.FAILED
        raise ValueError("Use mock-success or mock-failure with the mock provider.")
