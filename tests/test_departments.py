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


def make_role(client: TestClient, db: Session, email: str, role: UserRole) -> str:
    register_and_token(client, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = role
    db.commit()
    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def create_department(
    client: TestClient,
    admin_token: str,
    name: str = "Infrastructure",
    description: str | None = "Infrastructure support queue",
) -> dict:
    response = client.post(
        "/departments",
        headers=auth(admin_token),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()


def test_department_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/departments").status_code == 401
    assert client.post("/departments", json={"name": "Infrastructure"}).status_code == 401


def test_only_admin_can_manage_departments(client: TestClient) -> None:
    user_token = register_and_token(client, "department-user@example.com")
    response = client.post(
        "/departments",
        headers=auth(user_token),
        json={"name": "Infrastructure"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only admins can manage departments"


def test_admin_can_create_list_get_update_and_delete_department(
    client: TestClient,
    db: Session,
) -> None:
    admin_token = make_role(client, db, "department-admin@example.com", UserRole.ADMIN)
    created = create_department(client, admin_token)

    listed = client.get("/departments", headers=auth(admin_token))
    fetched = client.get(f"/departments/{created['id']}", headers=auth(admin_token))
    updated = client.patch(
        f"/departments/{created['id']}",
        headers=auth(admin_token),
        json={"name": "Platform", "description": "Platform support queue"},
    )
    deleted = client.delete(f"/departments/{created['id']}", headers=auth(admin_token))

    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Infrastructure"
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert updated.status_code == 200
    assert updated.json()["name"] == "Platform"
    assert deleted.status_code == 204


def test_department_name_is_unique_case_insensitively(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "duplicate-department-admin@example.com", UserRole.ADMIN)
    create_department(client, admin_token, name="Network")
    duplicate = client.post(
        "/departments",
        headers=auth(admin_token),
        json={"name": "network"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Department name already exists"


def test_user_can_create_ticket_with_existing_department(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "ticket-department-admin@example.com", UserRole.ADMIN)
    department = create_department(client, admin_token, name="Service Desk")
    user_token = register_and_token(client, "ticket-department-user@example.com")

    response = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Cannot access workstation",
            "description": "The workstation cannot authenticate to the domain",
            "department_id": department["id"],
        },
    )
    assert response.status_code == 201
    assert response.json()["department_id"] == department["id"]


def test_ticket_rejects_unknown_department(client: TestClient) -> None:
    user_token = register_and_token(client, "unknown-department@example.com")
    response = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Unknown department ticket",
            "description": "This ticket references a department that does not exist",
            "department_id": 999,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Department not found"


def test_ticket_list_filters_by_department(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "filter-department-admin@example.com", UserRole.ADMIN)
    infrastructure = create_department(client, admin_token, name="Infrastructure")
    applications = create_department(client, admin_token, name="Applications")
    user_token = register_and_token(client, "filter-department-user@example.com")

    for title, department_id in [
        ("Server unavailable", infrastructure["id"]),
        ("ERP error", applications["id"]),
    ]:
        response = client.post(
            "/tickets",
            headers=auth(user_token),
            json={
                "title": title,
                "description": "Department filtering test ticket",
                "department_id": department_id,
            },
        )
        assert response.status_code == 201

    filtered = client.get(
        f"/tickets?department_id={infrastructure['id']}",
        headers=auth(user_token),
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Server unavailable"


def test_user_cannot_change_department_after_creation(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "routing-admin@example.com", UserRole.ADMIN)
    first = create_department(client, admin_token, name="Infrastructure")
    second = create_department(client, admin_token, name="Applications")
    user_token = register_and_token(client, "routing-user@example.com")

    created = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Routing test",
            "description": "Ticket used to verify department routing permissions",
            "department_id": first["id"],
        },
    )
    ticket_id = created.json()["id"]

    response = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(user_token),
        json={"department_id": second["id"]},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Users cannot change ticket department"


def test_agent_can_change_and_remove_ticket_department(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "agent-routing-admin@example.com", UserRole.ADMIN)
    first = create_department(client, admin_token, name="Infrastructure")
    second = create_department(client, admin_token, name="Applications")
    user_token = register_and_token(client, "agent-routing-user@example.com")
    agent_token = make_role(client, db, "routing-agent@example.com", UserRole.AGENT)

    created = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Agent routing test",
            "description": "Agent should be able to route this ticket",
            "department_id": first["id"],
        },
    )
    ticket_id = created.json()["id"]

    changed = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(agent_token),
        json={"department_id": second["id"]},
    )
    removed = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(agent_token),
        json={"department_id": None},
    )

    assert changed.status_code == 200
    assert changed.json()["department_id"] == second["id"]
    assert removed.status_code == 200
    assert removed.json()["department_id"] is None


def test_department_change_is_recorded_in_ticket_history(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "history-department-admin@example.com", UserRole.ADMIN)
    department = create_department(client, admin_token, name="Security")
    user_token = register_and_token(client, "history-department-user@example.com")
    agent_token = make_role(client, db, "history-department-agent@example.com", UserRole.AGENT)

    created = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Security routing",
            "description": "Ticket used to verify department history",
        },
    )
    ticket_id = created.json()["id"]

    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(agent_token),
        json={"department_id": department["id"]},
    )
    assert update.status_code == 200

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth(user_token))
    assert history.status_code == 200
    entries = [entry for entry in history.json() if entry["field"] == "department_id"]
    assert len(entries) == 1
    assert entries[0]["action"] == "UPDATED"
    assert entries[0]["old_value"] is None
    assert entries[0]["new_value"] == str(department["id"])


def test_department_in_use_cannot_be_deleted(client: TestClient, db: Session) -> None:
    admin_token = make_role(client, db, "delete-department-admin@example.com", UserRole.ADMIN)
    department = create_department(client, admin_token, name="Operations")
    user_token = register_and_token(client, "delete-department-user@example.com")

    ticket = client.post(
        "/tickets",
        headers=auth(user_token),
        json={
            "title": "Operations incident",
            "description": "Ticket keeps this department in use",
            "department_id": department["id"],
        },
    )
    assert ticket.status_code == 201

    response = client.delete(
        f"/departments/{department['id']}",
        headers=auth(admin_token),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Department is in use by tickets"
