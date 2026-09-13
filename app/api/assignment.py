from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.ticket import Ticket
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.schemas.assignment import TicketAssignmentUpdate
from app.schemas.ticket import TicketRead

router = APIRouter()


def _assignment_action(old_agent_id: int | None, new_agent_id: int | None) -> str:
    if old_agent_id is None and new_agent_id is not None:
        return "ASSIGNED"
    if old_agent_id is not None and new_agent_id is None:
        return "UNASSIGNED"
    return "REASSIGNED"


@router.patch(
    "/{ticket_id}/assignment",
    response_model=TicketRead,
)
def update_ticket_assignment(
    ticket_id: int,
    data: TicketAssignmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    if current_user.role == UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users cannot assign tickets",
        )

    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    new_agent_id = data.agent_id

    if current_user.role == UserRole.AGENT:
        if new_agent_id is None:
            if ticket.assigned_agent_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents can only unassign tickets assigned to themselves",
                )
        elif new_agent_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agents can only assign tickets to themselves",
            )
        elif ticket.assigned_agent_id not in {None, current_user.id}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is already assigned to another agent",
            )

    if new_agent_id is not None:
        agent = db.get(User, new_agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.role != UserRole.AGENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assigned user must have AGENT role",
            )

    old_agent_id = ticket.assigned_agent_id
    if old_agent_id == new_agent_id:
        return ticket

    ticket.assigned_agent_id = new_agent_id
    db.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=current_user.id,
            action=_assignment_action(old_agent_id, new_agent_id),
            field="assigned_agent_id",
            old_value=str(old_agent_id) if old_agent_id is not None else None,
            new_value=str(new_agent_id) if new_agent_id is not None else None,
        )
    )

    db.commit()
    db.refresh(ticket)
    return ticket
