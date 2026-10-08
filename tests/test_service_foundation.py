from __future__ import annotations

import ast
import importlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service_common.logging import JsonFormatter, correlation_id_var

SERVICE_MODULES = (
    "catalog.main",
    "orders.main",
    "payments.main",
    "inventory.main",
    "notifications.main",
    "auth.main",
)


@pytest.fixture(params=SERVICE_MODULES)
def service_client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    app_module = importlib.import_module(request.param)
    app = app_module.app
    assert isinstance(app, FastAPI)
    with TestClient(app) as client:
        yield client


def test_liveness_is_available_for_each_service(service_client: TestClient) -> None:
    response = service_client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Correlation-ID"]


def test_valid_correlation_id_is_propagated(service_client: TestClient) -> None:
    correlation_id = "4b9d0858-b529-4d8d-b848-63f5041c3e0e"

    response = service_client.get("/health/live", headers={"X-Correlation-ID": correlation_id})

    assert response.headers["X-Correlation-ID"] == correlation_id


def test_structured_logs_include_the_active_correlation_id() -> None:
    correlation_id = "4b9d0858-b529-4d8d-b848-63f5041c3e0e"
    token = correlation_id_var.set(correlation_id)
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "request done", (), None)
        document = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id_var.reset(token)

    assert document["correlationId"] == correlation_id


def test_missing_resource_uses_structured_error(service_client: TestClient) -> None:
    response = service_client.get("/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["correlationId"] == response.headers["X-Correlation-ID"]


def test_catalog_validates_product_id_without_database_access() -> None:
    app = importlib.import_module("catalog.main").app
    with TestClient(app) as client:
        response = client.get("/v1/products/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_orders_validates_checkout_before_unavailable_workflow() -> None:
    app = importlib.import_module("orders.main").app
    with TestClient(app) as client:
        response = client.post(
            "/v1/checkout",
            headers={"Idempotency-Key": "checkout-test-key"},
            json={"items": []},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_payment_request_is_validated_before_provider_workflow() -> None:
    app = importlib.import_module("payments.main").app
    with TestClient(app) as client:
        response = client.post(
            "/v1/payments",
            headers={"Idempotency-Key": "payment-test-key"},
            json={"orderId": "not-a-uuid", "paymentMethodToken": "provider-token"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_inventory_request_is_validated_before_reservation_workflow() -> None:
    app = importlib.import_module("inventory.main").app
    with TestClient(app) as client:
        response = client.post(
            "/v1/inventory/reservations",
            headers={"Idempotency-Key": "inventory-test-key"},
            json={"orderId": "4b9d0858-b529-4d8d-b848-63f5041c3e0e", "items": []},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_each_service_declares_only_its_owned_tables() -> None:
    import auth.infrastructure.models  # noqa: F401
    import catalog.infrastructure.models  # noqa: F401
    import inventory.infrastructure.models  # noqa: F401
    import notifications.infrastructure.models  # noqa: F401
    import orders.infrastructure.models  # noqa: F401
    import payments.infrastructure.models  # noqa: F401
    from auth.infrastructure.database import Base as AuthBase
    from catalog.infrastructure.database import Base as CatalogBase
    from inventory.infrastructure.database import Base as InventoryBase
    from notifications.infrastructure.database import Base as NotificationsBase
    from orders.infrastructure.database import Base as OrdersBase
    from payments.infrastructure.database import Base as PaymentsBase

    assert set(CatalogBase.metadata.tables) == {"products", "categories", "product_details"}
    assert set(AuthBase.metadata.tables) == {"users"}
    assert set(OrdersBase.metadata.tables) == {
        "orders",
        "order_lines",
        "carts",
        "cart_items",
        "checkout_requests",
        "outbox_events",
        "inbox_events",
    }
    assert set(PaymentsBase.metadata.tables) == {
        "payment_attempts",
        "payment_requests",
        "outbox_events",
    }
    assert set(InventoryBase.metadata.tables) == {
        "stock",
        "reservations",
        "reservation_items",
        "reservation_requests",
    }
    assert set(NotificationsBase.metadata.tables) == {"notification_events"}
    assert (
        len(
            {
                id(CatalogBase.metadata),
                id(AuthBase.metadata),
                id(OrdersBase.metadata),
                id(PaymentsBase.metadata),
                id(InventoryBase.metadata),
                id(NotificationsBase.metadata),
            }
        )
        == 6
    )


def test_compose_gives_each_bounded_context_a_distinct_database() -> None:
    import yaml

    compose_path = Path(__file__).parents[1] / "compose.yaml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service_names = ("catalog", "orders", "payments", "inventory", "notifications", "auth")

    configured_database_variables = []
    for service_name in service_names:
        environment = compose["services"][service_name]["environment"]
        variable_name = f"{service_name.upper()}_DATABASE_URL"
        database_url = environment.get("AUTH_DATABASE_URL", environment.get("DATABASE_URL"))
        assert variable_name in database_url
        if service_name != "auth":
            assert f"@postgres:5432/{service_name}" in database_url
        configured_database_variables.append(variable_name)

    assert len(configured_database_variables) == len(set(configured_database_variables))

    for service_name in ("catalog", "orders", "payments", "gateway"):
        assert "AUTH_JWT_SECRET" in compose["services"][service_name]["environment"]


def test_application_containers_run_without_root_and_frontend_copy_source_exists() -> None:
    repository = Path(__file__).parents[1]
    backend_dockerfile = (repository / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (repository / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "USER app" in backend_dockerfile
    assert "USER node" in frontend_dockerfile
    assert "RUN mkdir -p public" in frontend_dockerfile


def test_services_do_not_import_each_others_packages() -> None:
    service_names = {"auth", "catalog", "orders", "payments", "inventory", "notifications"}
    services_root = Path(__file__).parents[1] / "services"

    for service_name in service_names:
        package_root = services_root / service_name / service_name
        for source_path in package_root.rglob("*.py"):
            syntax_tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots = {node.module.split(".")[0]}
                else:
                    continue
                assert not (imported_roots & (service_names - {service_name})), source_path


def test_orders_schema_migration_is_owned_by_orders_context() -> None:
    repository = Path(__file__).parents[1]
    common_migrations = (
        repository / "services" / "common" / "service_common" / "outbox_migration.py"
    ).read_text(encoding="utf-8")
    orders_migrations = (
        repository / "services" / "orders" / "orders" / "infrastructure" / "migrations.py"
    ).read_text(encoding="utf-8")

    assert "ensure_order_owner_columns" not in common_migrations
    assert "ALTER TABLE orders" in orders_migrations
    assert "ensure_inbox_correlation_column" in orders_migrations


def test_operational_views_preserve_external_event_producers() -> None:
    from notifications.main import _event_producer as notification_producer
    from orders.main import _event_producer as order_producer

    assert order_producer("PaymentConfirmed") == "payments"
    assert order_producer("OrderShipped") == "shipping"
    assert notification_producer("OrderPaid") == "orders"
    assert notification_producer("OrderDelivered") == "shipping"
