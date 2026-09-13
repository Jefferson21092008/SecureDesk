from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.department import Department
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate

router = APIRouter()


def require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can manage departments")


def department_name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    query = select(Department.id).where(func.lower(Department.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Department.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


@router.get("", response_model=list[DepartmentRead])
def list_departments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Department]:
    del current_user
    return list(db.scalars(select(Department).order_by(Department.name.asc(), Department.id.asc())))


@router.get("/{department_id}", response_model=DepartmentRead)
def get_department(
    department_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Department:
    del current_user
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Department:
    require_admin(current_user)
    if department_name_exists(db, data.name):
        raise HTTPException(status_code=409, detail="Department name already exists")

    department = Department(**data.model_dump())
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


@router.patch("/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int,
    data: DepartmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Department:
    require_admin(current_user)
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name is not None and department_name_exists(db, new_name, exclude_id=department.id):
        raise HTTPException(status_code=409, detail="Department name already exists")

    for field, value in changes.items():
        setattr(department, field, value)

    db.commit()
    db.refresh(department)
    return department


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    department_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_admin(current_user)
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    ticket_using_department = db.scalar(
        select(Ticket.id).where(Ticket.department_id == department.id).limit(1)
    )
    if ticket_using_department is not None:
        raise HTTPException(status_code=409, detail="Department is in use by tickets")

    db.delete(department)
    db.commit()
