from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole

PASSWORD = "StrongPass123!"


def register_and_token(client: TestClient, email: str) -> str:
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201
    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_admin(client: TestClient, db: Session, email: str = "admin-category@example.com") -> str:
    register_and_token(client, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = UserRole.ADMIN
    db.commit()

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def create_category(
    client: TestClient,
    admin_token: str,
    name: str = "Hardware",
    description: str | None = "Physical device incidents",
) -> dict:
    response = client.post(
        "/categories",
        headers=auth(admin_token),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()


def test_category_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/categories").status_code == 401
    assert client.post("/categories", json={"name": "Hardware"}).status_code == 401


def test_only_admin_can_manage_categories(client: TestClient) -> None:
    user_token = register_and_token(client, "category-user@example.com")

    response = client.post(
        "/categories",
        headers=auth(user_token),
        json={"name": "Hardware"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only admins can manage categories"


def test_admin_can_create_list_get_update_and_delete_category(
    client: TestClient,
    db: Session,
) -> None:
    admin_token = make_admin(client, db)
    created = create_category(client, admin_token)

    listed = client.get("/categories", headers=auth(admin_token))
    fetched = client.get(f"/categories/{created['id']}", headers=auth(admin_token))
    updated = client.patch(
        f"/categories/{created['id']}",
        headers=auth(admin_token),
        json={"name": "Devices", "description": "Laptops and peripherals"},
    )
    deleted = client.delete(f"/categories/{created['id']}", headers=auth(admin_token))

    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Hardware"
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert updated.status_code == 200
    assert updated.json()["name"] == "Devices"
    assert deleted.status_code == 204
    assert client.get(f"/categories/{created['id']}", headers=auth(admin_token)).status_code == 404


def test_category_name_is_unique_case_insensitively(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "duplicate-admin@example.com")
    create_category(client, admin_token, name="Network")

    duplicate = client.post(
        "/categories",
        headers=auth(admin_token),
        json={"name": "network"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Category name already exists"


def test_user_can_create_ticket_with_existing_category(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "ticket-category-admin@example.com")
    category = create_category(client, admin_token, name="Access")
    user_token = register_and_token(client, "ticket-category-user@example.com")

    response = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "VPN access issue",
            "description": "Unable to authenticate to corporate VPN",
            "priority": "HIGH",
            "category_id": category["id"],
        },
    )

    assert response.status_code == 201
    assert response.json()["category_id"] == category["id"]


def test_ticket_rejects_unknown_category(client: TestClient) -> None:
    user_token = register_and_token(client, "unknown-category@example.com")

    response = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Unknown category ticket",
            "description": "This ticket references a category that does not exist",
            "category_id": 999,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_ticket_list_filters_by_category(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "filter-category-admin@example.com")
    hardware = create_category(client, admin_token, name="Hardware")
    software = create_category(client, admin_token, name="Software")
    user_token = register_and_token(client, "filter-category-user@example.com")

    for title, category_id in [
        ("Broken keyboard", hardware["id"]),
        ("Application crash", software["id"]),
    ]:
        response = client.post(
            "/tickets",
            headers=auth(user_token),
            json={
                "title": title,
                "description": "Category filtering test ticket",
                "category_id": category_id,
            },
        )
        assert response.status_code == 201

    filtered = client.get(
        f"/tickets?category_id={hardware['id']}",
        headers=auth(user_token),
    )

    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Broken keyboard"


def test_ticket_category_can_be_changed_and_removed(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "change-category-admin@example.com")
    first = create_category(client, admin_token, name="Hardware")
    second = create_category(client, admin_token, name="Network")
    user_token = register_and_token(client, "change-category-user@example.com")

    created = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Category change",
            "description": "Ticket used to verify category reassignment",
            "category_id": first["id"],
        },
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    changed = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(user_token),
        json={"category_id": second["id"]},
    )
    removed = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(user_token),
        json={"category_id": None},
    )

    assert changed.status_code == 200
    assert changed.json()["category_id"] == second["id"]
    assert removed.status_code == 200
    assert removed.json()["category_id"] is None


def test_category_change_is_recorded_in_ticket_history(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "history-category-admin@example.com")
    category = create_category(client, admin_token, name="Security")
    user_token = register_and_token(client, "history-category-user@example.com")

    created = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Account lockout",
            "description": "User account is locked after failed authentication attempts",
        },
    )
    ticket_id = created.json()["id"]

    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(user_token),
        json={"category_id": category["id"]},
    )
    assert update.status_code == 200

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth(user_token))
    assert history.status_code == 200
    category_entries = [entry for entry in history.json() if entry["field"] == "category_id"]
    assert len(category_entries) == 1
    assert category_entries[0]["action"] == "UPDATED"
    assert category_entries[0]["old_value"] is None
    assert category_entries[0]["new_value"] == str(category["id"])


def test_category_in_use_cannot_be_deleted(client: TestClient, db: Session) -> None:
    admin_token = make_admin(client, db, "delete-category-admin@example.com")
    category = create_category(client, admin_token, name="Infrastructure")
    user_token = register_and_token(client, "delete-category-user@example.com")

    ticket = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Server unavailable",
            "description": "Production application server cannot be reached",
            "category_id": category["id"],
        },
    )
    assert ticket.status_code == 201

    response = client.delete(
        f"/categories/{category['id']}",
        headers=auth(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Category is in use by tickets"
