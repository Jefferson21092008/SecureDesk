"""Static contracts for the operational UI (browser interaction is checked manually)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_ticket_detail_dialog_has_operational_sections() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for element_id in (
        "ticket-detail-dialog", "detail-close", "detail-status", "detail-priority",
        "detail-description", "detail-comments", "detail-comment-form", "detail-history",
        "detail-attachments", "detail-upload-form", "detail-upload-file",
        "detail-agent-select", "detail-assign-button", "detail-lifecycle-button",
    ):
        assert f'id="{element_id}"' in html


def test_ticket_list_supports_real_pagination() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'id="ticket-prev-page"' in html
    assert 'id="ticket-next-page"' in html
    assert 'page_size: "20"' in js
    assert "page.total" in js and "page.pages" in js
    assert "ticketLoadSequence" in js  # Guard against out-of-order search responses.
    assert "resetTicketPage()" in js


def test_ticket_operations_keep_backend_authorization_and_escape_content() -> None:
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "escapeHtml(c.content)" in js
    assert "escapeHtml(a.original_filename)" in js
    assert "escapeHtml(h.action)" in js
    assert 'state.user?.role === "ADMIN"' in js
    assert 'state.user?.role === "AGENT"' in js
    assert "blockedByAnotherAgent" in js
    assert 'apiRequest(`/tickets/${ticketId}`)' in js
    for path in ("/comments", "/history", "/attachments", "/assignment"):
        assert path in js
    assert 'responseType: "blob"' in js
    assert "body instanceof FormData" not in js  # Multipart must use the browser's boundary.
    assert 'typeof fetchOptions.body === "string"' in js


def test_no_new_external_frontend_dependencies() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'src="/app.js"' in html
    assert 'href="/styles.css"' in html
    assert "unpkg.com" not in html
    assert "cdnjs" not in html
