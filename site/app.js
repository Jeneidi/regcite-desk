const DATA_ROOT = "data/";
const state = { cases: [], runs: [], regulations: [], reviewed: new Set() };

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;"}[char]));
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function simpleTokens(text) {
  return text.toLowerCase().match(/[a-z0-9]+/g) || [];
}

function rankParagraphs(complaint, regulations) {
  const query = new Set(simpleTokens(complaint));
  return regulations.flatMap((regulation) => regulation.paragraphs.map((paragraph) => {
    const overlap = simpleTokens(paragraph).filter((token) => query.has(token)).length;
    return { section: regulation.section, paragraph, score: overlap };
  })).sort((a, b) => b.score - a.score).slice(0, 3);
}

function renderCase(caseId) {
  const index = state.cases.findIndex((item) => item.id === caseId);
  const caseItem = state.cases[index] || state.cases[0];
  const run = state.runs.find((item) => item.id === caseItem.id);
  if (!caseItem || !run) return;
  const isRefusal = run.answer.section === "none";
  const reviewed = state.reviewed.has(caseItem.id);
  $("#case-meta").innerHTML = [caseItem.product, caseItem.issue, `Complaint ${caseItem.id}`].map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  $("#case-narrative").textContent = caseItem.narrative;
  $("#case-answer").textContent = isRefusal ? "No rule applies" : `12 CFR ${run.answer.section}`;
  $("#case-reason").textContent = run.answer.reason;
  const quote = $("#case-quote");
  quote.textContent = isRefusal ? "The AI found no rule that fits this complaint, so it did not quote one." : run.answer.quote;
  quote.className = `case-quote ${run.valid ? "is-pass" : "is-fail"}`;
  const badge = $("#review-badge");
  badge.textContent = reviewed ? "APPROVED" : (isRefusal ? "NO RULE APPLIES" : "QUOTE CHECKED");
  badge.className = `review-badge ${isRefusal ? "is-refusal" : ""}`;
  $("#review-button").textContent = reviewed ? "Approved" : "Approve";
  $("#review-button").disabled = reviewed;
  $("#retrieved-list").innerHTML = run.retrieved.map((item, rank) => `<div class="retrieved-row"><strong>${rank + 1}. 12 CFR ${escapeHtml(item.section)}</strong><span>match score ${item.score.toFixed(2)}</span></div>`).join("");
  $("#case-source").href = caseItem.source_url;
  $("#case-source").textContent = "public complaint archive";
}

function addCaseOptions() {
  const select = $("#case-select");
  select.innerHTML = state.cases.map((item, index) => `<option value="${escapeHtml(item.id)}">${String(index + 1).padStart(2, "0")} · ${escapeHtml(item.product)} · ${escapeHtml(item.issue)}</option>`).join("");
  select.addEventListener("change", () => renderCase(select.value));
}

function setLiveStatus(message, kind = "") {
  const status = $("#live-status");
  status.textContent = message;
  status.className = `live-status ${kind ? `is-${kind}` : ""}`;
}

function getStoredKey(provider) {
  return sessionStorage.getItem(`regcite-${provider}-key`) || "";
}

async function callProvider(provider, key, complaint, retrieved) {
  const context = retrieved.map((item) => `SECTION ${item.section}\n${item.paragraph}`).join("\n\n");
  const instruction = `Return only JSON with exactly section, quote, reason. section must be 1005.11, 1026.13, or none. Copy quote exactly from the provided eCFR text or use an empty quote for none. Complaint: ${complaint}\n\nECRF TEXT:\n${context}`;
  if (provider === "anthropic") {
    const response = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" }, body: JSON.stringify({ model: "claude-3-5-haiku-latest", max_tokens: 500, messages: [{ role: "user", content: instruction }] }) });
    if (!response.ok) throw new Error(`Anthropic returned error ${response.status}. Check your key and the AI company you picked.`);
    const payload = await response.json();
    return JSON.parse(payload.content?.[0]?.text || "{}");
  }
  const response = await fetch("https://api.openai.com/v1/chat/completions", { method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${key}` }, body: JSON.stringify({ model: "gpt-4o-mini", temperature: 0, response_format: { type: "json_object" }, messages: [{ role: "user", content: instruction }] }) });
  if (!response.ok) throw new Error(`OpenAI returned error ${response.status}. Check your key and the AI company you picked.`);
  const payload = await response.json();
  return JSON.parse(payload.choices?.[0]?.message?.content || "{}");
}

function verifyQuote(answer, regulations) {
  if (answer.section === "none") return answer.quote === "";
  const regulation = regulations.find((item) => item.section === answer.section);
  return Boolean(regulation && answer.quote && regulation.paragraphs.join(" ").includes(answer.quote));
}

async function runLive() {
  const provider = $("#provider").value;
  const key = $("#api-key").value.trim();
  const complaint = $("#live-input").value.trim();
  if (!key) return setLiveStatus("Paste your AI account key first, then try again.", "error");
  if (!complaint) return setLiveStatus("Type a complaint first.", "error");
  sessionStorage.setItem(`regcite-${provider}-key`, key);
  setLiveStatus("Looking up the two rules and asking the AI…");
  const retrieved = rankParagraphs(complaint, state.regulations);
  const started = performance.now();
  try {
    const answer = await callProvider(provider, key, complaint, retrieved);
    const valid = verifyQuote(answer, state.regulations);
    const latency = Math.round(performance.now() - started);
    const section = answer.section === "none" ? "No rule applies" : `12 CFR ${answer.section}`;
    setLiveStatus(`${section}. Quote check ${valid ? "passed" : "failed (the quote is not in the rule)"}. Answered in ${formatNumber(latency)} milliseconds. A person should review this before acting.`, valid ? "success" : "error");
    $("#live-output").innerHTML = `<strong>${escapeHtml(section)}</strong><p>${escapeHtml(answer.quote || "The AI said no rule applies.")}</p><small>${escapeHtml(answer.reason || "No reason given.")}</small>`;
  } catch (error) {
    setLiveStatus(error.message, "error");
  }
}

async function boot() {
  try {
    const [cases, runs, regulations] = await Promise.all([fetch(`${DATA_ROOT}recorded_cases.json`).then((response) => response.json()), fetch(`${DATA_ROOT}recorded_runs.json`).then((response) => response.json()), fetch(`${DATA_ROOT}regulations.json`).then((response) => response.json())]);
    state.cases = cases;
    state.runs = runs;
    state.regulations = regulations;
    addCaseOptions();
    renderCase(cases[0].id);
    $("#review-button").addEventListener("click", () => { state.reviewed.add($("#case-select").value); renderCase($("#case-select").value); kitToast("Marked as approved by a person"); });
    $("#run-live").addEventListener("click", runLive);
    $("#clear-key").addEventListener("click", () => { sessionStorage.removeItem(`regcite-${$("#provider").value}-key`); $("#api-key").value = ""; setLiveStatus("Your key was removed from this tab.", "success"); });
    $("#provider").addEventListener("change", () => { $("#api-key").value = getStoredKey($("#provider").value); });
  } catch (error) {
    setLiveStatus(`The saved examples could not load: ${error.message}`, "error");
  }
}

boot();
