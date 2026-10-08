import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_registration_login_authorization_and_password_storage(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_DATABASE_URL", "sqlite:///unused-auth-test.db")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret-with-at-least-32-bytes")

    from auth.api.router import get_session
    from auth.infrastructure.database import Base
    from auth.infrastructure.models import UserRecord
    from auth.main import app
    from auth.settings import settings

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    password = "correct-horse-battery-staple"
    try:
        with TestClient(app) as client:
            unauthenticated = client.get("/v1/auth/me")
            assert unauthenticated.status_code == 401

            registered = client.post(
                "/v1/auth/register", json={"username": "Demo.User", "password": password}
            )
            assert registered.status_code == 201
            customer_token = registered.json()["accessToken"]
            user_id = UUID(registered.json()["userId"])

            with sessions() as session:
                user = session.get(UserRecord, user_id)
                assert user is not None
                assert user.username == "demo.user"
                assert user.password_hash != password
                assert password not in user.password_hash

            profile = client.get(
                "/v1/auth/me", headers={"Authorization": f"Bearer {customer_token}"}
            )
            assert profile.status_code == 200
            assert profile.json() == {
                "userId": str(user_id),
                "username": "demo.user",
                "role": "customer",
            }

            bad_login = client.post(
                "/v1/auth/login", json={"username": "demo.user", "password": "incorrect-password"}
            )
            assert bad_login.status_code == 401

            duplicate = client.post(
                "/v1/auth/register", json={"username": "demo.user", "password": password}
            )
            assert duplicate.status_code == 409

            monkeypatch.setattr(settings, "engineering_operator_ids", str(user_id))
            operator_login = client.post(
                "/v1/auth/login", json={"username": "demo.user", "password": password}
            )
            assert operator_login.status_code == 200
            operator_profile = client.get(
                "/v1/auth/me",
                headers={"Authorization": f"Bearer {operator_login.json()['accessToken']}"},
            )
            assert operator_profile.status_code == 200
            assert operator_profile.json()["role"] == "operator"

            invalid_registration = client.post(
                "/v1/auth/register", json={"username": "x", "password": "short"}
            )
            assert invalid_registration.status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_openapi_contract_paths_methods_responses_and_gateway_exposure_match_apps() -> None:
    import yaml

    from auth.main import app as auth_app
    from catalog.main import app as catalog_app
    from inventory.main import app as inventory_app
    from orders.main import app as orders_app
    from payments.main import app as payments_app
    from gateway.main import ROUTES, _is_under

    contract_path = Path(__file__).parents[1] / "contracts" / "openapi" / "shop-easy-v1.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    apps = {
        "auth": auth_app,
        "catalog": catalog_app,
        "inventory": inventory_app,
        "orders": orders_app,
        "payments": payments_app,
    }
    route_owners = {
        "/auth": "auth",
        "/products": "catalog",
        "/categories": "catalog",
        "/carts": "orders",
        "/checkout": "orders",
        "/orders": "orders",
        "/payments": "payments",
        "/inventory": "inventory",
    }
    app_specs = {name: app.openapi() for name, app in apps.items()}

    for path, operations in contract["paths"].items():
        owner = next(
            (
                service
                for prefix, service in route_owners.items()
                if path == prefix or path.startswith(prefix + "/")
            ),
            None,
        )
        assert owner is not None, f"No service ownership for contract path {path}"
        implementation_path = re.sub(r"\{[^}]+\}", "{}", f"/v1{path}")
        implemented = next(
            (
                operations
                for implemented_path, operations in app_specs[owner]["paths"].items()
                if re.sub(r"\{[^}]+\}", "{}", implemented_path) == implementation_path
            ),
            {},
        )
        for method, operation in operations.items():
            assert method in implemented, f"{method.upper()} {path} is missing from {owner} OpenAPI"
            contract_success = {
                code for code in operation["responses"] if str(code).startswith("2")
            }
            app_success = set(implemented[method]["responses"])
            assert contract_success & app_success, f"{method.upper()} {path} success status differs"
            if not operation.get("x-internal", False):
                public_path = f"/v1{path}"
                assert any(_is_under(public_path, prefix) for prefix, _ in ROUTES), (
                    f"Public contract path {path} is not routed by the gateway"
                )


def test_gateway_rejects_customer_route_without_a_bearer_token() -> None:
    from gateway.main import FORWARDED_RESPONSE_HEADERS, app

    with TestClient(app) as client:
        response = client.get("/v1/orders")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "www-authenticate" in FORWARDED_RESPONSE_HEADERS
