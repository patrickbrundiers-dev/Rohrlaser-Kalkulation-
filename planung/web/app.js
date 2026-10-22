"use strict";
// Browser-Oberfläche der Maschinenplanung: Dashboard, Plantafel, Aufträge, Maschinen & Kalender, Benutzer.
// Jede Planänderung ist zuerst ein Entwurf: der Server rechnet die Vorschau, gespeichert wird erst nach Bestätigung.

const S = { benutzer: null, seite: "dashboard", ansicht: "woche", von: null, daten: null, auftraege: [] };
const STUFE = { lesen: 0, planen: 1, verwalten: 2 };
const WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const RASTER_MIN = 15;

// ------------------------------------------------------------------ Hilfen
const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const darf = (rolle) => S.benutzer && STUFE[S.benutzer.rolle] >= STUFE[rolle];
const pad = (n) => String(n).padStart(2, "0");

function zeit(t) {            // 'JJJJ-MM-TTTHH:MM' als Ortszeit
  if (!t) return null;
  const [d, u = "00:00"] = t.split("T");
  const [y, m, dd] = d.split("-").map(Number);
  const [h, mi] = u.split(":").map(Number);
  return new Date(y, m - 1, dd, h, mi);
}
const zeitText = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const tagText = (d) => `${WT[(d.getDay() + 6) % 7]} ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`;
const anzeigeZeit = (t) => { const d = zeit(t); return d ? `${tagText(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}` : "–"; };
const anzeigeDatum = (t) => { if (!t) return "–"; const [y, m, d] = t.split("-"); return `${d}.${m}.${y}`; };
const stunden = (min) => (min == null ? "–" : `${(min / 60).toLocaleString("de-DE", { maximumFractionDigits: 1 })} h`);
const prozent = (p) => (p == null ? "–" : `${p.toLocaleString("de-DE", { maximumFractionDigits: 0 })} %`);
const zahl = (v) => (v == null ? "" : String(v).replace(".", ","));

async function api(methode, pfad, daten) {
  const opt = { method: methode, headers: { "X-Planung": "1" } };
  if (daten !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(daten); }
  const r = await fetch("/api/" + pfad, opt);
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 && pfad !== "anmelden") { S.benutzer = null; zeigeAnmeldung(); }
  if (!r.ok) { const e = new Error(j.fehler || `Fehler ${r.status}`); e.status = r.status; e.daten = j; throw e; }
  return j;
}

function hinweis(text, fehler = false) {      // fehler: true = rot, "gut" = grün, sonst Hinweis
  const el = $("#hinweis");
  if (!text) { el.hidden = true; return; }
  el.textContent = text; el.className = "hinweis" + (fehler === "gut" ? " gut" : fehler ? " fehler" : ""); el.hidden = false;
  clearTimeout(hinweis.t); hinweis.t = setTimeout(() => (el.hidden = true), 8000);
}

function dialog(html, beiAbsenden) {
  const d = $("#dialog"), f = $("#dialog-form");
  f.innerHTML = html;
  f.onsubmit = async (ev) => {
    const knopf = ev.submitter?.value;
    if (knopf === "abbrechen" || !beiAbsenden) return;
    ev.preventDefault();
    try { if ((await beiAbsenden(knopf, new FormData(f))) !== false) d.close(); }
    catch (e) { meldung(f, e); }
  };
  if (d.open) d.close();
  d.showModal();
  return f;
}
function meldung(f, e) {
  let el = $(".dialog-fehler", f);
  if (!el) { el = document.createElement("div"); el.className = "hinweis fehler dialog-fehler"; f.prepend(el); }
  el.textContent = e.message + (e.status === 409 ? " Der aktuelle Stand wird neu geladen." : "");
  if (e.status === 409) laden();
}

// ------------------------------------------------------------------ Anmeldung, Navigation, Live
async function start() {
  const s = await api("GET", "status");
  S.benutzer = s.benutzer;
  if (!s.eingerichtet) return zeigeEinrichten();
  if (!S.benutzer) return zeigeAnmeldung();
  angemeldet();
}

function zeigeEinrichten() {
  $("#kopf").hidden = true;
  $("#inhalt").innerHTML = `<form class="anmeldung" id="f"><h1>Maschinenplanung einrichten</h1>
    <p class="klein">Der erste Benutzer bekommt die Rolle „verwalten“ und legt danach die anderen an.</p>
    <label>Name<input name="name" required autocomplete="username"></label>
    <label>Anzeigename<input name="anzeige"></label>
    <label>Passwort (mindestens 8 Zeichen)<input name="passwort" type="password" minlength="8" required autocomplete="new-password"></label>
    <button>Einrichten</button></form>`;
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try { S.benutzer = (await api("POST", "einrichten", Object.fromEntries(new FormData(ev.target)))).benutzer; angemeldet(); }
    catch (e) { hinweis(e.message, true); }
  };
}

function zeigeAnmeldung() {
  $("#kopf").hidden = true;
  $("#inhalt").innerHTML = `<form class="anmeldung" id="f"><h1>Maschinenplanung</h1>
    <label>Name<input name="name" required autofocus autocomplete="username"></label>
    <label>Passwort<input name="passwort" type="password" required autocomplete="current-password"></label>
    <button>Anmelden</button></form>`;
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try { S.benutzer = (await api("POST", "anmelden", Object.fromEntries(new FormData(ev.target)))).benutzer; angemeldet(); }
    catch (e) { hinweis(e.message, true); }
  };
}

function angemeldet() {
  $("#kopf").hidden = false;
  $("#wer").textContent = `${S.benutzer.anzeige} (${S.benutzer.rolle})`;
  document.querySelectorAll("[data-rolle]").forEach((a) => (a.hidden = !darf(a.dataset.rolle)));
  live();
  navigieren();
}

$("#abmelden").onclick = async () => { await api("POST", "abmelden"); location.hash = ""; location.reload(); };
$("#passwort").onclick = () => dialog(`<h2>Passwort ändern</h2>
  <label>Bisheriges Passwort<input name="alt" type="password" required></label>
  <label>Neues Passwort (mindestens 8 Zeichen)<input name="neu" type="password" minlength="8" required></label>
  <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Speichern</button></div>`,
  async (k, fd) => { await api("PUT", "passwort", Object.fromEntries(fd)); hinweis("Passwort geändert", "gut"); });

window.addEventListener("hashchange", navigieren);
function navigieren() {
  S.seite = location.hash.slice(1) || "dashboard";
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("aktiv", a.dataset.seite === S.seite));
  laden();
}

let quelle = null;
function live() {
  if (quelle) quelle.close();
  quelle = new EventSource("/api/ereignisse");
  quelle.onopen = () => $("#live").classList.add("an");
  quelle.onerror = () => $("#live").classList.remove("an");
  quelle.addEventListener("aenderung", (ev) => {
    const d = JSON.parse(ev.data);
    if (d.benutzer !== S.benutzer?.anzeige) hinweis(`${d.benutzer} hat ${d.was === "Plan" ? "den Plan" : d.was} geändert – Ansicht aktualisiert.`);
    if (!$("#dialog").open) laden();
  });
}

async function laden() {
  if (!S.benutzer) return;
  try {
    if (S.seite === "dashboard") return await dashboard();
    if (S.seite === "plantafel") return await plantafel();
    if (S.seite === "auftraege") return await auftraegeSeite();
    if (S.seite === "kalender") return await kalenderSeite();
    if (S.seite === "benutzer") return await benutzerSeite();
  } catch (e) { if (e.status !== 401) hinweis(e.message, true); }
}

// ------------------------------------------------------------------ Dashboard
async function dashboard() {
  const d = await api("GET", "dashboard");
  const karten = d.maschinen.map((m) => {
    const wochen = m.wochen.map((w) => `<span>${esc(w.name)}</span>
      <div class="balken ${w.auslastung > 100 ? "ueber" : ""}"><div style="width:${Math.min(100, w.auslastung || 0)}%"></div></div>
      <span class="zahl">${prozent(w.auslastung)}</span><span class="zahl klein">${stunden(w.frei_min)} frei</span>`).join("");
    return `<div class="karte"><h2>${esc(m.id)} <span class="klein">${esc(m.bezeichnung || "")} · ${esc(m.status)}</span></h2>
      ${m.ohne_schicht ? `<p class="offen">Kein Schichtmodell hinterlegt – Auslastung kann nicht gerechnet werden.</p>` : ""}
      <div class="gross">${prozent(m.heute.auslastung)}</div>
      <div class="klein">geplante Auslastung heute · ${stunden(m.heute.geplant_min)} von ${stunden(m.heute.verfuegbar_min)}</div>
      <div class="wochen" style="margin-top:10px">${wochen}</div></div>`;
  }).join("");
  const kritisch = d.kritisch.map((b) => `<tr><td>${esc(b.auftragsnummer)}</td><td>${esc(b.kunde || "")}</td><td>${esc(b.maschine)}</td>
    <td>${anzeigeZeit(b.ende)}</td><td>${anzeigeDatum(b.liefertermin)}</td><td><span class="badge ${esc(b.risiko)}">${esc(b.risiko)}</span></td></tr>`).join("");
  const ungeplant = d.ungeplant.map((a) => `<tr><td>${esc(a.auftragsnummer)}</td><td>${esc(a.kunde || "")}</td>
    <td>${anzeigeDatum(a.liefertermin)}</td><td class="zahl">${stunden((a.maschinenzeit_min || 0) + (a.ruestzeit_min || 0))}</td></tr>`).join("");
  const still = d.stillstaende.map((s) => `<tr><td>${esc(s.maschine)}</td><td>${anzeigeZeit(s.beginn)}</td><td>${anzeigeZeit(s.ende)}</td><td>${esc(s.art || "")}</td></tr>`).join("");
  const warn = d.warnungen.map((b) => `<tr><td>${esc(b.auftragsnummer)}</td><td>${esc(b.maschine)}</td><td>${b.warnungen.map(esc).join("<br>")}</td></tr>`).join("");
  $("#inhalt").innerHTML = `<h1>Dashboard</h1><div class="karten">${karten}</div>
    <div class="karten">
      <div class="karte"><h2>Kritische Liefertermine</h2>${kritisch ? `<table><tr><th>Auftrag</th><th>Kunde</th><th>Maschine</th><th>Geplantes Ende</th><th>Liefertermin</th><th>Risiko</th></tr>${kritisch}</table>` : `<p class="klein">Keine.</p>`}
        <p class="klein">Kritisch = weniger als ${d.schwelle} Arbeitstage Puffer bis zum Liefertermin (Einstellung).</p></div>
      <div class="karte"><h2>Ungeplante Aufträge</h2>${ungeplant ? `<table><tr><th>Auftrag</th><th>Kunde</th><th>Liefertermin</th><th class="zahl">Dauer</th></tr>${ungeplant}</table>` : `<p class="klein">Keine.</p>`}</div>
      <div class="karte"><h2>Nächste Stillstände und Wartungen</h2>${still ? `<table><tr><th>Maschine</th><th>Beginn</th><th>Ende</th><th>Art</th></tr>${still}</table>` : `<p class="klein">Keine.</p>`}</div>
      <div class="karte"><h2>Hinweise zur Planung</h2>${warn ? `<table><tr><th>Auftrag</th><th>Maschine</th><th>Hinweis</th></tr>${warn}</table>` : `<p class="klein">Keine.</p>`}</div>
    </div>
    <p class="klein">Alle Werte sind geplante Auslastung (geplante Belegung ÷ verfügbare Schichtzeit), keine gemessene Produktivität.</p>`;
}

// ------------------------------------------------------------------ Plantafel
function zeitraum() {
  const heute = new Date(); heute.setHours(0, 0, 0, 0);
  let von = S.von ? new Date(S.von) : heute, bis;
  if (S.ansicht === "tag") { bis = new Date(von); bis.setDate(bis.getDate() + 1); }
  else if (S.ansicht === "woche") { von.setDate(von.getDate() - ((von.getDay() + 6) % 7)); bis = new Date(von); bis.setDate(bis.getDate() + 7); }
  else { von.setDate(1); bis = new Date(von); bis.setMonth(bis.getMonth() + 1); }
  S.von = von;
  return [von, bis];
}
function blaettern(richtung) {
  const v = new Date(S.von);
  if (S.ansicht === "tag") v.setDate(v.getDate() + richtung);
  else if (S.ansicht === "woche") v.setDate(v.getDate() + 7 * richtung);
  else v.setMonth(v.getMonth() + richtung);
  S.von = v; plantafel();
}

async function plantafel() {
  const [von, bis] = zeitraum();
  const [p, auftraege] = await Promise.all([api("GET", `plan?von=${zeitText(von)}&bis=${zeitText(bis)}`), api("GET", "auftraege")]);
  S.daten = p; S.auftraege = auftraege;
  const spanne = bis - von;
  const x = (t) => ((zeit(t) - von) / spanne) * 100;
  const breite = (a, b) => Math.max(0.15, x(b) - x(a));
  // Achse
  let striche = "";
  const t = new Date(von);
  while (t < bis) {
    const pos = ((t - von) / spanne) * 100;
    const text = S.ansicht === "tag" ? `${pad(t.getHours())}:00` : S.ansicht === "woche" ? tagText(t) : String(t.getDate());
    striche += `<div class="strich" style="left:${pos}%">${text}</div>`;
    if (S.ansicht === "tag") t.setHours(t.getHours() + 2); else t.setDate(t.getDate() + 1);
  }
  const jetzt = new Date();
  const jetztLinie = jetzt > von && jetzt < bis ? `<div class="jetzt" style="left:${((jetzt - von) / spanne) * 100}%" title="jetzt"></div>` : "";
  const zeilen = p.maschinen.map((m) => {
    const fenster = m.fenster.map(([a, b]) => `<div class="fenster" style="left:${x(a)}%;width:${breite(a, b)}%"></div>`).join("");
    const still = p.stillstaende.filter((s) => s.maschine === m.id).map((s) =>
      `<div class="stillstand" style="left:${Math.max(0, x(s.beginn))}%;width:${breite(s.beginn < p.von ? p.von : s.beginn, s.ende > p.bis ? p.bis : s.ende)}%" title="${esc(s.art || "Stillstand")}: ${anzeigeZeit(s.beginn)} – ${anzeigeZeit(s.ende)}"></div>`).join("");
    const belege = p.belegungen.filter((b) => b.maschine === m.id).map((b) => {
      const ende = b.ende || p.bis;
      const a = b.beginn_eff < p.von ? p.von : b.beginn_eff, e = ende > p.bis ? p.bis : ende;
      const titel = `${b.auftragsnummer} ${b.kunde || ""}\n${anzeigeZeit(b.beginn_eff)} – ${anzeigeZeit(b.ende)}\nDauer ${stunden(b.dauer)} (${b.dauer_quelle})\nLiefertermin ${anzeigeDatum(b.liefertermin)} · ${b.risiko}${b.puffer_tage != null ? ` (${b.puffer_tage} AT Puffer)` : ""}${b.fixiert ? "\nfixiert" : ""}${b.warnungen.length ? "\n! " + b.warnungen.join("\n! ") : ""}\nzuletzt geändert: ${b.geaendert_von || "–"}, ${b.geaendert_am || ""}`;
      return `<div class="beleg ${esc(b.risiko)} ${b.fixiert ? "fix" : ""} ${b.warnungen.length ? "warnung" : ""}" draggable="${darf("planen")}"
        data-id="${b.id}" style="left:${x(a)}%;width:${breite(a, e)}%" title="${esc(titel)}">
        <div><strong>${esc(b.auftragsnummer)}</strong> ${esc(b.bezeichnung || b.kunde || "")}</div>
        <div class="z2">${stunden(b.dauer)} · LT ${anzeigeDatum(b.liefertermin)}</div></div>`;
    }).join("");
    const k = m.kennzahlen;
    return `<div class="zeile"><div class="name"><strong>${esc(m.id)}</strong> <span class="klein">${esc(m.status)}</span>
        <div class="gross" style="font-size:20px">${prozent(k.auslastung)}</div>
        <div class="klein">${stunden(k.geplant_min)} / ${stunden(k.verfuegbar_min)}<br>frei ${stunden(k.frei_min)}</div>
        ${m.ohne_schicht ? `<div class="offen klein">kein Schichtmodell</div>` : ""}</div>
      <div class="spur" data-maschine="${esc(m.id)}">${fenster}${still}${jetztLinie}${belege}</div></div>`;
  }).join("");
  const vorrat = auftraege.filter((a) => a.belegung_id == null && (a.status === "offen" || a.status === "in Arbeit"))
    .sort((a, b) => (a.prioritaet ?? 99) - (b.prioritaet ?? 99) || (a.liefertermin || "9999").localeCompare(b.liefertermin || "9999"))
    .map((a) => `<div class="auftrag" draggable="${darf("planen")}" data-auftrag="${a.id}">
      <strong>${esc(a.auftragsnummer)}</strong> ${a.prioritaet != null ? `<span class="badge">P${esc(a.prioritaet)}</span>` : ""}<br>
      <span class="klein">${esc(a.kunde || "")} · ${stunden((a.maschinenzeit_min || 0) + (a.ruestzeit_min || 0))} · LT ${anzeigeDatum(a.liefertermin)}
      ${a.maschinen_erlaubt ? ` · nur ${esc(a.maschinen_erlaubt)}` : ""}</span></div>`).join("");
  const titel = S.ansicht === "tag" ? tagText(von) : S.ansicht === "woche" ? `KW ${kw(von)} · ${tagText(von)} – ${tagText(new Date(bis - 1))}` : `${pad(von.getMonth() + 1)}/${von.getFullYear()}`;
  $("#inhalt").innerHTML = `<div class="leiste"><h1 style="margin:0">Plantafel</h1>
      <button class="leise" id="zurueck">◀</button><strong>${titel}</strong><button class="leise" id="vor">▶</button>
      <button class="leise" id="heute">Heute</button>
      <select id="ansicht"><option value="tag">Tag</option><option value="woche">Woche</option><option value="monat">Monat</option></select>
      <label class="rechts">Auftrag suchen<input id="suche" placeholder="Auftragsnummer"></label></div>
    <div class="tafel-rahmen"><div><div class="tafel"><div class="zeile"><div class="name klein">Maschine</div><div class="achse">${striche}</div></div>${zeilen}</div>
      <div class="legende"><span><i style="background:var(--belegt)"></i>geplant</span><span><i style="background:#fff"></i>frei (Schicht)</span>
        <span><i style="background:var(--aus)"></i>keine Schicht</span><span><i style="background:var(--still)"></i>Stillstand/Wartung</span>
        <span><i style="border:2px solid var(--risiko)"></i>Terminrisiko</span><span><i style="border:2px solid var(--konflikt)"></i>Termin überschritten</span>
        <span>! = Hinweis (Maus darüber)</span></div></div>
      <div class="vorrat"><h2>Ungeplante Aufträge</h2>${vorrat || `<p class="klein">Keine.</p>`}
        ${darf("planen") ? `<p class="klein">Auf eine Maschine ziehen. Nichts wird gespeichert, bevor die Vorschau bestätigt ist.</p>` : ""}</div></div>`;
  $("#ansicht").value = S.ansicht;
  $("#ansicht").onchange = (e) => { S.ansicht = e.target.value; plantafel(); };
  $("#zurueck").onclick = () => blaettern(-1);
  $("#vor").onclick = () => blaettern(1);
  $("#heute").onclick = () => { S.von = null; plantafel(); };
  $("#suche").onchange = (e) => suchen(e.target.value.trim());
  ziehenEinrichten(von, spanne);
}

function kw(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  return pad(Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7));
}

async function suchen(nr) {
  if (!nr) return;
  const a = S.auftraege.find((x) => x.auftragsnummer.toLowerCase() === nr.toLowerCase())
    || S.auftraege.find((x) => x.auftragsnummer.toLowerCase().includes(nr.toLowerCase()));
  if (!a) return hinweis(`Auftrag ${nr} nicht gefunden`, true);
  if (a.belegung_id == null) return hinweis(`Auftrag ${a.auftragsnummer} ist noch nicht eingeplant`);
  const alle = await api("GET", `plan?von=2000-01-01T00:00&bis=2100-01-01T00:00`);
  const b = alle.belegungen.find((x) => x.id === a.belegung_id);
  if (b) { S.von = zeit(b.beginn_eff); await plantafel(); document.querySelector(`.beleg[data-id="${b.id}"]`)?.scrollIntoView({ block: "center" }); }
}

function ziehenEinrichten(von, spanne) {
  document.querySelectorAll(".beleg").forEach((el) => {
    el.addEventListener("dragstart", (ev) => {
      ev.dataTransfer.setData("text/plain", JSON.stringify({ id: Number(el.dataset.id), versatz: ev.offsetX }));
    });
    el.addEventListener("click", () => belegungBearbeiten(S.daten.belegungen.find((b) => b.id === Number(el.dataset.id))));
  });
  document.querySelectorAll(".vorrat .auftrag").forEach((el) => el.addEventListener("dragstart", (ev) =>
    ev.dataTransfer.setData("text/plain", JSON.stringify({ auftrag_id: Number(el.dataset.auftrag), versatz: 0 }))));
  document.querySelectorAll(".spur").forEach((spur) => {
    spur.addEventListener("dragover", (ev) => { if (darf("planen")) { ev.preventDefault(); spur.classList.add("ziel"); } });
    spur.addEventListener("dragleave", () => spur.classList.remove("ziel"));
    spur.addEventListener("drop", (ev) => {
      ev.preventDefault(); spur.classList.remove("ziel");
      const d = JSON.parse(ev.dataTransfer.getData("text/plain") || "{}");
      const r = spur.getBoundingClientRect();
      let t = new Date(von.getTime() + ((ev.clientX - r.left - (d.versatz || 0)) / r.width) * spanne);
      t = new Date(Math.round(t / (RASTER_MIN * 60000)) * RASTER_MIN * 60000);
      const aenderung = { maschine: spur.dataset.maschine, beginn: zeitText(t) };
      if (d.id) aenderung.id = d.id; else aenderung.auftrag_id = d.auftrag_id;
      vorschauDialog(aenderung, "Planänderung prüfen");
    });
  });
}

function belegungBearbeiten(b) {
  if (!b) return;
  const lesen = !darf("planen");
  dialog(`<h2>Auftrag ${esc(b.auftragsnummer)} <span class="klein">${esc(b.kunde || "")}</span></h2>
    <p class="klein">Geplant ${anzeigeZeit(b.beginn_eff)} – ${anzeigeZeit(b.ende)} auf ${esc(b.maschine)} · Dauer ${stunden(b.dauer)} (${esc(b.dauer_quelle)})
      · Liefertermin ${anzeigeDatum(b.liefertermin)} · <span class="badge ${esc(b.risiko)}">${esc(b.risiko)}</span>
      · zuletzt geändert von ${esc(b.geaendert_von || "–")} am ${esc(b.geaendert_am || "")}</p>
    ${b.warnungen.length ? `<ul class="meldungen">${b.warnungen.map((w) => `<li class="warnung">${esc(w)}</li>`).join("")}</ul>` : ""}
    <div class="raster">
      <label>Maschine<select name="maschine" ${lesen ? "disabled" : ""}>${S.daten.maschinen.map((m) => `<option ${m.id === b.maschine ? "selected" : ""}>${esc(m.id)}</option>`).join("")}</select></label>
      <label>Geplanter Beginn<input type="datetime-local" name="beginn" value="${esc(b.beginn)}" step="${RASTER_MIN * 60}" ${lesen ? "disabled" : ""}></label>
      <label>Dauer in Minuten (leer = aus dem Auftrag: ${zahl((b.maschinenzeit_min || 0) + (b.ruestzeit_min || 0))})<input name="dauer_min" value="${zahl(b.dauer_min)}" ${lesen ? "disabled" : ""}></label>
      <label>Fixiert (Vorschläge und Nachrücken bewegen sie nicht)<select name="fixiert" ${lesen ? "disabled" : ""}><option value="">nein</option><option value="1" ${b.fixiert ? "selected" : ""}>ja</option></select></label>
      <label>Tatsächlicher Beginn<input type="datetime-local" name="ist_beginn" value="${esc(b.ist_beginn || "")}" ${lesen ? "disabled" : ""}></label>
      <label>Tatsächliches Ende<input type="datetime-local" name="ist_ende" value="${esc(b.ist_ende || "")}" ${lesen ? "disabled" : ""}></label>
    </div>
    <div class="knoepfe"><button value="historie" class="leise links" formnovalidate>Verlauf</button>
      ${lesen ? "" : `<button value="entfernen" class="leise" formnovalidate>Ausplanen</button>`}
      <button value="abbrechen" class="leise" formnovalidate>Schließen</button>${lesen ? "" : `<button value="pruefen">Prüfen</button>`}</div>`,
    async (knopf, fd) => {
      if (knopf === "historie") { verlauf("belegung", b.id, `Verlauf ${b.auftragsnummer}`); return false; }
      const a = { id: b.id, maschine: fd.get("maschine"), beginn: fd.get("beginn") };
      if (knopf === "entfernen") { a.entfernen = true; a.maschine = b.maschine; a.beginn = b.beginn; }
      else {
        a.dauer_min = fd.get("dauer_min").replace(",", ".");
        a.fixiert = fd.get("fixiert") === "1";
        a.ist_beginn = fd.get("ist_beginn"); a.ist_ende = fd.get("ist_ende");
      }
      $("#dialog").close();
      vorschauDialog(a, knopf === "entfernen" ? "Ausplanen prüfen" : "Änderung prüfen");
      return false;
    });
}

async function vorschauDialog(aenderung, titel) {
  let v;
  try { v = await api("POST", "plan/vorschau", aenderung); } catch (e) { return hinweis(e.message, true); }
  const liste = v.belegungen.map((b) => `<tr><td>${esc(b.auftragsnummer)}</td><td>${esc(b.maschine)}</td><td>${anzeigeZeit(b.beginn_eff)}</td>
    <td>${anzeigeZeit(b.ende)}</td><td>${anzeigeDatum(b.liefertermin)}</td><td><span class="badge ${esc(b.risiko)}">${esc(b.risiko)}</span></td></tr>`).join("");
  const meld = [...v.fehler.map((f) => `<li class="fehler">${esc(f)}</li>`), ...v.warnungen.map((w) => `<li class="warnung">${esc(w)}</li>`)].join("");
  const nachrueckbar = !aenderung.entfernen;
  dialog(`<h2>${esc(titel)}</h2>
    ${aenderung.entfernen ? `<p>Die Belegung wird aus dem Plan genommen; der Auftrag bleibt erhalten und steht wieder bei den ungeplanten.</p>` :
      `<table><tr><th>Auftrag</th><th>Maschine</th><th>Beginn</th><th>Ende</th><th>Liefertermin</th><th>Risiko</th></tr>${liste}</table>`}
    ${meld ? `<ul class="meldungen">${meld}</ul>` : `<p class="klein">Keine Konflikte.</p>`}
    ${nachrueckbar ? `<label class="haken"><input type="checkbox" name="nachruecken" ${aenderung.nachruecken ? "checked" : ""}>
      Nachfolgende, nicht fixierte Aufträge auf ${esc(aenderung.maschine)} nach hinten schieben, wenn sie sich überschneiden</label>` : ""}
    <label>Grund (für den Verlauf, optional)<input name="grund" maxlength="200"></label>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Verwerfen</button>
      <button value="speichern" ${v.fehler.length ? "disabled" : ""}>Speichern</button></div>`,
    async (knopf, fd) => {
      if (knopf !== "speichern") return;
      await api("POST", "plan/speichern", { aenderung, maschinen_versionen: v.maschinen_versionen, grund: fd.get("grund") });
      hinweis("Gespeichert", "gut");
      laden();
    });
  const box = $('#dialog-form input[name="nachruecken"]');
  if (box) box.onchange = () => { $("#dialog").close(); vorschauDialog({ ...aenderung, nachruecken: box.checked }, titel); };
}

async function verlauf(objekt, id, titel) {
  const h = await api("GET", `historie?objekt=${objekt}&id=${id}`);
  const fmt = (o) => (o ? Object.entries(o).filter(([, v]) => v != null).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join("<br>") : "");
  dialog(`<h2>${esc(titel)}</h2><table><tr><th>Wann</th><th>Wer</th><th>Was</th><th>Vorher</th><th>Nachher</th><th>Grund</th></tr>
    ${h.map((e) => `<tr><td>${esc(e.zeit.replace("T", " "))}</td><td>${esc(e.benutzer)}</td><td>${esc(e.aktion)}</td><td class="klein">${fmt(e.alt)}</td><td class="klein">${fmt(e.neu)}</td><td>${esc(e.grund || "")}</td></tr>`).join("")}</table>
    <div class="knoepfe"><button value="abbrechen">Schließen</button></div>`);
}

// ------------------------------------------------------------------ Aufträge
const AUFTRAG_FELDER = [["auftragsnummer", "Auftragsnummer", "text", true], ["angebot_nummer", "Angebotsnummer"], ["kunde", "Kunde"],
  ["bezeichnung", "Artikel / Bauteil"], ["profil", "Profil"], ["werkstoff", "Werkstoff"], ["stueck", "Stückzahl"],
  ["maschinenzeit_min", "Maschinenzeit (Schneiden) in min"], ["ruestzeit_min", "Rüstzeit in min"], ["liefertermin", "Liefertermin", "date"],
  ["prioritaet", "Priorität (1 = höchste)"], ["maschinen_erlaubt", "Nur auf Maschinen (z. B. T11, LT7; leer = keine Einschränkung bekannt)"]];

async function auftraegeSeite() {
  S.auftraege = await api("GET", "auftraege");
  const filter = S.filter || { text: "", status: "aktiv" };
  const zeilen = S.auftraege.filter((a) => (filter.status === "alle" || (filter.status === "aktiv" ? !["fertig", "storniert"].includes(a.status) : a.status === filter.status))
    && (!filter.text || `${a.auftragsnummer} ${a.kunde} ${a.bezeichnung}`.toLowerCase().includes(filter.text.toLowerCase())))
    .map((a) => `<tr class="klickbar" data-id="${a.id}"><td>${esc(a.auftragsnummer)}</td><td>${esc(a.kunde || "")}</td><td>${esc(a.bezeichnung || "")}</td>
      <td class="zahl">${zahl(a.stueck)}</td><td class="zahl">${stunden((a.maschinenzeit_min || 0) + (a.ruestzeit_min || 0))}</td><td>${esc(a.zeitquelle || "")}</td>
      <td>${anzeigeDatum(a.liefertermin)}</td><td>${a.prioritaet ?? ""}</td><td>${esc(a.status)}</td><td>${a.belegung_id ? "eingeplant" : "ungeplant"}</td></tr>`).join("");
  $("#inhalt").innerHTML = `<div class="leiste"><h1 style="margin:0">Aufträge</h1>
      <label>Suche<input id="text" value="${esc(filter.text)}" placeholder="Nummer, Kunde, Artikel"></label>
      <label>Status<select id="status"><option value="aktiv">offen + in Arbeit</option><option>offen</option><option>in Arbeit</option><option>fertig</option><option>storniert</option><option value="alle">alle</option></select></label>
      ${darf("planen") ? `<button class="rechts" id="neu">Neuer Auftrag</button>` : ""}</div>
    <table><tr><th>Auftrag</th><th>Kunde</th><th>Artikel</th><th class="zahl">Stück</th><th class="zahl">Dauer</th><th>Zeitquelle</th><th>Liefertermin</th><th>Prio</th><th>Status</th><th>Plan</th></tr>${zeilen}</table>
    <p class="klein">Dauer = Maschinenzeit + Rüstzeit. Zeiten aus der Rohrlaser-Kalkulation kommen später per „An Planung übergeben“; bis dahin von Hand.</p>`;
  $("#status").value = filter.status;
  $("#text").oninput = (e) => { S.filter = { ...filter, text: e.target.value }; clearTimeout(S.tt); S.tt = setTimeout(auftraegeSeite, 300); };
  $("#status").onchange = (e) => { S.filter = { ...filter, status: e.target.value }; auftraegeSeite(); };
  if ($("#neu")) $("#neu").onclick = () => auftragDialog(null);
  document.querySelectorAll("tr.klickbar").forEach((tr) => (tr.onclick = () => auftragDialog(S.auftraege.find((a) => a.id === Number(tr.dataset.id)))));
}

function auftragDialog(a) {
  const lesen = !darf("planen");
  const felder = AUFTRAG_FELDER.map(([n, t, typ = "text", pflicht]) => `<label>${esc(t)}<input name="${n}" type="${typ}" value="${esc(typeof a?.[n] === "number" ? zahl(a[n]) : a?.[n] ?? "")}" ${pflicht ? "required" : ""} ${lesen ? "disabled" : ""}></label>`).join("");
  dialog(`<h2>${a ? `Auftrag ${esc(a.auftragsnummer)}` : "Neuer Auftrag"}</h2>
    ${a ? `<p class="klein">Angelegt von ${esc(a.angelegt_von || "–")} am ${esc(a.angelegt_am || "")} · zuletzt geändert von ${esc(a.geaendert_von || "–")} am ${esc(a.geaendert_am || "")}</p>` : ""}
    <div class="raster">${felder}
      <label>Status<select name="status" ${lesen ? "disabled" : ""}>${["offen", "in Arbeit", "fertig", "storniert"].map((s) => `<option ${a?.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></label></div>
    <label>Bemerkung<textarea name="bemerkung" rows="2" ${lesen ? "disabled" : ""}>${esc(a?.bemerkung || "")}</textarea></label>
    <div class="knoepfe">${a ? `<button value="historie" class="leise links" formnovalidate>Verlauf</button>` : ""}
      ${a && !lesen ? `<button value="loeschen" class="leise" formnovalidate>Löschen</button>` : ""}
      <button value="abbrechen" class="leise" formnovalidate>Schließen</button>${lesen ? "" : `<button value="speichern">Speichern</button>`}</div>`,
    async (knopf, fd) => {
      if (knopf === "historie") { verlauf("auftrag", a.id, `Verlauf ${a.auftragsnummer}`); return false; }
      if (knopf === "loeschen") {
        if (!confirm(`Auftrag ${a.auftragsnummer} samt Einplanung löschen?`)) return false;
        await api("DELETE", `auftraege/${a.id}?version=${a.version}`); laden(); return;
      }
      const d = Object.fromEntries(fd);
      if (a) await api("PUT", `auftraege/${a.id}`, { daten: d, version: a.version });
      else await api("POST", "auftraege", d);
      hinweis("Gespeichert", "gut"); laden();
    });
}

// ------------------------------------------------------------------ Maschinen & Kalender
async function kalenderSeite() {
  const [k, e] = await Promise.all([api("GET", "kalender"), api("GET", "einstellungen")]);
  const verw = darf("verwalten"), plan = darf("planen");
  const karten = k.maschinen.map((m) => {
    const sch = k.schichten.filter((s) => s.maschine === m.id);
    const summe = sch.reduce((n, s) => { const [b, x] = [s.beginn, s.ende].map((u) => u.split(":").reduce((h, mi) => h * 60 + Number(mi))); return n + (x > b ? x - b : x + 1440 - b); }, 0);
    return `<div class="karte"><h2>${esc(m.id)} <span class="klein">${esc(m.bezeichnung || "")}</span></h2>
      <p>Status: <strong>${esc(m.status)}</strong>${m.bemerkung ? ` · ${esc(m.bemerkung)}` : ""}</p>
      ${sch.length ? `<table><tr><th>Tag</th><th>Beginn</th><th>Ende</th><th>gültig</th></tr>${sch.map((s) => `<tr><td>${WT[s.wochentag]}</td><td>${esc(s.beginn)}</td><td>${esc(s.ende)}</td><td class="klein">${s.gueltig_ab ? "ab " + anzeigeDatum(s.gueltig_ab) : ""} ${s.gueltig_bis ? "bis " + anzeigeDatum(s.gueltig_bis) : ""}</td></tr>`).join("")}</table>
        <p class="klein">${stunden(summe)} Schichtzeit je Woche (ohne Feiertage und Stillstände)</p>` : `<p class="offen">Kein Schichtmodell hinterlegt (offene Konfiguration).</p>`}
      ${verw ? `<div class="knoepfe"><button class="leise" data-maschine="${esc(m.id)}" data-aktion="stamm">Maschine bearbeiten</button><button data-maschine="${esc(m.id)}" data-aktion="schichten">Schichten bearbeiten</button></div>` : ""}</div>`;
  }).join("");
  const heuteText = zeitText(new Date()).slice(0, 10);
  const vergangen = k.ausnahmen.filter((a) => a.datum < heuteText).length;
  const aus = k.ausnahmen.filter((a) => a.datum >= heuteText).map((a) => `<tr><td>${anzeigeDatum(a.datum)}</td><td>${esc(a.maschine || "alle")}</td><td>${a.art === "frei" ? "frei" : `Zusatzschicht ${esc(a.beginn)}–${esc(a.ende)}`}</td><td>${esc(a.bezeichnung || "")}</td>
    <td>${verw ? `<button class="leise" data-ausnahme="${a.id}">Löschen</button>` : ""}</td></tr>`).join("");
  const still = k.stillstaende.map((s) => `<tr><td>${esc(s.maschine)}</td><td>${anzeigeZeit(s.beginn)}</td><td>${anzeigeZeit(s.ende)}</td><td>${esc(s.art || "")}${s.geplant ? "" : " (ungeplant)"}</td><td>${esc(s.bemerkung || "")}</td>
    <td>${plan ? `<button class="leise" data-stillstand="${s.id}">Löschen</button>` : ""}</td></tr>`).join("");
  $("#inhalt").innerHTML = `<h1>Maschinen &amp; Kalender</h1><div class="karten">${karten}</div>
    <div class="karten">
      <div class="karte"><h2>Feiertage, Betriebsruhe, Zusatzschichten</h2><table><tr><th>Datum</th><th>Maschine</th><th>Art</th><th>Bezeichnung</th><th></th></tr>${aus}</table>
        ${vergangen ? `<p class="klein">${vergangen} vergangene Einträge ausgeblendet (sie zählen weiter für vergangene Zeiträume).</p>` : ""}
        ${verw ? `<div class="knoepfe"><button class="leise" id="feiertage">Bundesweite Feiertage eintragen …</button><button id="ausnahme">Ausnahme anlegen</button></div>
        <p class="klein">Eingetragen werden nur die neun bundesweiten Feiertage; Feiertage des Bundeslands (z. B. Fronleichnam) bitte als Ausnahme ergänzen.</p>` : ""}</div>
      <div class="karte"><h2>Stillstände und Wartungen</h2><table><tr><th>Maschine</th><th>Beginn</th><th>Ende</th><th>Art</th><th>Bemerkung</th><th></th></tr>${still}</table>
        ${plan ? `<div class="knoepfe"><button id="stillstand">Stillstand anlegen</button></div>` : ""}</div>
      <div class="karte"><h2>Einstellungen</h2><p>Terminrisiko „kritisch“ bei weniger als <strong>${esc(e.termin_schwelle_tage)}</strong> Arbeitstagen Puffer.</p>
        ${verw ? `<div class="knoepfe"><button class="leise" id="schwelle">Ändern</button>${`<button class="leise" id="sicherung">Sicherung jetzt</button>`}</div>` : ""}</div></div>`;
  document.querySelectorAll("[data-aktion=schichten]").forEach((b) => (b.onclick = () => schichtenDialog(k.maschinen.find((m) => m.id === b.dataset.maschine), k.schichten.filter((s) => s.maschine === b.dataset.maschine))));
  document.querySelectorAll("[data-aktion=stamm]").forEach((b) => (b.onclick = () => maschineDialog(k.maschinen.find((m) => m.id === b.dataset.maschine))));
  document.querySelectorAll("[data-ausnahme]").forEach((b) => (b.onclick = async () => { await api("DELETE", `ausnahmen/${b.dataset.ausnahme}`); laden(); }));
  document.querySelectorAll("[data-stillstand]").forEach((b) => (b.onclick = async () => { if (confirm("Stillstand löschen?")) { await api("DELETE", `stillstaende/${b.dataset.stillstand}`); laden(); } }));
  const maschinenOptionen = k.maschinen.map((m) => `<option>${esc(m.id)}</option>`).join("");
  if ($("#feiertage")) $("#feiertage").onclick = () => dialog(`<h2>Bundesweite Feiertage eintragen</h2><label>Jahr<input name="jahr" type="number" value="${new Date().getFullYear()}" required></label>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Eintragen</button></div>`,
    async (kn, fd) => { const r = await api("POST", "feiertage", { jahr: Number(fd.get("jahr")) }); hinweis(`${r.eingetragen} Feiertage eingetragen`); laden(); });
  if ($("#ausnahme")) $("#ausnahme").onclick = () => dialog(`<h2>Ausnahme anlegen</h2><div class="raster">
    <label>Datum<input name="datum" type="date" required></label><label>Maschine<select name="maschine"><option value="">alle</option>${maschinenOptionen}</select></label>
    <label>Art<select name="art"><option value="frei">frei (Feiertag, Betriebsruhe)</option><option value="zusatz">Zusatzschicht</option></select></label>
    <label>Beginn (nur Zusatzschicht)<input name="beginn" type="time"></label><label>Ende (nur Zusatzschicht)<input name="ende" type="time"></label>
    <label>Bezeichnung<input name="bezeichnung"></label></div>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Anlegen</button></div>`,
    async (kn, fd) => { await api("POST", "ausnahmen", Object.fromEntries(fd)); laden(); });
  if ($("#stillstand")) $("#stillstand").onclick = () => dialog(`<h2>Stillstand anlegen</h2><div class="raster">
    <label>Maschine<select name="maschine">${maschinenOptionen}</select></label>
    <label>Art<select name="art"><option>Wartung</option><option>Störung</option><option>Umbau</option><option>Sonstiges</option></select></label>
    <label>Beginn<input name="beginn" type="datetime-local" required></label><label>Ende<input name="ende" type="datetime-local" required></label>
    <label>Geplant<select name="geplant"><option value="1">ja</option><option value="0">nein (Störung)</option></select></label>
    <label>Bemerkung<input name="bemerkung"></label></div>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Anlegen</button></div>`,
    async (kn, fd) => { await api("POST", "stillstaende", Object.fromEntries(fd)); laden(); });
  if ($("#schwelle")) $("#schwelle").onclick = () => dialog(`<h2>Terminrisiko</h2><label>„kritisch“ bei weniger als … Arbeitstagen Puffer<input name="termin_schwelle_tage" type="number" min="0" value="${esc(e.termin_schwelle_tage)}"></label>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Speichern</button></div>`,
    async (kn, fd) => { await api("PUT", "einstellungen", Object.fromEntries(fd)); laden(); });
  if ($("#sicherung")) $("#sicherung").onclick = async () => { const r = await api("POST", "sicherung"); hinweis(`Sicherung: ${r.pfad}`); };
}

function maschineDialog(m) {
  dialog(`<h2>${esc(m.id)} bearbeiten</h2><div class="raster">
    <label>Bezeichnung<input name="bezeichnung" value="${esc(m.bezeichnung || "")}"></label>
    <label>Status<select name="status">${["verfügbar", "eingeschränkt", "außer Betrieb"].map((s) => `<option ${m.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></label>
    <label>Bemerkung<input name="bemerkung" value="${esc(m.bemerkung || "")}"></label></div>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Speichern</button></div>`,
    async (k, fd) => { await api("PUT", `maschinen/${m.id}`, { daten: Object.fromEntries(fd), version: m.version }); laden(); });
}

function schichtenDialog(m, schichten) {
  const zeile = (s = {}) => `<tr><td><select name="wochentag">${WT.map((t, i) => `<option value="${i}" ${Number(s.wochentag) === i ? "selected" : ""}>${t}</option>`).join("")}</select></td>
    <td><input name="beginn" type="time" value="${esc(s.beginn || "06:00")}" required></td><td><input name="ende" type="time" value="${esc(s.ende || "14:00")}" required></td>
    <td><input name="gueltig_ab" type="date" value="${esc(s.gueltig_ab || "")}"></td><td><input name="gueltig_bis" type="date" value="${esc(s.gueltig_bis || "")}"></td>
    <td><button type="button" class="leise weg">✕</button></td></tr>`;
  const f = dialog(`<h2>Schichtmodell ${esc(m.id)}</h2>
    <p class="klein">Je Zeile ein Zeitfenster, in dem die Maschine laufen kann. Pausen, in denen sie steht, sind Lücken zwischen zwei Fenstern
      (z. B. 06:00–09:00 und 09:15–14:00). Ende vor Beginn = über Mitternacht.</p>
    <table id="schichten"><tr><th>Tag</th><th>Beginn</th><th>Ende</th><th>gültig ab</th><th>gültig bis</th><th></th></tr>${schichten.map(zeile).join("")}</table>
    <div class="knoepfe" style="justify-content:flex-start"><button type="button" class="leise" id="plus">+ Zeile</button>
      <button type="button" class="leise" id="mofr">Letzte Zeile auf Mo–Fr übertragen</button></div>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Speichern</button></div>`,
    async () => {
      const liste = [...f.querySelectorAll("#schichten tr")].slice(1).map((tr) => Object.fromEntries(
        ["wochentag", "beginn", "ende", "gueltig_ab", "gueltig_bis"].map((n) => [n, $(`[name=${n}]`, tr).value])));
      await api("PUT", `maschinen/${m.id}/schichten`, { schichten: liste }); laden();
    });
  const tab = $("#schichten", f);
  const weg = () => tab.querySelectorAll(".weg").forEach((b) => (b.onclick = () => { b.closest("tr").remove(); }));
  weg();
  $("#plus", f).onclick = () => { tab.insertAdjacentHTML("beforeend", zeile()); weg(); };
  $("#mofr", f).onclick = () => {
    const z = [...tab.querySelectorAll("tr")].slice(1).pop();
    const s = z ? Object.fromEntries(["beginn", "ende", "gueltig_ab", "gueltig_bis"].map((n) => [n, $(`[name=${n}]`, z).value])) : {};
    for (let w = 0; w < 5; w++) if (!z || Number($("[name=wochentag]", z).value) !== w) tab.insertAdjacentHTML("beforeend", zeile({ ...s, wochentag: w }));
    weg();
  };
}

// ------------------------------------------------------------------ Benutzer
async function benutzerSeite() {
  const liste = await api("GET", "benutzer");
  $("#inhalt").innerHTML = `<div class="leiste"><h1 style="margin:0">Benutzer</h1><button class="rechts" id="neu">Benutzer anlegen</button></div>
    <table><tr><th>Name</th><th>Anzeigename</th><th>Rolle</th><th>Aktiv</th><th></th></tr>
    ${liste.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.anzeige)}</td><td>${esc(b.rolle)}</td><td>${b.aktiv ? "ja" : "nein"}</td>
      <td><button class="leise" data-name="${esc(b.name)}">Bearbeiten</button></td></tr>`).join("")}</table>
    <p class="klein">lesen = ansehen · planen = Aufträge, Einplanung, Stillstände · verwalten = zusätzlich Maschinen, Schichten, Feiertage, Einstellungen, Benutzer.</p>`;
  const rollen = (r) => ["lesen", "planen", "verwalten"].map((x) => `<option ${x === r ? "selected" : ""}>${x}</option>`).join("");
  $("#neu").onclick = () => dialog(`<h2>Benutzer anlegen</h2><div class="raster"><label>Name<input name="name" required></label><label>Anzeigename<input name="anzeige"></label>
    <label>Rolle<select name="rolle">${rollen("planen")}</select></label><label>Passwort (mindestens 8 Zeichen)<input name="passwort" type="password" minlength="8" required></label></div>
    <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Anlegen</button></div>`,
    async (k, fd) => { await api("POST", "benutzer", Object.fromEntries(fd)); laden(); });
  document.querySelectorAll("[data-name]").forEach((btn) => (btn.onclick = () => {
    const b = liste.find((x) => x.name === btn.dataset.name);
    dialog(`<h2>${esc(b.name)}</h2><div class="raster"><label>Rolle<select name="rolle">${rollen(b.rolle)}</select></label>
      <label>Aktiv<select name="aktiv"><option value="1">ja</option><option value="0" ${b.aktiv ? "" : "selected"}>nein</option></select></label>
      <label>Neues Passwort (leer = unverändert)<input name="passwort" type="password" minlength="8"></label></div>
      <div class="knoepfe"><button value="abbrechen" class="leise" formnovalidate>Abbrechen</button><button value="ok">Speichern</button></div>`,
      async (k, fd) => { await api("PUT", `benutzer/${b.name}`, { rolle: fd.get("rolle"), aktiv: fd.get("aktiv") === "1", passwort: fd.get("passwort") || null }); laden(); });
  }));
}

start().catch((e) => hinweis(e.message, true));
