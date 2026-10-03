"use strict";
let token = "";
const el = id => document.getElementById(id);
async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(new URL(path, document.baseURI), {...options, headers});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) el("connection").hidden = false;
    throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
  }
  return result;
}
async function action(fn) {
  const buttons = [...document.querySelectorAll("button")];
  buttons.forEach(b => b.disabled = true);
  el("notice").textContent = "Working…";
  try { await fn(); el("notice").textContent = "Done."; }
  catch (e) { el("notice").textContent = e.message; }
  finally { buttons.forEach(b => b.disabled = false); }
}
function button(text, callback) {
  const b = document.createElement("button"); b.textContent = text; b.className = "secondary";
  b.onclick = () => action(callback); return b;
}
async function refresh() {
  const data = await api("people");
  el("status").textContent = "LOCAL · CONNECTED";
  el("connection").hidden = true;
  el("people").replaceChildren();
  if (!data.people.length) el("people").textContent = "No people enrolled yet.";
  for (const person of data.people) {
    const container = document.createElement("div"); container.className = "person";
    const row = document.createElement("div"); row.className = "row";
    const name = document.createElement("strong"); name.textContent = `${person.name} · ${person.samples} samples`;
    row.append(name, button("Delete person", async () => {
      if (confirm(`Delete every sample for ${person.name}?`)) {
        await api(`people/${encodeURIComponent(person.name)}`, {method:"DELETE"}); await refresh();
      }
    }));
    container.append(row);
    for (const sample of person.items) {
      const item = document.createElement("div"); item.className = "sample";
      const label = document.createElement("span"); label.textContent = `${sample.created_at} · ${sample.id.slice(0,8)}`;
      item.append(label, button("Delete sample", async () => {
        if (confirm("Delete this enrollment sample?")) {
          await api(`people/${encodeURIComponent(person.name)}/${sample.id}`, {method:"DELETE"}); await refresh();
        }
      })); container.append(item);
    }
    el("people").append(container);
  }
}
el("connect").onsubmit = e => {e.preventDefault(); token = el("token").value; el("token").value = ""; action(refresh);};
el("refresh").onclick = () => action(refresh);
el("enroll").onsubmit = e => {e.preventDefault(); action(async () => {
  const outcomes = [];
  for (const file of el("photos").files) {
    const form = new FormData(); form.append("file", file);
    try { await api(`enroll/${encodeURIComponent(el("name").value.trim())}`, {method:"POST", body:form}); outcomes.push(`${file.name}: enrolled`); }
    catch (error) { outcomes.push(`${file.name}: ${error.message}`); }
  }
  el("result").textContent = outcomes.join("\n"); await refresh();
});};
el("test").onsubmit = e => {e.preventDefault(); action(async () => {
  const form = new FormData(); form.append("file", el("testphoto").files[0]);
  el("result").textContent = JSON.stringify(await api("recognize", {method:"POST", body:form}), null, 2);
});};
action(refresh);
