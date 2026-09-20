from fastapi.testclient import TestClient

from app.core.openapi import API_VERSION, OPENAPI_TAGS


def test_api_discovery_endpoint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "SecureDesk API",
        "version": API_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
    }


def test_interactive_documentation_endpoints(client: TestClient) -> None:
    swagger = client.get("/docs")
    redoc = client.get("/redoc")

    assert swagger.status_code == 200
    assert "Swagger UI" in swagger.text
    assert redoc.status_code == 200
    assert "ReDoc" in redoc.text


def test_openapi_metadata_and_tags(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "SecureDesk API"
    assert schema["info"]["version"] == API_VERSION
    assert "Authentication" in schema["info"]["description"]
    assert "Roles" in schema["info"]["description"]
    assert schema["tags"] == OPENAPI_TAGS


def test_openapi_documents_oauth2_password_flow(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    oauth2 = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]

    assert oauth2["type"] == "oauth2"
    assert oauth2["flows"]["password"]["tokenUrl"] == "/auth/login"
    assert schema["paths"]["/tickets"]["get"]["security"] == [
        {"OAuth2PasswordBearer": []}
    ]


def test_login_is_documented_as_form_request(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    login = schema["paths"]["/auth/login"]["post"]

    assert "application/x-www-form-urlencoded" in login["requestBody"]["content"]
    assert login["operationId"] == "login"


def test_write_schemas_publish_examples(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert schemas["UserCreate"]["example"]["email"] == "user@example.com"
    assert schemas["TicketCreate"]["example"]["priority"] == "HIGH"
    assert schemas["CategoryCreate"]["example"]["name"] == "Network"
    assert schemas["DepartmentCreate"]["example"]["name"] == "Infrastructure"
    assert schemas["CommentCreate"]["example"]["content"]
    assert schemas["TicketAssignmentUpdate"]["example"] == {"agent_id": 5}


def test_every_operation_has_tag_summary_and_unique_operation_id(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation_ids: list[str] = []

    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation.get("tags")
            assert operation.get("summary")
            operation_id = operation.get("operationId")
            assert operation_id
            operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))
