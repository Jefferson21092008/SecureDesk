from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.category import Category
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter()


def require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can manage categories")


def category_name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    query = select(Category.id).where(func.lower(Category.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


@router.get("", response_model=list[CategoryRead])
def list_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Category]:
    del current_user
    return list(db.scalars(select(Category).order_by(Category.name.asc(), Category.id.asc())))


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    del current_user
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    require_admin(current_user)
    if category_name_exists(db, data.name):
        raise HTTPException(status_code=409, detail="Category name already exists")

    category = Category(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Category:
    require_admin(current_user)
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name is not None and category_name_exists(db, new_name, exclude_id=category.id):
        raise HTTPException(status_code=409, detail="Category name already exists")

    for field, value in changes.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_admin(current_user)
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    ticket_using_category = db.scalar(select(Ticket.id).where(Ticket.category_id == category.id).limit(1))
    if ticket_using_category is not None:
        raise HTTPException(status_code=409, detail="Category is in use by tickets")

    db.delete(category)
    db.commit()
