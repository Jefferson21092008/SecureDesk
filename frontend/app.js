const API_BASE = "/api";
const TOKEN_KEY = "securedesk_access_token";

const roleNames = { ADMIN: "Administrador", AGENT: "Agente", USER: "Usuário" };
const state = {
  token: sessionStorage.getItem(TOKEN_KEY),
  user: null,
  tickets: [],
  departments: [],
  overview: null,
  sla: null,
  breakdown: null,
};

const loginView = document.querySelector("#login-view");
const appView = document.querySelector("#app-view");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginMessage = document.querySelector("#login-message");
const roleLabel = document.querySelector("#role-label");
const sidebar = document.querySelector(".sidebar");
const toast = document.querySelector("#toast");
const ticketDialog = document.querySelector("#ticket-dialog");

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
  sessionStorage.removeItem(TOKEN_KEY);
  appView.classList.add("hidden");
  loginView.classList.remove("hidden");
  if (message) {
    loginMessage.textContent = message;
    loginMessage.classList.add("is-error");
  }
}

async function apiRequest(path, options = {}) {
  const { auth = true, headers = {}, ...fetchOptions } = options;
  const requestHeaders = new Headers(headers);
  if (auth && state.token) requestHeaders.set("Authorization", `Bearer ${state.token}`);
  if (fetchOptions.body && !(fetchOptions.body instanceof URLSearchParams) && !requestHeaders.has("Content-Type")) {
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
    payload = contentType.includes("application/json") ? await response.json() : await response.text();
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
  const base = `<td>#${ticket.id}</td><td class="ticket-title">${escapeHtml(ticket.title)}</td><td>${priorityBadge(ticket.priority)}</td><td>${statusBadge(ticket.status)}</td>`;
  if (recent) return `<tr>${base}<td>${escapeHtml(agentName(ticket.assigned_agent_id))}</td><td>${escapeHtml(slaLabel(ticket))}</td></tr>`;
  return `<tr>${base}<td>${escapeHtml(departmentName(ticket.department_id))}</td><td>${escapeHtml(agentName(ticket.assigned_agent_id))}</td></tr>`;
}

function renderRecentTickets() {
  const target = document.querySelector("#recent-ticket-rows");
  if (!state.tickets.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum chamado encontrado.</td></tr>';
    return;
  }
  target.innerHTML = state.tickets.slice(0, 5).map((ticket) => ticketRow(ticket, true)).join("");
}

function renderTickets() {
  const target = document.querySelector("#ticket-rows");
  document.querySelector("#ticket-count-label").textContent = `${state.tickets.length} chamado${state.tickets.length === 1 ? "" : "s"} encontrado${state.tickets.length === 1 ? "" : "s"}`;
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
  if (viewName === "security" && state.user?.role !== "ADMIN") return;
  const titles = { overview: ["OPERAÇÃO", "Visão geral"], tickets: ["ATENDIMENTO", "Chamados"], metrics: ["ANÁLISE", "Métricas"], security: ["SEGURANÇA", "Auditoria"] };
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
  const params = new URLSearchParams({ page: "1", page_size: "100", sort_by: "created_at", sort_order: "desc" });
  const search = document.querySelector("#ticket-search").value.trim();
  const status = document.querySelector("#status-filter").value;
  const priority = document.querySelector("#priority-filter").value;
  if (search) params.set("search", search);
  if (status !== "ALL") params.set("status", status);
  if (priority !== "ALL") params.set("priority", priority);
  const page = await apiRequest(`/tickets?${params}`);
  state.tickets = page.items;
  renderTickets();
  if (!search && status === "ALL" && priority === "ALL") renderRecentTickets();
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

async function loadApplication() {
  await Promise.all([loadDepartments(), loadTickets(), loadDashboard(), loadMetrics()]);
  if (state.user?.role === "ADMIN") await loadAudit();
}

async function startAuthenticatedSession() {
  state.user = await apiRequest("/auth/me");
  updateUserUI();
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  navigate("overview");
  await loadApplication();
}

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

document.querySelector("#status-filter").addEventListener("change", () => loadTickets().catch((error) => showToast(error.message)));
document.querySelector("#priority-filter").addEventListener("change", () => loadTickets().catch((error) => showToast(error.message)));
let searchTimer;
document.querySelector("#ticket-search").addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => loadTickets().catch((error) => showToast(error.message)), 300);
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
    await Promise.all([loadTickets(), loadDashboard(), loadMetrics()]);
    showToast("Chamado criado com sucesso.");
  } catch (error) {
    showToast(error.message);
  }
});

async function boot() {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  document.querySelector("#metrics-date-from").value = dateInputValue(firstDay);
  document.querySelector("#metrics-date-to").value = dateInputValue(today);

  if (!state.token) return;
  try {
    await startAuthenticatedSession();
  } catch {
    clearSession("Sua sessão não pôde ser restaurada. Entre novamente.");
  }
}

boot();
