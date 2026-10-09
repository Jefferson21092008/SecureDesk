const API_BASE = "/api";
const TOKEN_KEY = "securedesk_access_token";

const roleNames = { ADMIN: "Administrador", AGENT: "Agente", USER: "Usuário" };
const state = {
  token: sessionStorage.getItem(TOKEN_KEY),
  user: null,
  tickets: [],
  recentTickets: [],
  ticketPage: 1,
  ticketPages: 1,
  ticketTotal: 0,
  selectedTicketId: null,
  departments: [],
  overview: null,
  sla: null,
  breakdown: null,
};

const loginView = document.querySelector("#login-view");
const invitationView = document.querySelector("#invitation-view");
let currentInvitationToken = null;
const appView = document.querySelector("#app-view");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginMessage = document.querySelector("#login-message");
const roleLabel = document.querySelector("#role-label");
const sidebar = document.querySelector(".sidebar");
const toast = document.querySelector("#toast");
const ticketDialog = document.querySelector("#ticket-dialog");
const detailDialog = document.querySelector("#ticket-detail-dialog");
let ticketLoadSequence = 0;
let detailLoadSequence = 0;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatApiError(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg || "Entrada inválida").join(" · ");
  }
  return fallback;
}

function clearSession(message = "") {
  state.token = null;
  state.user = null;
  state.selectedTicketId = null;
  detailLoadSequence += 1;
  if (detailDialog.open) detailDialog.close();
  sessionStorage.removeItem(TOKEN_KEY);
  appView.classList.add("hidden");
  loginView.classList.remove("hidden");
  invitationView.classList.add("hidden");
  if (message) {
    loginMessage.textContent = message;
    loginMessage.classList.add("is-error");
  }
}

async function apiRequest(path, options = {}) {
  const { auth = true, headers = {}, responseType = "json", ...fetchOptions } = options;
  const requestHeaders = new Headers(headers);
  if (auth && state.token) requestHeaders.set("Authorization", `Bearer ${state.token}`);
  // Only JSON bodies get a JSON content type: FormData must keep its multipart boundary.
  if (typeof fetchOptions.body === "string" && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers: requestHeaders });
  } catch {
    throw new Error("Não foi possível conectar à API.");
  }

  let payload = null;
  if (response.status !== 204) {
    const contentType = response.headers.get("content-type") || "";
    payload = !response.ok
      ? contentType.includes("application/json") ? await response.json() : await response.text()
      : responseType === "blob" ? await response.blob()
        : contentType.includes("application/json") ? await response.json() : await response.text();
  }

  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearSession("Sua sessão expirou. Entre novamente.");
    }
    if (response.status === 429) {
      const retryAfter = response.headers.get("retry-after");
      throw new Error(retryAfter ? `Muitas requisições. Tente novamente em ${retryAfter}s.` : "Muitas requisições. Tente novamente em instantes.");
    }
    const fallback = response.status === 403 ? "Você não tem permissão para esta ação." : `Erro ${response.status} ao acessar a API.`;
    throw new Error(formatApiError(payload, fallback));
  }
  return payload;
}

function priorityBadge(priority) {
  const labels = { HIGH: "Alta", MEDIUM: "Média", LOW: "Baixa" };
  return `<span class="badge badge--${escapeHtml(priority.toLowerCase())}">${escapeHtml(labels[priority] || priority)}</span>`;
}

function statusBadge(status) {
  const labels = { OPEN: "Aberto", IN_PROGRESS: "Em andamento", CLOSED: "Fechado" };
  const styles = { OPEN: "open", IN_PROGRESS: "progress", CLOSED: "closed" };
  return `<span class="badge badge--${escapeHtml(styles[status] || "closed")}">${escapeHtml(labels[status] || status)}</span>`;
}

function departmentName(id) {
  if (id == null) return "Sem departamento";
  return state.departments.find((item) => item.id === id)?.name || `Departamento #${id}`;
}

function agentName(id) {
  return id == null ? "Não atribuído" : `Agente #${id}`;
}

function slaLabel(ticket) {
  const labels = { ON_TRACK: "No prazo", MET: "Cumprido", BREACHED: "Estourado" };
  return labels[ticket.sla_status] || ticket.sla_status || "—";
}

function ticketRow(ticket, recent = false) {
  const title = `<button type="button" class="ticket-open-button" data-ticket-id="${ticket.id}" aria-label="Abrir chamado ${ticket.id}: ${escapeHtml(ticket.title)}">${escapeHtml(ticket.title)}</button>`;
  const base = `<td>#${ticket.id}</td><td class="ticket-title">${title}</td><td>${priorityBadge(ticket.priority)}</td><td>${statusBadge(ticket.status)}</td>`;
  if (recent) return `<tr>${base}<td>${escapeHtml(agentName(ticket.assigned_agent_id))}</td><td>${escapeHtml(slaLabel(ticket))}</td></tr>`;
  return `<tr>${base}<td>${escapeHtml(departmentName(ticket.department_id))}</td><td>${escapeHtml(agentName(ticket.assigned_agent_id))}</td></tr>`;
}

function renderRecentTickets() {
  const target = document.querySelector("#recent-ticket-rows");
  if (!state.recentTickets.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum chamado encontrado.</td></tr>';
    return;
  }
  target.innerHTML = state.recentTickets.map((ticket) => ticketRow(ticket, true)).join("");
}

function renderTickets() {
  const target = document.querySelector("#ticket-rows");
  document.querySelector("#ticket-count-label").textContent = `${state.ticketTotal} chamado${state.ticketTotal === 1 ? "" : "s"} encontrado${state.ticketTotal === 1 ? "" : "s"}`;
  document.querySelector("#ticket-pagination-label").textContent = `Página ${state.ticketPage} de ${state.ticketPages}`;
  document.querySelector("#ticket-prev-page").disabled = state.ticketPage <= 1;
  document.querySelector("#ticket-next-page").disabled = state.ticketPage >= state.ticketPages;
  if (!state.tickets.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum chamado corresponde aos filtros.</td></tr>';
    return;
  }
  target.innerHTML = state.tickets.map((ticket) => ticketRow(ticket)).join("");
}

function renderPriorityBars() {
  const priorities = state.overview?.by_priority || { high: 0, medium: 0, low: 0 };
  const max = Math.max(priorities.high, priorities.medium, priorities.low, 1);
  for (const key of ["high", "medium", "low"]) {
    document.querySelector(`#priority-${key}-count`).textContent = priorities[key];
    document.querySelector(`#priority-${key}-bar`).style.width = `${Math.round((priorities[key] / max) * 100)}%`;
  }
}

function renderOverview() {
  if (!state.overview || !state.sla) return;
  const total = state.overview.total;
  const inProgress = state.overview.by_status.in_progress;
  const compliance = state.sla.closed.compliance_rate_percent;
  const average = state.sla.average_resolution_hours;

  document.querySelector("#overview-total").textContent = total;
  document.querySelector("#overview-total-detail").textContent = state.overview.scope === "OWN" ? "Seus chamados nos últimos 30 dias" : "Chamados nos últimos 30 dias";
  document.querySelector("#overview-in-progress").textContent = inProgress;
  document.querySelector("#overview-progress-detail").textContent = total ? `${Math.round((inProgress / total) * 100)}% do volume atual` : "Sem chamados no período";
  document.querySelector("#overview-sla").textContent = compliance == null ? "—" : `${compliance}%`;
  document.querySelector("#overview-sla-detail").textContent = `${state.sla.by_sla_status.breached} chamado(s) fora do prazo`;
  document.querySelector("#overview-average").textContent = average == null ? "—" : `${String(average).replace(".", ",")}h`;
  document.querySelector("#overview-sla-ring-value").textContent = compliance == null ? "—" : `${Math.round(compliance)}%`;
  document.querySelector("#overview-sla-ring").style.background = `conic-gradient(var(--success) 0 ${Math.max(0, Math.min(100, compliance || 0))}%, #edf1f5 ${Math.max(0, Math.min(100, compliance || 0))}%)`;
  renderPriorityBars();
}

function renderRankings() {
  const render = (items, labelKey, emptyLabel) => {
    const normalized = items.length ? items : [{ [labelKey]: emptyLabel, total: 0 }];
    const max = Math.max(...normalized.map((item) => item.total), 1);
    return normalized.map((item) => {
      const label = item[labelKey] || emptyLabel;
      const width = Math.round((item.total / max) * 100);
      return `<div class="rank-item"><span title="${escapeHtml(label)}">${escapeHtml(label)}</span><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><strong>${item.total}</strong></div>`;
    }).join("");
  };
  document.querySelector("#department-bars").innerHTML = render(state.breakdown?.by_department || [], "department_name", "Sem departamento");
  document.querySelector("#agent-bars").innerHTML = render(state.breakdown?.by_agent || [], "agent_email", "Não atribuído");
}

function renderMetrics() {
  if (!state.sla) return;
  document.querySelector("#metrics-on-track").textContent = state.sla.by_sla_status.on_track;
  document.querySelector("#metrics-breached").textContent = state.sla.by_sla_status.breached;
  document.querySelector("#metrics-closed").textContent = state.sla.closed.total;
  const compliance = state.sla.closed.compliance_rate_percent;
  document.querySelector("#metrics-compliance").textContent = compliance == null ? "Sem tickets fechados no período" : `${compliance}% de compliance`;
  renderRankings();
}

function renderAudit(items) {
  const target = document.querySelector("#audit-rows");
  if (!items.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum evento de segurança registrado.</td></tr>';
    return;
  }
  target.innerHTML = items.map((entry) => {
    const actor = entry.actor_id == null ? "—" : `Usuário #${entry.actor_id}`;
    const time = new Date(entry.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    return `<tr><td><strong>${escapeHtml(entry.event_type)}</strong></td><td>${escapeHtml(actor)}</td><td>${escapeHtml(entry.path)}</td><td>${escapeHtml(entry.status_code ?? "—")}</td><td>${escapeHtml(entry.ip_address)}</td><td>${escapeHtml(time)}</td></tr>`;
  }).join("");
}

function updateUserUI() {
  if (!state.user) return;
  roleLabel.textContent = roleNames[state.user.role] || state.user.role;
  const localPart = state.user.email.split("@")[0];
  const displayName = localPart.replace(/[._-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  document.querySelector("#user-email").textContent = displayName || state.user.email;
  document.querySelector("#user-avatar").textContent = (displayName || "SD").split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  document.querySelectorAll(".admin-only").forEach((element) => element.classList.toggle("hidden", state.user.role !== "ADMIN"));
}

function navigate(viewName) {
  if (["security", "users"].includes(viewName) && state.user?.role !== "ADMIN") return;
  const titles = { overview: ["OPERAÇÃO", "Visão geral"], tickets: ["ATENDIMENTO", "Chamados"], metrics: ["ANÁLISE", "Métricas"], security: ["SEGURANÇA", "Auditoria"], users: ["ADMINISTRAÇÃO", "Usuários"] };
  document.querySelectorAll(".page-view").forEach((view) => view.classList.add("hidden"));
  document.querySelector(`#view-${viewName}`)?.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("is-active", item.dataset.view === viewName));
  document.querySelector("#page-eyebrow").textContent = titles[viewName][0];
  document.querySelector("#page-title").textContent = titles[viewName][1];
  sidebar.classList.remove("is-open");
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3000);
}

function dateInputValue(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function metricsPeriodQuery() {
  const params = new URLSearchParams();
  const from = document.querySelector("#metrics-date-from").value;
  const to = document.querySelector("#metrics-date-to").value;
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  return params.toString() ? `?${params}` : "";
}

function dashboardPeriodQuery() {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 29);
  return `?date_from=${dateInputValue(from)}&date_to=${dateInputValue(to)}`;
}

async function loadDepartments() {
  state.departments = await apiRequest("/departments");
  const select = document.querySelector("#new-department");
  select.innerHTML = '<option value="">Sem departamento</option>' + state.departments.map((department) => `<option value="${department.id}">${escapeHtml(department.name)}</option>`).join("");
}

async function loadTickets() {
  const sequence = ++ticketLoadSequence;
  const params = new URLSearchParams({
    page: String(state.ticketPage), page_size: "20", sort_by: "created_at", sort_order: "desc",
  });
  const search = document.querySelector("#ticket-search").value.trim();
  const status = document.querySelector("#status-filter").value;
  const priority = document.querySelector("#priority-filter").value;
  if (search) params.set("search", search);
  if (status !== "ALL") params.set("status", status);
  if (priority !== "ALL") params.set("priority", priority);
  const page = await apiRequest(`/tickets?${params}`);
  if (sequence !== ticketLoadSequence) return;
  // Filters or deletions may reduce the total page count.
  if (state.ticketPage > Math.max(1, page.pages)) {
    state.ticketPage = Math.max(1, page.pages);
    return loadTickets();
  }
  state.tickets = page.items;
  state.ticketTotal = page.total;
  state.ticketPages = Math.max(1, page.pages);
  renderTickets();
}

async function loadRecentTickets() {
  const page = await apiRequest("/tickets?page=1&page_size=5&sort_by=created_at&sort_order=desc");
  state.recentTickets = page.items;
  renderRecentTickets();
}

function resetTicketPage() {
  state.ticketPage = 1;
  return loadTickets();
}

async function loadDashboard() {
  const period = dashboardPeriodQuery();
  const [overview, sla] = await Promise.all([
    apiRequest(`/metrics/overview${period}`),
    apiRequest(`/metrics/sla${period}`),
  ]);
  state.overview = overview;
  state.sla = sla;
  renderOverview();
}

async function loadMetrics() {
  const period = metricsPeriodQuery();
  const [sla, breakdown] = await Promise.all([
    apiRequest(`/metrics/sla${period}`),
    apiRequest(`/metrics/breakdown${period}`),
  ]);
  state.sla = sla;
  state.breakdown = breakdown;
  renderMetrics();
}

async function loadAudit() {
  if (state.user?.role !== "ADMIN") return;
  const page = await apiRequest("/security/audit?page=1&page_size=25");
  renderAudit(page.items);
}

async function loadUsersAndInvitations() {
  if (state.user?.role !== "ADMIN") return;
  const [users, invitations] = await Promise.all([
    apiRequest("/admin/users"),
    apiRequest("/admin/invitations"),
  ]);
  document.querySelector("#users-rows").innerHTML = users.length
    ? users.map((user) => `<tr><td>${user.id}</td><td>${escapeHtml(user.email)}</td><td>${escapeHtml(roleNames[user.role] || user.role)}</td></tr>`).join("")
    : '<tr><td colspan="3" class="empty-state">Nenhuma conta.</td></tr>';
  document.querySelector("#invitation-rows").innerHTML = invitations.length
    ? invitations.map((invite) => {
      const status = invite.accepted_at ? "Aceito" : invite.revoked_at ? "Substituído" : new Date(invite.expires_at).getTime() <= Date.now() ? "Expirado" : "Pendente";
      return `<tr><td>${escapeHtml(invite.email)}</td><td>${escapeHtml(roleNames[invite.role] || invite.role)}</td><td>${escapeHtml(new Date(invite.expires_at).toLocaleString("pt-BR"))}</td><td>${status}</td></tr>`;
    }).join("")
    : '<tr><td colspan="4" class="empty-state">Nenhum convite.</td></tr>';
}

// Ticket operations reuse the backend contracts and never decide permissions on behalf of the API.
function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function renderTicketDetail(ticket, comments, history, attachments, users) {
  document.querySelector("#detail-title").textContent = `#${ticket.id} — ${ticket.title}`;
  document.querySelector("#detail-description").textContent = ticket.description;
  document.querySelector("#detail-status").innerHTML = statusBadge(ticket.status);
  document.querySelector("#detail-priority").innerHTML = priorityBadge(ticket.priority);
  document.querySelector("#detail-owner").textContent = `Usuário #${ticket.owner_id}`;
  document.querySelector("#detail-department").textContent = departmentName(ticket.department_id);
  document.querySelector("#detail-assignee").textContent = agentName(ticket.assigned_agent_id);
  document.querySelector("#detail-sla").textContent = `${slaLabel(ticket)} · ${formatDate(ticket.sla_due_at)}`;
  document.querySelector("#detail-created").textContent = formatDate(ticket.created_at);

  document.querySelector("#detail-comments").innerHTML = comments.length
    ? comments.map((c) => `<article class="detail-entry"><div class="detail-entry__meta">Usuário #${c.author_id} · ${escapeHtml(formatDate(c.created_at))}</div><p>${escapeHtml(c.content)}</p></article>`).join("")
    : '<p class="muted">Nenhum comentário.</p>';
  document.querySelector("#detail-history").innerHTML = history.length
    ? history.map((h) => `<li><strong>${escapeHtml(h.action)}</strong> · ${escapeHtml(formatDate(h.created_at))}<span class="detail-history-description">${escapeHtml(h.field || "")} ${escapeHtml(h.old_value ?? "")} → ${escapeHtml(h.new_value ?? "")} · Usuário #${h.actor_id}</span></li>`).join("")
    : '<li>Nenhuma movimentação registrada.</li>';
  document.querySelector("#detail-attachments").innerHTML = attachments.length
    ? attachments.map((a) => `<li><span>${escapeHtml(a.original_filename)} <small>(${Math.round(a.size_bytes / 1024)} KB)</small></span><button type="button" class="button button--ghost button--small" data-attachment-id="${a.id}" data-filename="${escapeHtml(a.original_filename)}">Baixar</button></li>`).join("")
    : '<li>Sem anexos.</li>';

  const staff = state.user?.role === "ADMIN" || state.user?.role === "AGENT";
  document.querySelector("#detail-staff-actions").classList.toggle("hidden", !staff);
  if (!staff) return;
  const select = document.querySelector("#detail-agent-select");
  const blockedByAnotherAgent = state.user.role === "AGENT" &&
    ticket.assigned_agent_id !== null && ticket.assigned_agent_id !== state.user.id;
  if (state.user.role === "ADMIN") {
    select.innerHTML = '<option value="">Não atribuído</option>' + users.filter((u) => u.role === "AGENT")
      .map((u) => `<option value="${u.id}">${escapeHtml(u.email)}</option>`).join("");
  } else {
    select.innerHTML = `<option value="">Não atribuído</option><option value="${state.user.id}">Atribuir a mim</option>`;
  }
  select.value = ticket.assigned_agent_id == null ? "" : String(ticket.assigned_agent_id);
  select.disabled = blockedByAnotherAgent;
  document.querySelector("#detail-assign-button").disabled = blockedByAnotherAgent;
  const lifecycleButton = document.querySelector("#detail-lifecycle-button");
  lifecycleButton.textContent = ticket.status === "CLOSED" ? "Reabrir chamado" : "Fechar chamado";
  lifecycleButton.disabled = blockedByAnotherAgent;
  document.querySelector("#detail-staff-note").textContent = blockedByAnotherAgent
    ? "Este chamado já está atribuído a outro agente." : "Alterações são validadas pelo servidor.";
}

async function refreshTicketDetail() {
  const ticketId = state.selectedTicketId;
  if (!ticketId) return;
  const sequence = ++detailLoadSequence;
  const info = document.querySelector("#detail-loading");
  info.textContent = "Carregando detalhes...";
  try {
    const [ticket, comments, history, attachments, users] = await Promise.all([
      apiRequest(`/tickets/${ticketId}`),
      apiRequest(`/tickets/${ticketId}/comments`),
      apiRequest(`/tickets/${ticketId}/history`),
      apiRequest(`/tickets/${ticketId}/attachments`),
      state.user?.role === "ADMIN" ? apiRequest("/admin/users") : Promise.resolve([]),
    ]);
    if (sequence !== detailLoadSequence || state.selectedTicketId !== ticketId) return;
    renderTicketDetail(ticket, comments, history, attachments, users);
    info.textContent = "";
  } catch (error) {
    if (sequence !== detailLoadSequence) return;
    info.textContent = `Não foi possível carregar o chamado: ${error.message}`;
    throw error;
  }
}

async function openTicketDetail(ticketId) {
  if (!Number.isSafeInteger(ticketId) || ticketId < 1) return;
  state.selectedTicketId = ticketId;
  document.querySelector("#detail-title").textContent = `Chamado #${ticketId}`;
  // Never show stale details from the previously selected ticket while loading.
  for (const id of ["detail-description", "detail-comments", "detail-history", "detail-attachments",
    "detail-status", "detail-priority", "detail-owner", "detail-department", "detail-assignee",
    "detail-sla", "detail-created"]) {
    document.getElementById(id).textContent = "";
  }
  document.querySelector("#detail-staff-actions").classList.add("hidden");
  if (!detailDialog.open) detailDialog.showModal();
  await refreshTicketDetail();
}

async function refreshAfterTicketAction(includeOverview = false) {
  const tasks = [refreshTicketDetail()];
  if (includeOverview) tasks.push(loadTickets(), loadRecentTickets(), loadDashboard(), loadMetrics());
  await Promise.all(tasks);
}

async function submitTicketAction(button, operation, successMessage, includeOverview = false) {
  if (!state.selectedTicketId || button.disabled) return false;
  button.disabled = true;
  let saved = false;
  try {
    await operation(state.selectedTicketId);
    saved = true;
    await refreshAfterTicketAction(includeOverview);
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast(saved ? "Alteração salva, mas não foi possível atualizar a tela. Reabra o chamado." : error.message);
    return saved;
  } finally {
    button.disabled = false;
  }
}

async function downloadTicketAttachment(ticketId, attachmentId, filename) {
  // A normal href cannot include the bearer token and can bypass authorization.
  const blob = await apiRequest(`/tickets/${ticketId}/attachments/${attachmentId}`, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}

async function loadApplication() {
  await Promise.all([loadDepartments(), loadTickets(), loadRecentTickets(), loadDashboard(), loadMetrics()]);
  if (state.user?.role === "ADMIN") await Promise.all([loadAudit(), loadUsersAndInvitations()]);
}

async function startAuthenticatedSession() {
  state.user = await apiRequest("/auth/me");
  updateUserUI();
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  navigate("overview");
  await loadApplication();
}

document.querySelector("#invite-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#invite-submit");
  button.disabled = true;
  document.querySelector("#invite-result").classList.add("hidden");
  try {
    const invite = await apiRequest("/admin/invitations", {
      method: "POST",
      body: JSON.stringify({
        email: document.querySelector("#invite-email").value.trim(),
        role: document.querySelector("#invite-role").value,
      }),
    });
    document.querySelector("#invite-link").value = `${location.origin}${location.pathname}#invite=${encodeURIComponent(invite.token)}`;
    document.querySelector("#invite-result").classList.remove("hidden");
    document.querySelector("#invite-form").reset();
    await loadUsersAndInvitations();
    showToast("Convite gerado. Compartilhe o link com segurança.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#copy-invite-link").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(document.querySelector("#invite-link").value);
    showToast("Link copiado.");
  } catch {
    showToast("Não foi possível copiar automaticamente. Selecione o link para copiar.");
  }
});

function openInvitationFromFragment() {
  if (!location.hash.startsWith("#invite=")) return false;
  const token = location.hash.slice("#invite=".length);
  if (!token || token.length > 256) return false;
  try {
    currentInvitationToken = decodeURIComponent(token);
  } catch {
    return false;
  }
  // The URL fragment is not sent in HTTP requests, and we remove it from history.
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  appView.classList.add("hidden");
  loginView.classList.add("hidden");
  invitationView.classList.remove("hidden");
  return true;
}

document.querySelector("#invitation-accept-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = document.querySelector("#invitation-password").value;
  const confirmation = document.querySelector("#invitation-password-confirm").value;
  const message = document.querySelector("#invitation-message");
  message.classList.remove("is-error");
  if (password !== confirmation) {
    message.textContent = "As senhas não coincidem.";
    message.classList.add("is-error");
    return;
  }
  try {
    await apiRequest("/auth/accept-invitation", {
      auth: false,
      method: "POST",
      body: JSON.stringify({ token: currentInvitationToken, password }),
    });
    currentInvitationToken = null;
    document.querySelector("#invitation-accept-form").reset();
    invitationView.classList.add("hidden");
    loginView.classList.remove("hidden");
    loginMessage.classList.remove("is-error");
    loginMessage.textContent = "Conta ativada! Entre com o e-mail do seu convite.";
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("is-error");
  }
});

document.querySelector("#back-to-login").addEventListener("click", () => {
  currentInvitationToken = null;
  invitationView.classList.add("hidden");
  loginView.classList.remove("hidden");
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginMessage.classList.remove("is-error");
  loginMessage.textContent = "Autenticando...";
  loginButton.disabled = true;
  const body = new URLSearchParams({
    username: document.querySelector("#login-email").value.trim(),
    password: document.querySelector("#login-password").value,
  });
  try {
    const token = await apiRequest("/auth/login", { method: "POST", body, auth: false });
    state.token = token.access_token;
    sessionStorage.setItem(TOKEN_KEY, state.token);
    await startAuthenticatedSession();
    loginForm.reset();
    loginMessage.textContent = "A autenticação é feita pela API do SecureDesk.";
  } catch (error) {
    clearSession(error.message || "Falha ao autenticar.");
  } finally {
    loginButton.disabled = false;
  }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  try {
    if (state.token) await apiRequest("/auth/logout", { method: "POST" });
  } catch (error) {
    showToast(error.message);
  } finally {
    clearSession();
  }
});

document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.go)));
document.querySelector("#menu-button").addEventListener("click", () => sidebar.classList.toggle("is-open"));

document.querySelector("#status-filter").addEventListener("change", () => resetTicketPage().catch((error) => showToast(error.message)));
document.querySelector("#priority-filter").addEventListener("change", () => resetTicketPage().catch((error) => showToast(error.message)));
document.querySelector("#ticket-prev-page").addEventListener("click", () => {
  if (state.ticketPage <= 1) return;
  state.ticketPage -= 1;
  loadTickets().catch((error) => showToast(error.message));
});
document.querySelector("#ticket-next-page").addEventListener("click", () => {
  if (state.ticketPage >= state.ticketPages) return;
  state.ticketPage += 1;
  loadTickets().catch((error) => showToast(error.message));
});
let searchTimer;
document.querySelector("#ticket-search").addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => resetTicketPage().catch((error) => showToast(error.message)), 300);
});

document.querySelectorAll("#metrics-date-from, #metrics-date-to").forEach((input) => input.addEventListener("change", () => loadMetrics().catch((error) => showToast(error.message))));

document.querySelector("#new-ticket-button").addEventListener("click", () => ticketDialog.showModal());
document.querySelector("#ticket-form").addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const departmentValue = document.querySelector("#new-department").value;
  const payload = {
    title: document.querySelector("#new-title").value.trim(),
    description: document.querySelector("#new-description").value.trim(),
    priority: document.querySelector("#new-priority").value,
    department_id: departmentValue ? Number(departmentValue) : null,
  };
  try {
    await apiRequest("/tickets", { method: "POST", body: JSON.stringify(payload) });
    ticketDialog.close();
    document.querySelector("#ticket-form").reset();
    await Promise.all([resetTicketPage(), loadRecentTickets(), loadDashboard(), loadMetrics()]);
    showToast("Chamado criado com sucesso.");
  } catch (error) {
    showToast(error.message);
  }
});

// Use delegated events because ticket rows are rendered after every API refresh.
for (const table of ["#ticket-rows", "#recent-ticket-rows"]) {
  document.querySelector(table).addEventListener("click", (event) => {
    const button = event.target.closest("button[data-ticket-id]");
    if (!button) return;
    openTicketDetail(Number(button.dataset.ticketId)).catch((error) => showToast(error.message));
  });
}

detailDialog.addEventListener("close", () => {
  state.selectedTicketId = null;
  detailLoadSequence += 1;
});
document.querySelector("#detail-close").addEventListener("click", () => detailDialog.close());

document.querySelector("#detail-comment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#detail-comment-submit");
  const content = document.querySelector("#detail-comment-text").value.trim();
  if (!content || !state.selectedTicketId || button.disabled) return;
  const saved = await submitTicketAction(button, (id) => apiRequest(`/tickets/${id}/comments`, {
    method: "POST", body: JSON.stringify({ content }),
  }), "Comentário adicionado.");
  if (saved) document.querySelector("#detail-comment-form").reset();
});

document.querySelector("#detail-upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#detail-upload-submit");
  const file = document.querySelector("#detail-upload-file").files[0];
  if (!file || !state.selectedTicketId || button.disabled) return;
  const body = new FormData();
  body.append("file", file);
  button.disabled = true;
  let uploaded = false;
  try {
    await apiRequest(`/tickets/${state.selectedTicketId}/attachments`, { method: "POST", body });
    uploaded = true;
    document.querySelector("#detail-upload-form").reset();
    await refreshAfterTicketAction();
    showToast("Arquivo anexado com sucesso.");
  } catch (error) {
    showToast(uploaded ? "Arquivo enviado, mas não foi possível atualizar a lista. Reabra o chamado." : error.message);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#detail-attachments").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-attachment-id]");
  if (!button || !state.selectedTicketId) return;
  button.disabled = true;
  downloadTicketAttachment(state.selectedTicketId, Number(button.dataset.attachmentId), button.dataset.filename)
    .catch((error) => showToast(error.message)).finally(() => { button.disabled = false; });
});

document.querySelector("#detail-assign-button").addEventListener("click", () => {
  const button = document.querySelector("#detail-assign-button");
  const value = document.querySelector("#detail-agent-select").value;
  submitTicketAction(button, (id) => apiRequest(`/tickets/${id}/assignment`, {
    method: "PATCH", body: JSON.stringify({ agent_id: value ? Number(value) : null }),
  }), "Responsável atualizado.", true);
});

document.querySelector("#detail-lifecycle-button").addEventListener("click", () => {
  const button = document.querySelector("#detail-lifecycle-button");
  const operation = button.textContent === "Reabrir chamado" ? "reopen" : "close";
  submitTicketAction(button, (id) => apiRequest(`/tickets/${id}/${operation}`, {
    method: "POST",
  }), operation === "close" ? "Chamado fechado." : "Chamado reaberto.", true);
});

async function boot() {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  document.querySelector("#metrics-date-from").value = dateInputValue(firstDay);
  document.querySelector("#metrics-date-to").value = dateInputValue(today);

  if (openInvitationFromFragment()) return;
  if (!state.token) return;
  try {
    await startAuthenticatedSession();
  } catch {
    clearSession("Sua sessão não pôde ser restaurada. Entre novamente.");
  }
}

boot();
