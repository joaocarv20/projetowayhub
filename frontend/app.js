/* WayHub — SPA (hash router, sem dependências) */
"use strict";

const MIN_TRIP_FEE_CENTS = 500;
const LEAD_MINUTES = 40;
const app = document.getElementById("app");
let timers = [];

// ---------------------------------------------------------------- utilitários
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (cents) => (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtTime = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const fmtDate = (iso) => new Date(iso).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" });
const fmtDateTime = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const fmtDuration = (min) => {
  if (min == null) return "—";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? `${h}h${m ? String(m).padStart(2, "0") : ""}` : `${m} min`;
};
const fmtCountdown = (ms) => {
  const min = Math.floor(ms / 60000);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  return h < 24 ? `${h}h ${min % 60}min` : `${Math.floor(h / 24)}d ${h % 24}h`;
};
const digits = (s) => String(s || "").replace(/\D/g, "");
const svgLogo = `<svg width="20" height="20" viewBox="0 0 32 32"><path d="M5 20h14l-3.5-3.5M19 20l-3.5 3.5M27 12H13l3.5-3.5M13 12l3.5 3.5" stroke="white" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const brand = `<div class="brand"><div class="logo">${svgLogo}</div><span>WayHub</span></div>`;

function toast(msg, type = "") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.className = ""), 3800);
}

function modal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
  return { root, close: () => (root.innerHTML = "") };
}

function every(ms, fn) { timers.push(setInterval(fn, ms)); }

// ---------------------------------------------------------------- sessão & API
const session = {
  get token() { return localStorage.getItem("wh_token"); },
  get role() { return localStorage.getItem("wh_role"); },
  set(token, role) { localStorage.setItem("wh_token", token); localStorage.setItem("wh_role", role); },
  clear() { localStorage.removeItem("wh_token"); localStorage.removeItem("wh_role"); },
};

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && session.token) {
    session.clear();
    location.hash = "#/login";
  }
  if (!res.ok) throw new Error(data.error || "Erro inesperado. Tente novamente.");
  return data;
}

function formData(form) { return Object.fromEntries(new FormData(form).entries()); }

function bindSubmit(form, handler) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    const errBox = form.querySelector(".form-error");
    errBox?.classList.add("hidden");
    btn && (btn.disabled = true);
    try { await handler(); }
    catch (err) {
      if (errBox) { errBox.textContent = err.message; errBox.classList.remove("hidden"); errBox.scrollIntoView({ block: "center", behavior: "smooth" }); }
      else toast(err.message, "error");
    } finally { btn && (btn.disabled = false); }
  });
}

// ---------------------------------------------------------------- roteador
const routes = {
  "/login": viewLogin,
  "/cadastro/centro": viewRegisterHub,
  "/cadastro/motorista": viewRegisterDriver,
  "/motorista/buscar": viewDriverSearch,
  "/motorista/viagens": viewDriverTrips,
  "/motorista/documentos": viewDriverDocs,
  "/centro/pedidos": viewHubOrders,
  "/centro/acompanhamento": viewHubMonitoring,
  "/centro/previsao": viewHubPrediction,
};

function home() { return session.role === "hub" ? "/centro/pedidos" : session.role === "driver" ? "/motorista/buscar" : "/login"; }

function router() {
  timers.forEach(clearInterval);
  timers = [];
  document.getElementById("modal-root").innerHTML = "";
  let path = location.hash.slice(1) || home();
  const isPublic = path === "/login" || path.startsWith("/cadastro");
  if (!session.token && !isPublic) path = "/login";
  if (session.token && isPublic) path = home();
  if (session.token && path.startsWith("/centro") && session.role !== "hub") path = home();
  if (session.token && path.startsWith("/motorista") && session.role !== "driver") path = home();
  if (`#${path}` !== location.hash) history.replaceState(null, "", `#${path}`);
  (routes[path] || viewLogin)();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", router);

function logout() { session.clear(); location.hash = "#/login"; }

// ================================================================ AUTENTICAÇÃO
let chosenRole = localStorage.getItem("wh_last_role") || "driver";

function viewLogin() {
  app.innerHTML = `
  <div class="auth-wrap"><div class="auth-card">
    ${brand}
    <p class="tagline">Caronas de pedidos entre Centros Logísticos. Aproveite o espaço livre da sua viagem.</p>
    <div class="segmented" id="role">
      <button type="button" data-role="hub">🏢 Centro Logístico<small>Publicar pedidos</small></button>
      <button type="button" data-role="driver">🚗 Motorista<small>Levar cargas</small></button>
    </div>
    <form id="f">
      <div class="form-error hidden"></div>
      <label class="field"><span>E-mail</span><input name="email" type="email" autocomplete="email" required></label>
      <label class="field"><span>Senha</span><input name="password" type="password" autocomplete="current-password" required></label>
      <button class="btn block" type="submit">Entrar</button>
    </form>
    <p class="auth-foot">Ainda não tem conta? <a href="#" id="go-register">Cadastre-se</a></p>
    <div class="demo-hint"><strong>Contas demo</strong> (senha <code>wayhub123</code>):<br>
      Centro: hub.anapolis@wayhub.com · hub.goiania@wayhub.com<br>Motorista: motorista@wayhub.com</div>
  </div></div>`;
  const seg = document.getElementById("role");
  const paint = () => seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.role === chosenRole));
  seg.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) { chosenRole = b.dataset.role; localStorage.setItem("wh_last_role", chosenRole); paint(); }
  });
  paint();
  document.getElementById("go-register").onclick = (e) => {
    e.preventDefault();
    location.hash = chosenRole === "hub" ? "#/cadastro/centro" : "#/cadastro/motorista";
  };
  const form = document.getElementById("f");
  bindSubmit(form, async () => {
    const data = await api("/api/auth/login", { method: "POST", body: { ...formData(form), role: chosenRole } });
    session.set(data.token, data.role);
    location.hash = `#${home()}`;
  });
}

function viewRegisterHub() {
  app.innerHTML = `
  <div class="auth-wrap"><div class="auth-card wide">
    ${brand}
    <p class="tagline">Cadastro de <strong>Centro Logístico</strong></p>
    <form id="f">
      <div class="form-error hidden"></div>
      <fieldset><legend>Dados da empresa</legend>
        <label class="field"><span>Nome do Centro Logístico</span><input name="name" required></label>
        <div class="grid c2">
          <label class="field"><span>CNPJ</span><input name="cnpj" inputmode="numeric" placeholder="00.000.000/0000-00" required></label>
          <label class="field"><span>Telefone / WhatsApp</span><input name="phone" type="tel" placeholder="(62) 90000-0000" required></label>
          <label class="field"><span>E-mail</span><input name="email" type="email" required></label>
          <label class="field"><span>Senha</span><input name="password" type="password" minlength="6" required></label>
        </div>
      </fieldset>
      <fieldset><legend>Endereço de origem</legend>
        <div class="grid c3">
          <label class="field"><span>CEP</span><input name="cep" id="cep" inputmode="numeric" placeholder="00000-000" required></label>
          <label class="field" style="grid-column: span 2"><span>Rua e número</span><input name="street" id="street" required></label>
          <label class="field"><span>Bairro</span><input name="neighborhood" id="neighborhood" required></label>
          <label class="field"><span>Cidade</span><input name="city" id="city" required></label>
          <label class="field"><span>Estado (UF)</span><input name="state" id="state" maxlength="2" required></label>
        </div>
      </fieldset>
      <button class="btn block" type="submit">Criar conta do Centro</button>
    </form>
    <p class="auth-foot"><a href="#/login">← Voltar para o login</a></p>
  </div></div>`;
  // Preenchimento automático de endereço via ViaCEP
  document.getElementById("cep").addEventListener("blur", async (e) => {
    const cep = digits(e.target.value);
    if (cep.length !== 8) return;
    try {
      const r = await (await fetch(`https://viacep.com.br/ws/${cep}/json/`)).json();
      if (r.erro) return;
      const set = (id, v) => { const el = document.getElementById(id); if (!el.value && v) el.value = v; };
      set("street", r.logradouro); set("neighborhood", r.bairro); set("city", r.localidade); set("state", r.uf);
    } catch { /* offline: preenchimento manual */ }
  });
  const form = document.getElementById("f");
  bindSubmit(form, async () => {
    const data = await api("/api/auth/register/hub", { method: "POST", body: formData(form) });
    session.set(data.token, data.role);
    toast("Centro Logístico cadastrado!", "success");
    location.hash = "#/centro/pedidos";
  });
}

function viewRegisterDriver() {
  app.innerHTML = `
  <div class="auth-wrap"><div class="auth-card">
    ${brand}
    <p class="tagline">Cadastro de <strong>Motorista</strong> · passo 1 de 2</p>
    <form id="f">
      <div class="form-error hidden"></div>
      <div class="grid c2">
        <label class="field"><span>Nome</span><input name="first_name" required></label>
        <label class="field"><span>Sobrenome</span><input name="last_name" required></label>
      </div>
      <label class="field"><span>E-mail</span><input name="email" type="email" required></label>
      <label class="field"><span>Senha</span><input name="password" type="password" minlength="6" required></label>
      <label class="field"><span>Telefone</span><input name="phone" type="tel" placeholder="(62) 90000-0000" required></label>
      <label class="field"><span>Cidade de origem</span><input name="origin_city" required></label>
      <label class="field"><span>Endereço residencial</span><input name="home_address" required></label>
      <button class="btn block" type="submit">Continuar → Veículo e documentos</button>
    </form>
    <p class="auth-foot"><a href="#/login">← Voltar para o login</a></p>
  </div></div>`;
  const form = document.getElementById("f");
  bindSubmit(form, async () => {
    const data = await api("/api/auth/register/driver", { method: "POST", body: formData(form) });
    session.set(data.token, data.role);
    location.hash = "#/motorista/documentos";
  });
}

// ================================================================ MOTORISTA
function driverNav(active) {
  const items = [["buscar", "🔍", "Buscar"], ["viagens", "🧭", "Viagens"], ["documentos", "🪪", "Veículo"]];
  return `<div class="bottom-nav"><nav>
    ${items.map(([k, i, l]) => `<a href="#/motorista/${k}" class="${active === k ? "active" : ""}"><span class="i">${i}</span>${l}</a>`).join("")}
    <a href="#" onclick="logout();return false"><span class="i">↩</span>Sair</a>
  </nav></div>`;
}

async function viewDriverDocs() {
  app.innerHTML = `<div class="m-shell">
    <header class="m-header slim">${brand}<h1>Veículo e documentos</h1><p>Segurança para centros e motoristas.</p></header>
    <div class="m-body flat" id="body"><div class="empty">Carregando…</div></div>
  </div>${driverNav("documentos")}`;
  let me, docs;
  try { [me, docs] = await Promise.all([api("/api/me"), api("/api/driver/documents")]); }
  catch (e) { return toast(e.message, "error"); }
  const v = me.vehicle || {};
  const has = Object.fromEntries(docs.map((d) => [d.doc_type, d]));
  const docField = (key, label) => `
    <label class="field"><span>${label} ${has[key] ? `· <a href="${has[key].url}" target="_blank" rel="noopener">✔ enviado (ver)</a>` : ""}</span>
      <input type="file" name="${key}" accept="image/jpeg,image/png,image/webp,application/pdf" ${has[key] ? "" : "required"}></label>`;
  const opt = (val, label) => `<option value="${val}" ${v.cargo_type === val ? "selected" : ""}>${label}</option>`;

  document.getElementById("body").innerHTML = `
    ${me.driver.status === "active"
      ? `<div class="check" style="cursor:default"><span>✅</span><span><strong>Cadastro aprovado.</strong><br><span class="small muted">Você já pode solicitar cargas. Atualize os dados se trocar de veículo.</span></span></div>`
      : `<div class="check" style="cursor:default;background:var(--amber-bg)"><span>⚠️</span><span><strong>Passo 2 de 2:</strong> cadastre seu veículo e envie os documentos para liberar as solicitações.</span></div>`}
    <form id="f" class="trip-card">
      <div class="form-error hidden"></div>
      <fieldset><legend>Veículo</legend>
        <div class="grid c2">
          <label class="field"><span>Placa</span><input name="plate" value="${esc(v.plate)}" placeholder="ABC1D23" required></label>
          <label class="field"><span>Ano</span><input name="year" type="number" min="1980" value="${esc(v.year)}" required></label>
          <label class="field"><span>Modelo</span><input name="model" value="${esc(v.model)}" required></label>
          <label class="field"><span>Cor</span><input name="color" value="${esc(v.color)}" required></label>
        </div>
        <label class="field"><span>Tipo de porta-malas / caçamba</span>
          <select name="cargo_type" id="cargo" required>
            <option value="">Selecione…</option>
            ${opt("porta_malas_pequeno", "Porta-malas pequeno (hatch) · até 50 kg")}
            ${opt("porta_malas_medio", "Porta-malas médio (sedan) · até 100 kg")}
            ${opt("porta_malas_grande", "Porta-malas grande (SUV/perua) · até 200 kg")}
            ${opt("cacamba", "Caçamba (picape) · até 600 kg")}
            ${opt("furgao", "Furgão · até 1.000 kg")}
          </select></label>
        <label class="field"><span>Capacidade de carga livre (kg)</span><input name="capacity_kg" id="cap" type="number" min="1" step="1" value="${esc(v.capacity_kg ? Math.round(v.capacity_kg) : "")}" placeholder="Padrão do tipo selecionado"></label>
      </fieldset>
      <fieldset><legend>Documentos</legend>
        ${docField("cnh", "Foto da CNH")}
        ${docField("crlv", "Foto do CRLV (documento do veículo)")}
        <label class="check"><input type="checkbox" name="owned_by_third_party" id="third" value="1" ${v.owned_by_third_party ? "checked" : ""}>
          <span><strong>O veículo está em nome de outra pessoa?</strong><br><span class="small muted">Nesse caso, é obrigatório enviar o RG/CPF do proprietário legal.</span></span></label>
        <div id="owner-wrap">${docField("owner_id", "Documento de identificação (RG/CPF) do proprietário")}</div>
      </fieldset>
      <p class="small muted">🔒 Arquivos armazenados em storage privado e acessados apenas por links assinados temporários.</p>
      <button class="btn block" type="submit">Salvar e enviar documentos</button>
    </form>`;
  const third = document.getElementById("third"), ownerWrap = document.getElementById("owner-wrap");
  const ownerInput = ownerWrap.querySelector("input");
  const syncOwner = () => {
    ownerWrap.classList.toggle("hidden", !third.checked);
    ownerInput.required = third.checked && !has.owner_id;
  };
  third.addEventListener("change", syncOwner);
  syncOwner();
  const form = document.getElementById("f");
  bindSubmit(form, async () => {
    const fd = new FormData(form);
    for (const [k, val] of [...fd.entries()]) if (val instanceof File && !val.name) fd.delete(k);
    if (!third.checked) fd.delete("owner_id");
    await api("/api/driver/onboarding", { method: "POST", form: fd });
    toast("Cadastro concluído! Você já pode buscar cargas.", "success");
    location.hash = "#/motorista/buscar";
  });
}

const searchState = { origin: "", destination: "", date: "", time: "", results: [], selected: new Map(), vehicle: null, driver: null };

async function viewDriverSearch() {
  const s = searchState;
  app.innerHTML = `<div class="m-shell">
    <header class="m-header">${brand}<h1>Para onde você vai?</h1><p>Leve pedidos entre Centros Logísticos e ganhe na sua viagem.</p></header>
    <div class="m-body">
      <form class="search-card" id="sf" style="position:relative">
        <div class="search-row"><span class="dot"></span><input name="origin" list="cities" placeholder="Saindo de (cidade)" value="${esc(s.origin)}" autocomplete="off"></div>
        <div class="search-row"><span class="dot fill"></span><input name="destination" list="cities" placeholder="Indo para (cidade)" value="${esc(s.destination)}" autocomplete="off"></div>
        <button type="button" class="swap" id="swap" title="Inverter">⇅</button>
        <div class="search-split">
          <div class="search-row"><span class="ico">📅</span><input name="date" type="date" value="${esc(s.date)}"></div>
          <div class="search-row"><span class="ico">🕒</span><input name="time" type="time" value="${esc(s.time)}"></div>
        </div>
        <button class="btn" type="submit">Buscar cargas</button>
        <datalist id="cities"></datalist>
      </form>
      <div id="alert"></div>
      <div class="section-title"><h2 id="res-title">Cargas disponíveis</h2><span class="small muted" id="res-count"></span></div>
      <div id="results"><div class="empty">Carregando…</div></div>
    </div>
  </div>
  <div class="checkout-bar hidden" id="cbar"></div>
  ${driverNav("buscar")}`;

  const form = document.getElementById("sf");
  document.getElementById("swap").onclick = () => {
    const [o, d] = [form.origin.value, form.destination.value];
    form.origin.value = d; form.destination.value = o;
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); Object.assign(s, formData(form)); runSearch(); });

  api("/api/cities").then((list) => {
    document.getElementById("cities").innerHTML = list.map((c) => `<option value="${esc(c)}">`).join("");
  });
  try {
    const me = await api("/api/me");
    s.vehicle = me.vehicle; s.driver = me.driver;
    if (me.driver.status !== "active") {
      document.getElementById("alert").innerHTML = `<div class="check" style="margin-top:14px;background:var(--amber-bg);cursor:pointer" onclick="location.hash='#/motorista/documentos'">
        <span>⚠️</span><span><strong>Complete seu cadastro</strong><br><span class="small">Envie veículo, CNH e CRLV para poder solicitar cargas. Toque aqui.</span></span></div>`;
    }
    if (!s.origin && !s.results.length) { s.origin = me.driver.origin_city; form.origin.value = s.origin; }
  } catch { /* segue sem dados do perfil */ }
  runSearch();
  every(30000, renderResults); // atualiza o cronômetro de antecedência
}

async function runSearch() {
  const s = searchState;
  const params = new URLSearchParams();
  if (s.origin) params.set("origin", s.origin);
  if (s.destination) params.set("destination", s.destination);
  if (s.date || s.time) {
    const day = s.date || new Date().toLocaleDateString("sv-SE");
    params.set("from", new Date(`${day}T${s.time || "00:00"}`).toISOString());
    if (s.date) params.set("to", new Date(`${day}T23:59:59`).toISOString());
  }
  try {
    s.results = await api(`/api/driver/orders/search?${params}`);
    // mantém seleção somente de pedidos ainda disponíveis
    const ids = new Set(s.results.map((o) => o.id));
    for (const id of [...s.selected.keys()]) if (!ids.has(id)) s.selected.delete(id);
    renderResults();
  } catch (e) { toast(e.message, "error"); }
}

function renderResults() {
  const s = searchState;
  const box = document.getElementById("results");
  if (!box) return;
  const now = Date.now();
  // Lock-in: pedidos cujo prazo de solicitação (retirada − 40 min) já passou saem da lista
  s.results = s.results.filter((o) => new Date(o.request_deadline) > now);
  for (const id of [...s.selected.keys()]) if (!s.results.some((o) => o.id === id)) s.selected.delete(id);

  const title = s.origin || s.destination ? `${esc(s.origin || "Qualquer cidade")} ➔ ${esc(s.destination || "Qualquer cidade")}` : "Cargas disponíveis";
  document.getElementById("res-title").innerHTML = title;
  document.getElementById("res-count").textContent = `${s.results.length} pedido(s)`;

  if (!s.results.length) {
    box.innerHTML = `<div class="empty"><div class="big">📦</div><strong>Nenhuma carga encontrada</strong><p class="small">Tente outra cidade ou data. Pedidos aparecem até ${LEAD_MINUTES} min antes da retirada.</p></div>`;
  } else {
    let lastDay = "";
    box.innerHTML = s.results.map((o) => {
      const day = fmtDate(o.pickup_at);
      const header = day !== lastDay ? `<div class="small muted" style="margin:14px 4px 8px;font-weight:700;text-transform:capitalize">${day}</div>` : "";
      lastDay = day;
      const left = new Date(o.request_deadline) - now;
      const sel = s.selected.has(o.id);
      const arrival = o.eta_minutes != null ? fmtTime(new Date(new Date(o.pickup_at).getTime() + o.eta_minutes * 60000)) : "";
      return `${header}
      <article class="order-card ${sel ? "selected" : ""}">
        <div class="oc-top">
          <div class="route">
            <div class="time">${fmtTime(o.pickup_at)}</div><div class="line"><i></i><b></b></div>
            <div><div class="city">${esc(o.origin.city)}</div><div class="hub">${esc(o.origin.name)} · ${esc(o.origin.neighborhood)}</div></div>
            <div class="eta">${fmtDuration(o.eta_minutes)}</div><div class="line"><b></b></div><div></div>
            <div class="time">${arrival}</div><div class="line"><i></i></div>
            <div><div class="city">${esc(o.destination.city)}</div><div class="hub" style="margin:0">${esc(o.destination.name)} · ${esc(o.destination.neighborhood)}</div></div>
          </div>
          <div class="fee"><strong>${money(o.fee_cents)}</strong><span>Taxa de carona</span></div>
        </div>
        <div class="oc-meta">
          <span class="chip size">📦 Tam. ${esc(o.size)}</span>
          <span class="chip">📐 ${+o.height_cm}×${+o.width_cm}×${+o.length_cm} cm</span>
          <span class="chip">⚖️ ${(+o.weight_kg).toLocaleString("pt-BR")} kg</span>
          <span class="chip ${left < 3600000 ? "warn" : ""}">⏳ Solicite em até ${fmtCountdown(left)}</span>
        </div>
        <div class="oc-foot">
          <span class="code mono">${esc(o.code)}</span>
          <button class="btn small ${sel ? "light" : ""}" data-toggle="${o.id}">${sel ? "✓ Adicionado" : "+ Solicitar"}</button>
        </div>
      </article>`;
    }).join("");
    box.querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", () => {
      const id = +b.dataset.toggle;
      if (s.selected.has(id)) s.selected.delete(id);
      else s.selected.set(id, s.results.find((o) => o.id === id));
      renderResults();
    }));
  }
  renderCheckout();
}

function renderCheckout() {
  const s = searchState;
  const bar = document.getElementById("cbar");
  if (!bar) return;
  const items = [...s.selected.values()];
  bar.classList.toggle("hidden", !items.length);
  if (!items.length) return;
  const total = items.reduce((a, o) => a + o.fee_cents, 0);
  const weight = items.reduce((a, o) => a + o.weight_kg, 0);
  const cap = s.vehicle?.capacity_kg;
  const overCap = cap && weight > cap;
  const ok = total >= MIN_TRIP_FEE_CENTS && !overCap;
  const pct = Math.min(100, (total / MIN_TRIP_FEE_CENTS) * 100);
  const hint = overCap
    ? `⚠️ Peso ${weight.toFixed(1)} kg excede a capacidade do veículo (${Math.round(cap)} kg)`
    : total < MIN_TRIP_FEE_CENTS
      ? `Faltam ${money(MIN_TRIP_FEE_CENTS - total)} para a taxa mínima de ${money(MIN_TRIP_FEE_CENTS)}`
      : `✓ Taxa mínima atingida · ${weight.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg${cap ? ` de ${Math.round(cap)} kg` : ""}`;
  bar.innerHTML = `<div class="checkout-inner">
    <div class="checkout-row">
      <div><div class="small" style="opacity:.8">${items.length} pedido(s) na viagem</div><div class="checkout-total">${money(total)}</div></div>
      <button class="btn" id="confirm" ${ok ? "" : "disabled"}>Confirmar carona</button>
    </div>
    <div class="progress"><div style="width:${pct}%"></div></div>
    <div class="checkout-hint">${hint}</div>
  </div>`;
  document.getElementById("confirm").onclick = confirmTrip;
}

async function confirmTrip() {
  const s = searchState;
  const btn = document.getElementById("confirm");
  btn.disabled = true;
  try {
    const r = await api("/api/driver/trips", { method: "POST", body: { order_ids: [...s.selected.keys()] } });
    s.selected.clear();
    const m = modal(`<div class="big">🎉</div><h2>Carona solicitada!</h2>
      <p class="muted">Ganho previsto: <strong>${money(r.total_fee_cents)}</strong>. Na coleta, informe ao atendente o código abaixo:</p>
      <div class="otp-box"><div class="lbl">Código 1 · Retirada</div><div class="otp">${esc(r.pickup_code)}</div></div>
      <button class="btn block" id="ok">Ver minhas viagens</button>`);
    m.root.querySelector("#ok").onclick = () => { m.close(); location.hash = "#/motorista/viagens"; };
  } catch (e) {
    toast(e.message, "error");
    runSearch();
  }
}

async function viewDriverTrips() {
  app.innerHTML = `<div class="m-shell">
    <header class="m-header slim">${brand}<h1>Minhas viagens</h1><p>Códigos de retirada e entrega.</p></header>
    <div class="m-body flat" id="body"><div class="empty">Carregando…</div></div>
  </div>${driverNav("viagens")}`;
  const load = async () => {
    let trips;
    try { trips = await api("/api/driver/trips"); } catch (e) { return toast(e.message, "error"); }
    const body = document.getElementById("body");
    if (!body) return;
    if (!trips.length) {
      body.innerHTML = `<div class="empty"><div class="big">🧭</div><strong>Nenhuma viagem ainda</strong><p class="small">Busque cargas no seu trajeto e selecione até atingir ${money(MIN_TRIP_FEE_CENTS)}.</p><a class="btn" href="#/motorista/buscar">Buscar cargas</a></div>`;
      return;
    }
    body.innerHTML = trips.map((t) => {
      const cities = [...new Set(t.orders.map((o) => `${o.origin.city} ➔ ${o.destination.city}`))].join(" · ");
      const codes = t.status === "closed"
        ? `<div class="otp-box" style="border-style:solid"><div class="lbl">Viagem encerrada</div><div style="font-weight:700;margin-top:4px">💰 ${money(t.total_fee_cents)} liberados para pagamento</div></div>`
        : `<div class="otp-box ${t.orders.some((o) => o.status === "requested") ? "" : "locked"}">
             <div class="lbl">Código 1 · Retirada na origem</div>
             <div class="otp">${t.orders.some((o) => o.status === "requested") ? esc(t.pickup_code) : "✓ Coleta validada"}</div></div>
           <div class="otp-box ${t.delivery_code ? "" : "locked"}">
             <div class="lbl">Código 2 · Entrega no destino</div>
             <div class="otp">${t.delivery_code ? esc(t.delivery_code) : "🔒 Disponível após a coleta"}</div></div>`;
      return `<div class="trip-card">
        <div class="trip-head"><div><strong>${esc(cities)}</strong><div class="small muted">Viagem #${t.id} · ${money(t.total_fee_cents)}</div></div>
          <span class="badge ${t.status}">${t.status_label}</span></div>
        ${codes}
        ${t.orders.map((o) => `<div class="trip-order">
          <div><span class="mono">${esc(o.code)}</span><div class="small muted">Retirada ${fmtDateTime(o.pickup_at)} · ${esc(o.origin.name)} (${esc(o.origin.neighborhood)}) ➔ ${esc(o.destination.name)}</div></div>
          <div style="text-align:right"><span class="badge ${o.status}">${o.status_label}</span><div class="small" style="margin-top:4px;font-weight:700">${money(o.fee_cents)}</div></div>
        </div>`).join("")}
      </div>`;
    }).join("");
  };
  await load();
  every(15000, load);
}

// ================================================================ CENTRO LOGÍSTICO
let hubCache = null;

function hubShell(active, inner) {
  const h = hubCache || {};
  return `<div class="h-shell">
    <header class="h-top"><div class="h-top-inner">
      ${brand}
      <nav>
        <a href="#/centro/pedidos" class="${active === "pedidos" ? "active" : ""}">Pedidos</a>
        <a href="#/centro/acompanhamento" class="${active === "acompanhamento" ? "active" : ""}">Acompanhamento</a>
        <a href="#/centro/previsao" class="${active === "previsao" ? "active" : ""}">Previsão de prazo</a>
      </nav>
      <div class="h-user"><div class="who"><strong>${esc(h.name || "")}</strong><br><span class="muted">${esc(h.neighborhood || "")} · ${esc(h.city || "")}</span></div>
        <button class="btn ghost small" onclick="logout()">Sair</button></div>
    </div></header>
    <main class="h-main">${inner}</main>
  </div>`;
}

async function loadHub() {
  if (!hubCache) hubCache = (await api("/api/me")).hub;
  return hubCache;
}
window.addEventListener("hashchange", () => { if (session.role !== "hub") hubCache = null; });

async function viewHubOrders() {
  try { await loadHub(); } catch (e) { return toast(e.message, "error"); }
  const h = hubCache;
  const defaultPickup = new Date(Date.now() + 3 * 3600000);
  defaultPickup.setMinutes(0, 0, 0);
  const localIso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

  app.innerHTML = hubShell("pedidos", `
    <div class="h-title"><div><h1>Cadastro de pedidos</h1><p class="muted" style="margin:4px 0 0">Publique volumes para motoristas que já vão fazer o trajeto.</p></div></div>
    <div class="h-cols">
      <form class="panel" id="f">
        <h2>Novo pedido</h2>
        <div class="form-error hidden"></div>
        <label class="field"><span>Código do pedido <span class="muted">(opcional — gerado automaticamente)</span></span><input name="code" placeholder="WH-AAMMDD-XXXX"></label>
        <div class="origin-box"><span class="small muted">Origem</span><br><strong>${esc(h.name)}</strong><br>${esc(h.neighborhood)} · ${esc(h.city)}/${esc(h.state)}</div>
        <label class="field"><span>Destino (Centro Logístico)</span><select name="dest_hub_id" id="dest" required><option value="">Carregando…</option></select></label>
        <div class="grid c3">
          <label class="field"><span>Altura (cm)</span><input name="height_cm" type="number" step="0.1" min="0.1" required></label>
          <label class="field"><span>Largura (cm)</span><input name="width_cm" type="number" step="0.1" min="0.1" required></label>
          <label class="field"><span>Compr. (cm)</span><input name="length_cm" type="number" step="0.1" min="0.1" required></label>
        </div>
        <div class="grid c2">
          <label class="field"><span>Peso (kg)</span><input name="weight_kg" type="number" step="0.01" min="0.01" required></label>
          <label class="field"><span>Retirada prevista</span><input name="pickup_at" type="datetime-local" value="${localIso(defaultPickup)}" required></label>
        </div>
        <div class="fee-preview"><div><div class="small" style="opacity:.8">Taxa ao motorista (automática)</div><div class="small" id="fee-detail" style="opacity:.7">Informe dimensões e peso</div></div><strong id="fee">—</strong></div>
        <button class="btn block" type="submit">Publicar pedido</button>
      </form>
      <section class="panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h2 style="margin:0">Pedidos publicados</h2><span class="small muted" id="cnt"></span></div>
        <div class="table-wrap" id="list"><div class="empty">Carregando…</div></div>
      </section>
    </div>`);

  api("/api/hubs").then((hubs) => {
    const others = hubs.filter((x) => x.id !== h.id);
    document.getElementById("dest").innerHTML = `<option value="">Selecione o centro de destino…</option>` +
      others.map((x) => `<option value="${x.id}">${esc(x.city)} — ${esc(x.name)} (${esc(x.neighborhood)})</option>`).join("");
  });

  const form = document.getElementById("f");
  let quoteT;
  form.addEventListener("input", () => {
    clearTimeout(quoteT);
    quoteT = setTimeout(async () => {
      const d = formData(form);
      if (!(d.height_cm > 0 && d.width_cm > 0 && d.length_cm > 0 && d.weight_kg > 0)) return;
      try {
        const q = await api(`/api/pricing/quote?${new URLSearchParams({ height_cm: d.height_cm, width_cm: d.width_cm, length_cm: d.length_cm, weight_kg: d.weight_kg })}`);
        document.getElementById("fee").textContent = money(q.fee_cents);
        document.getElementById("fee-detail").textContent = `Tamanho ${q.size} · peso cubado ${q.cubic_weight_kg.toLocaleString("pt-BR")} kg`;
      } catch { /* valores inválidos */ }
    }, 250);
  });
  bindSubmit(form, async () => {
    const d = formData(form);
    const o = await api("/api/hub/orders", { method: "POST", body: { ...d, pickup_at: new Date(d.pickup_at).toISOString() } });
    toast(`Pedido ${o.code} publicado · taxa ${money(o.fee_cents)}`, "success");
    ["code", "height_cm", "width_cm", "length_cm", "weight_kg"].forEach((n) => (form[n].value = ""));
    document.getElementById("fee").textContent = "—";
    loadOrders();
  });

  const STATUS = { available: "Disponível", requested: "Solicitado", in_progress: "Em Andamento", closed: "Encerrado", cancelled: "Cancelado" };
  async function loadOrders() {
    let orders;
    try { orders = await api("/api/hub/orders"); } catch (e) { return toast(e.message, "error"); }
    const list = document.getElementById("list");
    if (!list) return;
    document.getElementById("cnt").textContent = `${orders.length} pedido(s)`;
    if (!orders.length) { list.innerHTML = `<div class="empty"><div class="big">📦</div>Nenhum pedido publicado ainda.</div>`; return; }
    list.innerHTML = `<table class="responsive"><thead><tr><th>Código</th><th>Destino</th><th>Volume / Peso</th><th>Retirada</th><th>Taxa</th><th>Status</th><th></th></tr></thead><tbody>
      ${orders.map((o) => `<tr>
        <td data-l="Código" class="mono">${esc(o.code)}</td>
        <td data-l="Destino"><div>${esc(o.destination.name)}</div><div class="sub">${esc(o.destination.neighborhood)} · ${esc(o.destination.city)}</div></td>
        <td data-l="Volume"><div>${+o.height_cm}×${+o.width_cm}×${+o.length_cm} cm</div><div class="sub">${(+o.weight_kg).toLocaleString("pt-BR")} kg · Tam. ${esc(o.size)}</div></td>
        <td data-l="Retirada" class="nowrap">${fmtDateTime(o.pickup_at)}</td>
        <td data-l="Taxa"><strong>${money(o.fee_cents)}</strong></td>
        <td data-l="Status"><span class="badge ${o.status}">${STATUS[o.status]}</span></td>
        <td data-l="">${o.status === "available" ? `<button class="btn danger small" data-cancel="${o.id}">Cancelar</button>` : ""}</td>
      </tr>`).join("")}</tbody></table>`;
    list.querySelectorAll("[data-cancel]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Cancelar este pedido?")) return;
      try { await api(`/api/hub/orders/${b.dataset.cancel}/cancel`, { method: "POST" }); loadOrders(); }
      catch (e) { toast(e.message, "error"); }
    }));
  }
  loadOrders();
  every(20000, loadOrders);
}

let monitorFilter = "all";

async function viewHubMonitoring() {
  try { await loadHub(); } catch (e) { return toast(e.message, "error"); }
  app.innerHTML = hubShell("acompanhamento", `
    <div class="h-title"><div><h1>Acompanhamento e histórico</h1><p class="muted" style="margin:4px 0 0">Operações ativas e encerradas · atualização automática.</p></div></div>
    <form class="validate" id="vf">
      <div class="txt"><strong>🔐 Validar código do motorista</strong><p>Código 1 libera a carga (Em Andamento) · Código 2 confirma a entrega (Encerrado + pagamento).</p></div>
      <input name="code" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="off" required>
      <button class="btn" type="submit">Validar</button>
      <div class="validate-msg hidden" id="vmsg"></div>
    </form>
    <div class="stats" id="stats"></div>
    <section class="panel">
      <div class="tabs" id="tabs">
        <button data-f="all">Todos</button><button data-f="outbound">Saindo daqui</button><button data-f="inbound">Chegando aqui</button>
      </div>
      <div class="table-wrap" id="table"><div class="empty">Carregando…</div></div>
    </section>`);

  let rows = [];
  const render = () => {
    const count = (st) => rows.filter((r) => r.status === st).length;
    const paid = rows.filter((r) => r.paid_at && r.direction === "outbound").reduce((a, r) => a + r.fee_cents, 0);
    document.getElementById("stats").innerHTML = `
      <div class="stat requested"><div class="n">${count("requested")}</div><div class="l">Solicitado</div></div>
      <div class="stat in_progress"><div class="n">${count("in_progress")}</div><div class="l">Em Andamento</div></div>
      <div class="stat closed"><div class="n">${count("closed")}</div><div class="l">Encerrado</div></div>
      <div class="stat"><div class="n" style="font-size:22px;padding-top:6px">${money(paid)}</div><div class="l">Taxas pagas (saída)</div></div>`;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.f === monitorFilter));
    const list = rows.filter((r) => monitorFilter === "all" || r.direction === monitorFilter);
    const table = document.getElementById("table");
    if (!list.length) { table.innerHTML = `<div class="empty"><div class="big">🛰️</div>Nenhuma operação por aqui ainda. Pedidos aparecem quando um motorista solicita a carona.</div>`; return; }
    table.innerHTML = `<table class="responsive"><thead><tr><th>Pedido</th><th>Origem</th><th>Destino</th><th>Tempo médio</th><th>Motorista</th><th>Status</th><th>Pagamento</th></tr></thead><tbody>
      ${list.map((r) => {
        const wa = digits(r.driver.phone);
        return `<tr>
        <td data-l="Pedido"><span class="mono">${esc(r.code)}</span><div class="sub">${r.direction === "outbound" ? "↗ Saída" : "↙ Chegada"} · ${money(r.fee_cents)}</div></td>
        <td data-l="Origem"><div>${esc(r.origin.name)}</div><div class="sub">${esc(r.origin.neighborhood)} · ${esc(r.origin.city)}</div></td>
        <td data-l="Destino"><div>${esc(r.destination.name)}</div><div class="sub">${esc(r.destination.neighborhood)} · ${esc(r.destination.city)}</div></td>
        <td data-l="Tempo médio">${fmtDuration(r.eta_minutes)}<div class="sub">Retirada ${fmtDateTime(r.pickup_at)}</div></td>
        <td data-l="Motorista"><div>${esc(r.driver.name)}</div><div class="sub"><a href="https://wa.me/55${wa}" target="_blank" rel="noopener">${esc(r.driver.phone)}</a></div></td>
        <td data-l="Status"><span class="badge ${r.status}">${esc(r.status_label)}</span>
          <div class="sub">${r.delivered_at ? `Entregue ${fmtDateTime(r.delivered_at)}` : r.picked_up_at ? `Coletado ${fmtDateTime(r.picked_up_at)}` : ""}</div></td>
        <td data-l="Pagamento">${r.paid_at ? `<span class="badge closed">✓ Pago</span>` : `<span class="sub">Pendente</span>`}</td>
      </tr>`;
      }).join("")}</tbody></table>`;
  };
  const load = async () => {
    try { rows = await api("/api/hub/monitoring"); } catch (e) { return toast(e.message, "error"); }
    if (document.getElementById("table")) render();
  };
  document.getElementById("tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) { monitorFilter = b.dataset.f; render(); }
  });

  const vf = document.getElementById("vf"), vmsg = document.getElementById("vmsg");
  vf.code.addEventListener("input", () => (vf.code.value = digits(vf.code.value).slice(0, 6)));
  vf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = vf.querySelector("button");
    btn.disabled = true;
    try {
      const r = await api("/api/hub/validate-code", { method: "POST", body: { code: vf.code.value } });
      vmsg.className = "validate-msg ok";
      vmsg.textContent = `✓ ${r.message} (${r.orders.join(", ")})`;
      vf.code.value = "";
      load();
    } catch (err) {
      vmsg.className = "validate-msg err";
      vmsg.textContent = `✕ ${err.message}`;
    } finally { btn.disabled = false; }
  });

  await load();
  every(15000, load);
}

// Previsão de prazo de trânsito pelo modelo supervisionado (OptiRoute AI)
async function viewHubPrediction() {
  try { await loadHub(); } catch (e) { return toast(e.message, "error"); }
  const h = hubCache;
  const fmtDays = (d) => `${d.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${d === 1 ? "dia" : "dias"}`;
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  app.innerHTML = hubShell("previsao", `
    <div class="h-title"><div><h1>Previsão de prazo de entrega</h1><p class="muted" style="margin:4px 0 0">Modelo de Machine Learning treinado com ~95 mil entregas reais (Olist, 2016–2018).</p></div></div>
    <div class="h-cols">
      <form class="panel" id="f">
        <h2>Dados do envio</h2>
        <div class="form-error hidden"></div>
        <div class="grid c2">
          <label class="field"><span>CEP de origem</span><input name="origin_cep" inputmode="numeric" value="${esc(h.cep)}" placeholder="00000-000" required></label>
          <label class="field"><span>CEP de destino</span><input name="dest_cep" inputmode="numeric" placeholder="00000-000" required></label>
        </div>
        <div class="grid c3">
          <label class="field"><span>Altura (cm)</span><input name="height_cm" type="number" step="0.1" min="0.1" value="20" required></label>
          <label class="field"><span>Largura (cm)</span><input name="width_cm" type="number" step="0.1" min="0.1" value="20" required></label>
          <label class="field"><span>Compr. (cm)</span><input name="length_cm" type="number" step="0.1" min="0.1" value="20" required></label>
        </div>
        <div class="grid c2">
          <label class="field"><span>Peso (kg)</span><input name="weight_kg" type="number" step="0.01" min="0.01" value="1" required></label>
          <label class="field"><span>Data de postagem</span><input name="posted_at" type="date" value="${today}" required></label>
        </div>
        <p class="small muted">Exemplos de destino: 01310-100 (São Paulo/SP) · 69005-000 (Manaus/AM) · 90010-000 (Porto Alegre/RS)</p>
        <button class="btn block" type="submit">Prever prazo</button>
      </form>
      <section class="panel" id="result">
        <h2>Resultado</h2>
        <div class="empty"><div class="big">🔮</div>Preencha os dados do envio e clique em <strong>Prever prazo</strong>.</div>
      </section>
    </div>`);

  const form = document.getElementById("f");
  bindSubmit(form, async () => {
    const d = formData(form);
    const r = await api("/api/predict/transit", { method: "POST", body: { ...d, posted_at: new Date(`${d.posted_at}T12:00:00`).toISOString() } });
    const diff = r.route_avg_days - r.expected_days;
    const posted = new Date(`${d.posted_at}T12:00:00`);
    const until = (days) => new Date(posted.getTime() + Math.ceil(days) * 86400000).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" });
    document.getElementById("result").innerHTML = `
      <h2>Resultado</h2>
      <div class="pred-route"><strong>${esc(r.origin.state)}</strong> <span class="muted">(${esc(r.origin.region)})</span> ➔ <strong>${esc(r.destination.state)}</strong> <span class="muted">(${esc(r.destination.region)})</span> · ${r.distance_km.toLocaleString("pt-BR")} km em linha reta</div>
      <div class="stats" style="margin:14px 0">
        <div class="stat in_progress"><div class="n">${fmtDays(r.expected_days)}</div><div class="l">Tempo esperado</div></div>
        <div class="stat closed"><div class="n">${fmtDays(r.safe_days)}</div><div class="l">Prazo seguro (até ${until(r.safe_days)})</div></div>
        <div class="stat"><div class="n">${fmtDays(r.route_avg_days)}</div><div class="l">Média histórica da rota</div></div>
      </div>
      <p><strong>Como ler:</strong> o pacote deve chegar em cerca de <strong>${fmtDays(r.expected_days)}</strong> após a postagem.
        Para prometer ao cliente, use o <strong>prazo seguro de ${Math.ceil(r.safe_days)} dias</strong>: em ~9 de cada 10 envios parecidos, a entrega chegou antes dele.</p>
      <p class="small muted">${Math.abs(diff) < 0.5 ? "A previsão está alinhada com a média histórica dessa rota." :
        `A previsão está ${fmtDays(Math.abs(diff))} ${diff > 0 ? "abaixo" : "acima"} da média histórica da rota (${esc(r.origin.state)}➔${esc(r.destination.state)}), porque considera também distância exata, peso, volume e época do ano.`}</p>
      <p class="small muted">Modelo: ${esc(r.model)} · erro médio no teste: ±${r.model_mae_days.toLocaleString("pt-BR")} dias. Previsões para o Norte e para rotas muito longas são menos precisas.</p>`;
  });
}

router();
