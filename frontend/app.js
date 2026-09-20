const tickets = [
  { id: 1048, title: "VPN desconecta após autenticação", priority: "HIGH", status: "IN_PROGRESS", department: "Infraestrutura", agent: "Ana Souza", sla: "1h 22m" },
  { id: 1047, title: "Erro ao acessar o ERP financeiro", priority: "HIGH", status: "OPEN", department: "Sistemas", agent: "Não atribuído", sla: "2h 10m" },
  { id: 1046, title: "Notebook sem acesso à impressora", priority: "LOW", status: "CLOSED", department: "Suporte", agent: "Lucas Melo", sla: "Cumprido" },
  { id: 1045, title: "Solicitação de acesso ao Git interno", priority: "MEDIUM", status: "IN_PROGRESS", department: "Sistemas", agent: "Marina Lima", sla: "5h 45m" },
  { id: 1044, title: "Wi-Fi instável na sala de reunião", priority: "MEDIUM", status: "OPEN", department: "Infraestrutura", agent: "Ana Souza", sla: "7h 12m" },
  { id: 1043, title: "Atualização de software corporativo", priority: "LOW", status: "CLOSED", department: "Suporte", agent: "Lucas Melo", sla: "Cumprido" },
];

const auditEvents = [
  { event: "LOGIN_SUCCESS", actor: "admin@securedesk.dev", route: "/auth/login", status: 200, ip: "172.18.0.1", time: "19:12" },
  { event: "FORBIDDEN_ACCESS", actor: "user@securedesk.dev", route: "/security/audit", status: 403, ip: "172.18.0.1", time: "18:54" },
  { event: "RATE_LIMIT_EXCEEDED", actor: "—", route: "/auth/login", status: 429, ip: "10.0.0.42", time: "18:47" },
  { event: "LOGOUT", actor: "agent@securedesk.dev", route: "/auth/logout", status: 204, ip: "172.18.0.1", time: "18:21" },
];

const roleNames = { ADMIN: "Administrador", AGENT: "Agente", USER: "Usuário" };
let currentRole = "ADMIN";
const loginView = document.querySelector("#login-view");
const appView = document.querySelector("#app-view");
const loginForm = document.querySelector("#login-form");
const roleSelect = document.querySelector("#demo-role");
const roleLabel = document.querySelector("#role-label");
const sidebar = document.querySelector(".sidebar");
const toast = document.querySelector("#toast");

function priorityBadge(priority) {
  const labels = { HIGH: "Alta", MEDIUM: "Média", LOW: "Baixa" };
  return `<span class="badge badge--${priority.toLowerCase()}">${labels[priority]}</span>`;
}
function statusBadge(status) {
  const labels = { OPEN: "Aberto", IN_PROGRESS: "Em andamento", CLOSED: "Fechado" };
  const styles = { OPEN: "open", IN_PROGRESS: "progress", CLOSED: "closed" };
  return `<span class="badge badge--${styles[status]}">${labels[status]}</span>`;
}
function renderRecentTickets() {
  document.querySelector("#recent-ticket-rows").innerHTML = tickets.slice(0, 5).map((ticket) => `<tr><td>#${ticket.id}</td><td class="ticket-title">${ticket.title}</td><td>${priorityBadge(ticket.priority)}</td><td>${statusBadge(ticket.status)}</td><td>${ticket.agent}</td><td>${ticket.sla}</td></tr>`).join("");
}
function renderTickets() {
  const search = document.querySelector("#ticket-search").value.trim().toLowerCase();
  const status = document.querySelector("#status-filter").value;
  const priority = document.querySelector("#priority-filter").value;
  const filtered = tickets.filter((ticket) => (!search || ticket.title.toLowerCase().includes(search) || String(ticket.id).includes(search)) && (status === "ALL" || ticket.status === status) && (priority === "ALL" || ticket.priority === priority));
  document.querySelector("#ticket-count-label").textContent = `${filtered.length} chamado${filtered.length === 1 ? "" : "s"} encontrado${filtered.length === 1 ? "" : "s"}`;
  document.querySelector("#ticket-rows").innerHTML = filtered.map((ticket) => `<tr><td>#${ticket.id}</td><td class="ticket-title">${ticket.title}</td><td>${priorityBadge(ticket.priority)}</td><td>${statusBadge(ticket.status)}</td><td>${ticket.department}</td><td>${ticket.agent}</td></tr>`).join("");
}
function renderRankings() {
  const departments = [["Infraestrutura", 18], ["Sistemas", 14], ["Suporte", 11], ["Sem departamento", 5]];
  const agents = [["Ana Souza", 13], ["Lucas Melo", 10], ["Marina Lima", 8], ["Não atribuído", 7]];
  const render = (items) => items.map(([label, value]) => `<div class="rank-item"><span>${label}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, value * 5.5)}%"></div></div><strong>${value}</strong></div>`).join("");
  document.querySelector("#department-bars").innerHTML = render(departments);
  document.querySelector("#agent-bars").innerHTML = render(agents);
}
function renderAudit() {
  document.querySelector("#audit-rows").innerHTML = auditEvents.map((entry) => `<tr><td><strong>${entry.event}</strong></td><td>${entry.actor}</td><td>${entry.route}</td><td>${entry.status}</td><td>${entry.ip}</td><td>${entry.time}</td></tr>`).join("");
}
function updateRoleVisibility() {
  roleLabel.textContent = roleNames[currentRole];
  document.querySelectorAll(".admin-only").forEach((element) => element.classList.toggle("hidden", currentRole !== "ADMIN"));
  if (currentRole !== "ADMIN" && document.querySelector("#view-security:not(.hidden)")) navigate("overview");
}
function navigate(viewName) {
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
  window.setTimeout(() => toast.classList.remove("show"), 2600);
}

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  currentRole = roleSelect.value;
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  updateRoleVisibility();
  navigate("overview");
});
document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.go)));
document.querySelector("#logout-button").addEventListener("click", () => { appView.classList.add("hidden"); loginView.classList.remove("hidden"); });
document.querySelector("#menu-button").addEventListener("click", () => sidebar.classList.toggle("is-open"));
document.querySelectorAll("#ticket-search, #status-filter, #priority-filter").forEach((input) => input.addEventListener("input", renderTickets));

const ticketDialog = document.querySelector("#ticket-dialog");
document.querySelector("#new-ticket-button").addEventListener("click", () => ticketDialog.showModal());
document.querySelector("#ticket-form").addEventListener("submit", (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const title = document.querySelector("#new-title").value.trim();
  if (!title) return;
  tickets.unshift({ id: 1049, title, priority: document.querySelector("#new-priority").value, status: "OPEN", department: document.querySelector("#new-department").value, agent: "Não atribuído", sla: "Calculando" });
  ticketDialog.close();
  document.querySelector("#ticket-form").reset();
  renderTickets();
  renderRecentTickets();
  showToast("Chamado criado no modo demonstração.");
});

renderRecentTickets();
renderTickets();
renderRankings();
renderAudit();
