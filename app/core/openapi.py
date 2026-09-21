from fastapi.routing import APIRoute

API_VERSION = "1.0.0"

API_DESCRIPTION = """
SecureDesk is a secure IT service desk API for managing the complete lifecycle of support tickets.

### Authentication

Use `POST /auth/register` to create a standard `USER` account and `POST /auth/login` to obtain a Bearer access token. In Swagger UI, use **Authorize** with the same email and password used by the login endpoint. Access tokens are short-lived JWTs and can be revoked with `POST /auth/logout`.

### Roles

- **USER** — creates tickets and accesses only their own ticket scope.
- **AGENT** — handles tickets, assignment and lifecycle operations across the service desk.
- **ADMIN** — has administrative access to categories, departments and security audit data.

### Operational behavior

Ticket endpoints support categories, departments, assignment, comments, attachments, lifecycle history and SLA tracking. Metrics endpoints provide dashboard-ready aggregations and optional UTC creation-date filters.

The API applies request rate limiting. `429 Too Many Requests` responses include a `Retry-After` header. Authentication and security endpoints also use `Cache-Control: no-store`.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "System",
        "description": "Service discovery and health endpoints.",
    },
    {
        "name": "Authentication",
        "description": "Account registration, OAuth2 password login, JWT sessions and logout/revocation.",
    },
    {
        "name": "Tickets",
        "description": "Create, search, read, update and delete service desk tickets.",
    },
    {
        "name": "Ticket Assignment",
        "description": "Assign, unassign and reassign tickets according to AGENT/ADMIN authorization rules.",
    },
    {
        "name": "Lifecycle",
        "description": "Explicit ticket close and reopen operations with lifecycle history.",
    },
    {
        "name": "Comments",
        "description": "Ticket conversation entries scoped by ticket authorization.",
    },
    {
        "name": "Attachments",
        "description": "Validated ticket file uploads, listing, download and deletion.",
    },
    {
        "name": "History",
        "description": "Read-only functional history for ticket changes and lifecycle events.",
    },
    {
        "name": "Categories",
        "description": "Ticket classification. Reading requires authentication; management is ADMIN-only.",
    },
    {
        "name": "Departments",
        "description": "Service desk routing departments. Reading requires authentication; management is ADMIN-only.",
    },
    {
        "name": "Metrics",
        "description": "Dashboard-ready overview, SLA and dimensional metrics with optional UTC date filters.",
    },
    {
        "name": "Security Audit",
        "description": "ADMIN-only, read-only security audit events for authentication, authorization and abuse signals.",
    },
]

SWAGGER_UI_PARAMETERS = {
    "defaultModelsExpandDepth": 1,
    "displayRequestDuration": True,
    "docExpansion": "list",
    "filter": True,
    "persistAuthorization": True,
    "tryItOutEnabled": True,
}


def operation_id_from_route_name(route: APIRoute) -> str:
    """Keep generated SDK operation IDs short and stable across path refactors."""
    return route.name
