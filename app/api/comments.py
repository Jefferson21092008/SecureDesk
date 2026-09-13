from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.ticket_access import get_accessible_ticket
from app.db import get_db
from app.models.comment import Comment
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead

router = APIRouter()


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    ticket_id: int,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Comment:
    get_accessible_ticket(ticket_id, current_user, db)

    comment = Comment(
        content=data.content,
        ticket_id=ticket_id,
        author_id=current_user.id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.get(
    "/{ticket_id}/comments",
    response_model=list[CommentRead],
)
def list_comments(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Comment]:
    get_accessible_ticket(ticket_id, current_user, db)

    return list(
        db.scalars(
            select(Comment)
            .where(Comment.ticket_id == ticket_id)
            .order_by(Comment.id.asc())
        )
    )
