from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.category import Category
from app.models.department import Department
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.services.sla import calculate_sla_due_at

DEMO_PASSWORD = "SecureDesk!2026"


def get_or_create_user(db, email: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(DEMO_PASSWORD), role=role)
        db.add(user)
        db.flush()
    else:
        user.role = role
    return user


def get_or_create_department(db, name: str) -> Department:
    department = db.scalar(select(Department).where(Department.name == name))
    if department is None:
        department = Department(name=name, description=f"Fila de atendimento {name.lower()}.")
        db.add(department)
        db.flush()
    return department


def get_or_create_category(db, name: str) -> Category:
    category = db.scalar(select(Category).where(Category.name == name))
    if category is None:
        category = Category(name=name, description=f"Categoria de demonstração: {name}.")
        db.add(category)
        db.flush()
    return category


def create_ticket_if_missing(
    db,
    *,
    owner: User,
    agent: User | None,
    department: Department,
    category: Category,
    title: str,
    description: str,
    priority: TicketPriority,
    status: TicketStatus,
    created_at: datetime,
    closed_at: datetime | None = None,
) -> None:
    if db.scalar(select(Ticket.id).where(Ticket.title == title)) is not None:
        return

    ticket = Ticket(
        title=title,
        description=description,
        priority=priority,
        status=status,
        owner_id=owner.id,
        assigned_agent_id=agent.id if agent else None,
        department_id=department.id,
        category_id=category.id,
        created_at=created_at,
        sla_due_at=calculate_sla_due_at(created_at, priority),
        closed_at=closed_at,
    )
    db.add(ticket)
    db.flush()
    db.add(TicketHistory(ticket_id=ticket.id, actor_id=owner.id, action="CREATED"))


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("Demo seed is disabled when APP_ENV=production")

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        admin = get_or_create_user(db, "admin@securedesk.dev", UserRole.ADMIN)
        agent = get_or_create_user(db, "agent@securedesk.dev", UserRole.AGENT)
        user = get_or_create_user(db, "user@securedesk.dev", UserRole.USER)

        infra = get_or_create_department(db, "Infraestrutura")
        systems = get_or_create_department(db, "Sistemas")
        support = get_or_create_department(db, "Suporte")
        network = get_or_create_category(db, "Rede")
        access = get_or_create_category(db, "Acesso")
        hardware = get_or_create_category(db, "Hardware")

        create_ticket_if_missing(
            db,
            owner=user,
            agent=agent,
            department=infra,
            category=network,
            title="VPN desconecta após autenticação",
            description="A conexão VPN cai poucos segundos após a autenticação.",
            priority=TicketPriority.HIGH,
            status=TicketStatus.IN_PROGRESS,
            created_at=now - timedelta(hours=2),
        )
        create_ticket_if_missing(
            db,
            owner=user,
            agent=None,
            department=systems,
            category=access,
            title="Erro ao acessar o ERP financeiro",
            description="O usuário recebe erro de permissão ao abrir o módulo financeiro.",
            priority=TicketPriority.HIGH,
            status=TicketStatus.OPEN,
            created_at=now - timedelta(hours=5),
        )
        create_ticket_if_missing(
            db,
            owner=admin,
            agent=agent,
            department=support,
            category=hardware,
            title="Notebook sem acesso à impressora",
            description="A impressora corporativa não aparece para o notebook do setor.",
            priority=TicketPriority.LOW,
            status=TicketStatus.CLOSED,
            created_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=2, hours=12),
        )
        create_ticket_if_missing(
            db,
            owner=admin,
            agent=agent,
            department=systems,
            category=access,
            title="Solicitação de acesso ao Git interno",
            description="Conceder acesso ao repositório interno para novo integrante.",
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.CLOSED,
            created_at=now - timedelta(days=2),
            closed_at=now - timedelta(days=1, hours=12),
        )
        create_ticket_if_missing(
            db,
            owner=user,
            agent=agent,
            department=infra,
            category=network,
            title="Wi-Fi instável na sala de reunião",
            description="Há quedas intermitentes de Wi-Fi durante videoconferências.",
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.IN_PROGRESS,
            created_at=now - timedelta(hours=3),
        )
        create_ticket_if_missing(
            db,
            owner=admin,
            agent=agent,
            department=support,
            category=hardware,
            title="Atualização de software corporativo",
            description="Atualizar a versão homologada do software corporativo.",
            priority=TicketPriority.LOW,
            status=TicketStatus.CLOSED,
            created_at=now - timedelta(days=5),
            closed_at=now - timedelta(days=4, hours=12),
        )

        db.commit()

    print("Demo data ready.")
    print("admin@securedesk.dev / SecureDesk!2026")
    print("agent@securedesk.dev / SecureDesk!2026")
    print("user@securedesk.dev / SecureDesk!2026")


if __name__ == "__main__":
    main()
