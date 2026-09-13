from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketStatus

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
    priority: str = "MEDIUM",
) -> dict:
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": title,
            "description": "SLA validation ticket",
            "priority": priority,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    ("priority", "target_hours"),
    [("HIGH", 4), ("MEDIUM", 8), ("LOW", 24)],
)
def test_ticket_creation_assigns_sla_by_priority(
    client: TestClient,
    priority: str,
    target_hours: int,
) -> None:
    token = create_user_and_token(client, f"sla-{priority.lower()}@example.com")
    ticket = create_ticket(client, token, title=f"{priority} SLA ticket", priority=priority)

    created_at = datetime.fromisoformat(ticket["created_at"])
    due_at = datetime.fromisoformat(ticket["sla_due_at"])

    assert ticket["sla_target_hours"] == target_hours
    assert due_at - created_at == timedelta(hours=target_hours)
    assert ticket["sla_status"] == "ON_TRACK"


def test_priority_change_recalculates_sla_from_original_creation(client: TestClient) -> None:
    token = create_user_and_token(client, "sla-recalculate@example.com")
    ticket = create_ticket(client, token, title="Priority change", priority="LOW")

    response = client.patch(
        f"/tickets/{ticket['id']}",
        headers=auth(token),
        json={"priority": "HIGH"},
    )

    assert response.status_code == 200
    updated = response.json()
    created_at = datetime.fromisoformat(updated["created_at"])
    due_at = datetime.fromisoformat(updated["sla_due_at"])
    assert updated["sla_target_hours"] == 4
    assert due_at - created_at == timedelta(hours=4)


def test_priority_change_records_sla_recalculation(client: TestClient) -> None:
    token = create_user_and_token(client, "sla-history@example.com")
    ticket = create_ticket(client, token, title="History SLA", priority="MEDIUM")

    update = client.patch(
        f"/tickets/{ticket['id']}",
        headers=auth(token),
        json={"priority": "HIGH"},
    )
    assert update.status_code == 200

    history = client.get(f"/tickets/{ticket['id']}/history", headers=auth(token))
    assert history.status_code == 200
    sla_event = next(item for item in history.json() if item["action"] == "SLA_RECALCULATED")
    assert sla_event["field"] == "sla_due_at"
    assert sla_event["old_value"] != sla_event["new_value"]


def test_open_overdue_ticket_reports_breached(client: TestClient, db: Session) -> None:
    token = create_user_and_token(client, "sla-overdue@example.com")
    payload = create_ticket(client, token, title="Overdue ticket")

    ticket = db.get(Ticket, payload["id"])
    assert ticket is not None
    ticket.sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.get(f"/tickets/{ticket.id}", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["sla_status"] == "BREACHED"


def test_closed_before_deadline_reports_met(client: TestClient, db: Session) -> None:
    token = create_user_and_token(client, "sla-met@example.com")
    payload = create_ticket(client, token, title="Met SLA")

    ticket = db.get(Ticket, payload["id"])
    assert ticket is not None
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = ticket.sla_due_at - timedelta(minutes=30)
    db.commit()

    response = client.get(f"/tickets/{ticket.id}", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["sla_status"] == "MET"


def test_closed_after_deadline_reports_breached(client: TestClient, db: Session) -> None:
    token = create_user_and_token(client, "sla-late-close@example.com")
    payload = create_ticket(client, token, title="Late close")

    ticket = db.get(Ticket, payload["id"])
    assert ticket is not None
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = ticket.sla_due_at + timedelta(minutes=30)
    db.commit()

    response = client.get(f"/tickets/{ticket.id}", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["sla_status"] == "BREACHED"


def test_ticket_list_filters_by_sla_status(client: TestClient, db: Session) -> None:
    token = create_user_and_token(client, "sla-filter@example.com")
    overdue_payload = create_ticket(client, token, title="Overdue filter")
    on_track_payload = create_ticket(client, token, title="On track filter")
    met_payload = create_ticket(client, token, title="Met filter")

    overdue = db.get(Ticket, overdue_payload["id"])
    met = db.get(Ticket, met_payload["id"])
    assert overdue is not None
    assert met is not None

    overdue.sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    met.status = TicketStatus.CLOSED
    met.closed_at = met.sla_due_at - timedelta(minutes=5)
    db.commit()

    breached = client.get("/tickets?sla_status=BREACHED", headers=auth(token))
    on_track = client.get("/tickets?sla_status=ON_TRACK", headers=auth(token))
    met_response = client.get("/tickets?sla_status=MET", headers=auth(token))

    assert breached.status_code == 200
    assert [item["id"] for item in breached.json()["items"]] == [overdue_payload["id"]]
    assert on_track.status_code == 200
    assert [item["id"] for item in on_track.json()["items"]] == [on_track_payload["id"]]
    assert met_response.status_code == 200
    assert [item["id"] for item in met_response.json()["items"]] == [met_payload["id"]]


def test_ticket_list_sorts_by_sla_deadline(client: TestClient) -> None:
    token = create_user_and_token(client, "sla-sort@example.com")
    low = create_ticket(client, token, title="Low deadline", priority="LOW")
    high = create_ticket(client, token, title="High deadline", priority="HIGH")
    medium = create_ticket(client, token, title="Medium deadline", priority="MEDIUM")

    response = client.get(
        "/tickets?sort_by=sla_due_at&sort_order=asc",
        headers=auth(token),
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [high["id"], medium["id"], low["id"]]
