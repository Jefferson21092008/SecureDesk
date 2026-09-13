from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole

PASSWORD = "StrongPass123!"


def create_user_and_token(client: TestClient, email: str) -> str:
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ticket(
    client: TestClient,
    token: str,
    *,
    title: str,
    description: str = "Generic service desk problem",
    priority: str = "MEDIUM",
) -> dict:
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": title,
            "description": description,
            "priority": priority,
        },
    )
    assert response.status_code == 201
    return response.json()


def make_agent(client: TestClient, db: Session, email: str = "agent-query@example.com") -> str:
    create_user_and_token(client, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = UserRole.AGENT
    db.commit()

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_ticket_list_is_paginated(client: TestClient) -> None:
    token = create_user_and_token(client, "pagination@example.com")
    for index in range(5):
        create_ticket(client, token, title=f"Ticket number {index}")

    response = client.get("/tickets?page=2&page_size=2&sort_by=id&sort_order=asc", headers=auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    assert payload["total"] == 5
    assert payload["pages"] == 3
    assert [item["title"] for item in payload["items"]] == ["Ticket number 2", "Ticket number 3"]


def test_ticket_list_filters_by_status(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "status-owner@example.com")
    first = create_ticket(client, owner_token, title="Open ticket")
    second = create_ticket(client, owner_token, title="In progress ticket")
    agent_token = make_agent(client, db, "status-agent@example.com")

    update = client.patch(
        f"/tickets/{second['id']}",
        headers=auth(agent_token),
        json={"status": "IN_PROGRESS"},
    )
    assert update.status_code == 200

    response = client.get("/tickets?status=IN_PROGRESS", headers=auth(agent_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == second["id"]
    assert payload["items"][0]["id"] != first["id"]


def test_ticket_list_filters_by_priority(client: TestClient) -> None:
    token = create_user_and_token(client, "priority@example.com")
    create_ticket(client, token, title="Low priority", priority="LOW")
    high = create_ticket(client, token, title="High priority", priority="HIGH")

    response = client.get("/tickets?priority=HIGH", headers=auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == high["id"]


def test_ticket_search_matches_title_case_insensitively(client: TestClient) -> None:
    token = create_user_and_token(client, "search-title@example.com")
    match = create_ticket(client, token, title="VPN Access Failure")
    create_ticket(client, token, title="Printer offline")

    response = client.get("/tickets?search=vpn", headers=auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == match["id"]


def test_ticket_search_matches_description(client: TestClient) -> None:
    token = create_user_and_token(client, "search-description@example.com")
    match = create_ticket(
        client,
        token,
        title="Workstation issue",
        description="The accounting workstation cannot connect to SAP.",
    )
    create_ticket(client, token, title="Mouse issue", description="Mouse button is broken.")

    response = client.get("/tickets?search=accounting", headers=auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == match["id"]


def test_querying_never_exposes_another_users_tickets(client: TestClient) -> None:
    first_token = create_user_and_token(client, "scope-first@example.com")
    second_token = create_user_and_token(client, "scope-second@example.com")
    first = create_ticket(client, first_token, title="Shared search word alpha")
    second = create_ticket(client, second_token, title="Shared search word alpha")

    response = client.get("/tickets?search=alpha", headers=auth(first_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == first["id"]
    assert payload["items"][0]["id"] != second["id"]


def test_agent_can_query_tickets_from_all_users(client: TestClient, db: Session) -> None:
    first_token = create_user_and_token(client, "all-first@example.com")
    second_token = create_user_and_token(client, "all-second@example.com")
    create_ticket(client, first_token, title="Network alpha")
    create_ticket(client, second_token, title="Network alpha")
    agent_token = make_agent(client, db, "all-agent@example.com")

    response = client.get("/tickets?search=alpha", headers=auth(agent_token))

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_ticket_list_sorts_by_title_ascending(client: TestClient) -> None:
    token = create_user_and_token(client, "sort-title@example.com")
    create_ticket(client, token, title="Zulu issue")
    create_ticket(client, token, title="Alpha issue")
    create_ticket(client, token, title="Middle issue")

    response = client.get("/tickets?sort_by=title&sort_order=asc", headers=auth(token))

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Alpha issue", "Middle issue", "Zulu issue"]


def test_ticket_list_sorts_by_id_descending(client: TestClient) -> None:
    token = create_user_and_token(client, "sort-id@example.com")
    first = create_ticket(client, token, title="First issue")
    second = create_ticket(client, token, title="Second issue")

    response = client.get("/tickets?sort_by=id&sort_order=desc", headers=auth(token))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [second["id"], first["id"]]


def test_query_parameters_are_validated(client: TestClient) -> None:
    token = create_user_and_token(client, "invalid-query@example.com")

    bad_page = client.get("/tickets?page=0", headers=auth(token))
    bad_page_size = client.get("/tickets?page_size=101", headers=auth(token))
    bad_sort = client.get("/tickets?sort_by=unknown", headers=auth(token))

    assert bad_page.status_code == 422
    assert bad_page_size.status_code == 422
    assert bad_sort.status_code == 422
