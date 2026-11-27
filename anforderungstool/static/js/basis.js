// Gemeinsame Helfer: Übersetzung, Server-Anfragen, DOM-Aufbau, Dialoge, Meldungen.

// ---------------------------------------------------------------- Übersetzung
let texte = {};
export let sprache = "de";

export async function spracheLaden(code) {
  const r = await fetch(`i18n/${code}.json`, { cache: "no-cache" });
  if (!r.ok && code !== "de") return spracheLaden("de");
  texte = await r.json();
  sprache = code;
  document.documentElement.lang = code;
}

/** t(schlüssel, {name: "x"}) – fehlende Schlüssel werden sichtbar angezeigt. */
export function t(schluessel, werte = {}) {
  let v = schluessel.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), texte);
  if (v === undefined) return `⟨${schluessel}⟩`;
  if (typeof v !== "string") return v;
  return v.replace(/\{(\w+)\}/g, (_, k) => (werte[k] ?? `{${k}}`));
}

/** Setzt Texte für alle Elemente mit data-i18n unterhalb von wurzel. */
export function uebersetzen(wurzel = document) {
  wurzel.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
}

export function zahl(wert, stellen = 1) {
  return new Intl.NumberFormat(sprache, { maximumFractionDigits: stellen }).format(wert);
}

const GELD = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
export function geld(wert) {
  return wert === null || wert === undefined ? "–" : GELD.format(wert);
}

/** "2026-12-10" → "Do, 10.12.2026" */
export function datumText(iso) {
  if (!iso) return "–";
  const d = new Date(iso.slice(0, 10) + "T00:00:00");
  return `${t("wochentag")[d.getDay()]}, ${d.toLocaleDateString("de-DE")}`;
}

/** Zeitstempel aus der Datenbank (UTC, "2026-11-27 13:05:00") → Ortszeit "27.11.2026, 14:05" */
export function zeitText(utc) {
  if (!utc) return "–";
  const d = new Date(utc.replace(" ", "T") + "Z");
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function heute() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Status als farbige Marke */
export function statusMarke(status) {
  return h(`span.status.${status}`, t(`status.${status}`));
}

/** Anforderungsnummer, z. B. "A-0042" */
export function nummer(id) {
  return `A-${String(id).padStart(4, "0")}`;
}

// ---------------------------------------------------------------- Server
export class ApiFehler extends Error {
  constructor(status, detail, roh = "") {
    let d = detail && typeof detail === "object" && detail.code ? detail : { code: "allgemein" };
    // Unbekannte Antwort (z. B. Prüfung der Anfrage, Proxy, Absturz): Code und Text zeigen, damit man es nachverfolgen kann
    if (d.code === "allgemein" && status) {
      const text = (typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((x) => x.msg || "").join("; ") : roh || "")
        .replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160);
      d = { code: "unbekannt", status, text: text || "–" };
    }
    super(fehlerText(d));
    this.status = status;
    this.code = d.code;
    this.detail = d;
  }
}

export function fehlerText(detail) {
  const text = t(`fehler.${detail.code}`, detail);
  return text.startsWith("⟨") ? t("fehler.allgemein") : text;
}

let beiAbmeldung = () => {};
export function wennAbgemeldet(fn) {
  beiAbmeldung = fn;
}

export async function api(pfad, { methode = "GET", daten, roh = false } = {}) {
  const optionen = { method: methode, headers: {}, credentials: "same-origin" };
  if (daten !== undefined) {
    optionen.headers["Content-Type"] = "application/json";
    optionen.body = JSON.stringify(daten);
  }
  let r;
  try {
    r = await fetch(`/api/${pfad}`, optionen);
  } catch {
    throw new ApiFehler(0, { code: "netzwerk" });
  }
  if (!r.ok) {
    let detail = null;
    try {
      detail = (await r.json()).detail;
    } catch {}
    if (r.status === 401 && pfad !== "anmelden") beiAbmeldung();
    throw new ApiFehler(r.status, detail);
  }
  return roh ? r : r.json();
}

// ---------------------------------------------------------------- DOM
/**
 * h("button.knopf", {onclick: fn, type: "button"}, "Text", kindElement)
 * Texte werden immer als Text eingefügt, nie als HTML.
 */
export function h(tag, attribute = {}, ...kinder) {
  const [name, ...klassen] = tag.split(".");
  const el = document.createElement(name || "div");
  if (klassen.length) el.className = klassen.join(" ");
  if (attribute === null || typeof attribute !== "object" || attribute instanceof Node || Array.isArray(attribute)) {
    kinder.unshift(attribute);
    attribute = {};
  }
  for (const [k, v] of Object.entries(attribute)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className += (el.className ? " " : "") + v;
    else if (k === "style" && typeof v === "object") {
      for (const [eig, wert] of Object.entries(v)) {
        if (eig.startsWith("--")) el.style.setProperty(eig, wert);
        else el.style[eig] = wert;
      }
    }
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kind of kinder.flat(Infinity)) {
    if (kind === null || kind === undefined || kind === false) continue;
    el.append(kind instanceof Node ? kind : String(kind));
  }
  return el;
}

export function leeren(el, ...kinder) {
  el.replaceChildren(...kinder.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}

// ---------------------------------------------------------------- Meldungen
export function melden(text, art = "ok") {
  const el = h(`div.meldung.${art}`, { role: art === "fehler" ? "alert" : "status" }, text);
  document.getElementById("meldungen").append(el);
  setTimeout(() => el.classList.add("weg"), art === "fehler" ? 6000 : 3000);
  setTimeout(() => el.remove(), art === "fehler" ? 6500 : 3500);
}

export function fehlerMelden(e) {
  console.error(e);
  melden(e instanceof ApiFehler ? e.message : t("fehler.allgemein"), "fehler");
}

// ---------------------------------------------------------------- Dialoge
/**
 * Formular-Dialog. felder: [{name, label, typ, wert, optionen, pflicht, hilfe, attr}]
 * typ: text | number | password | time | date | color | auswahl | haken | mehrfach (Häkchenliste, Wert = Array) | textfeld | ueberschrift
 * speichern(werte) darf einen Fehler werfen – dann bleibt der Dialog offen und zeigt ihn an.
 */
export function formularDialog({ titel, felder, speichernText, speichern, gross = false }) {
  return new Promise((fertig) => {
    const fehlerZeile = h("p.dialog-fehler", { hidden: true });
    const eingaben = {};
    const zeilen = felder.map((f) => {
      let feld;
      if (f.typ === "ueberschrift") return h("h3.dialog-abschnitt", f.label);
      if (f.typ === "element") {
        // eigenes Bedienelement: f.element (DOM) und f.lesen() → Wert
        const el = f.element;
        el.wertLesen = f.lesen;
        eingaben[f.name] = el;
        return h("div.feld", f.label ? h("span", f.label) : null, el, f.hilfe && h("small", f.hilfe));
      }
      if (f.typ === "auswahl") {
        feld = h("select", { name: f.name }, f.optionen.map(([wert, text]) => h("option", { value: wert, selected: String(wert) === String(f.wert) }, text)));
      } else if (f.typ === "mehrfach") {
        const gewaehlt = new Set((f.wert || []).map(String));
        feld = h("div.mehrfach", f.optionen.map(([wert, text]) => h("label.haken", h("input", { type: "checkbox", value: wert, checked: gewaehlt.has(String(wert)) }), h("span", text))));
        feld.wertLesen = () => [...feld.querySelectorAll("input:checked")].map((i) => (isNaN(Number(i.value)) ? i.value : Number(i.value)));
        eingaben[f.name] = feld;
        return h("div.feld", h("span", f.label), feld, f.hilfe && h("small", f.hilfe));
      } else if (f.typ === "textfeld") {
        feld = h("textarea", { name: f.name, rows: 3, ...(f.attr || {}) }, f.wert ?? "");
      } else if (f.typ === "haken") {
        feld = h("input", { type: "checkbox", name: f.name, checked: !!f.wert });
      } else {
        feld = h("input", { type: f.typ || "text", name: f.name, value: f.wert ?? "", required: !!f.pflicht, ...(f.attr || {}) });
      }
      eingaben[f.name] = feld;
      return h(`label.feld${f.typ === "haken" ? ".haken" : ""}`, f.typ === "haken" ? [feld, h("span", f.label)] : [h("span", f.label), feld], f.hilfe && h("small", f.hilfe));
    });
    const dialog = h(gross ? "dialog.dialog.gross" : "dialog.dialog");
    const form = h(
      "form",
      { method: "dialog" },
      h("h2", titel),
      zeilen,
      fehlerZeile,
      h(
        "div.dialog-knoepfe",
        h("button.knopf-flach", { type: "button", onclick: () => dialog.close() }, t("allgemein.abbrechen")),
        h("button.knopf", { type: "submit" }, speichernText || t("allgemein.speichern"))
      )
    );
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const werte = {};
      for (const [name, el] of Object.entries(eingaben)) {
        werte[name] = el.wertLesen ? el.wertLesen() : el.type === "checkbox" ? el.checked : el.type === "number" ? (el.value === "" ? null : Number(el.value)) : el.value;
      }
      try {
        const ergebnis = await speichern(werte);
        dialog.close();
        fertig(ergebnis ?? werte);
      } catch (err) {
        fehlerZeile.textContent = err instanceof ApiFehler ? err.message : err.message || t("fehler.allgemein");
        fehlerZeile.hidden = false;
      }
    });
    dialog.append(form);
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(null);
    });
    document.body.append(dialog);
    dialog.showModal();
    form.querySelector("input, select")?.focus();
  });
}

export function bestaetigen(text, knopf = null) {
  return new Promise((fertig) => {
    const dialog = h("dialog.dialog");
    dialog.append(
      h(
        "form",
        { method: "dialog" },
        h("p", text),
        h(
          "div.dialog-knoepfe",
          h("button.knopf-flach", { value: "nein" }, t("allgemein.abbrechen")),
          h("button.knopf.gefahr", { value: "ja" }, knopf || t("allgemein.loeschen"))
        )
      )
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(dialog.returnValue === "ja");
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

/** Auswahl zwischen mehreren Wegen. optionen: [[wert, titel, erklaerung], …] → gewählter Wert oder null. */
export function auswahlDialog(titel, text, optionen) {
  return new Promise((fertig) => {
    const dialog = h("dialog.dialog");
    dialog.append(
      h(
        "form",
        { method: "dialog" },
        h("h2", titel),
        text ? h("p", text) : null,
        h("div.auswahl-optionen", optionen.map(([wert, ueberschrift, erklaerung]) =>
          h("button.auswahl-option", { value: wert }, h("strong", ueberschrift), erklaerung ? h("small", erklaerung) : null))),
        h("div.dialog-knoepfe", h("button.knopf-flach", { value: "" }, t("allgemein.abbrechen")))
      )
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      fertig(dialog.returnValue || null);
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

// ---------------------------------------------------------------- Angemeldeter Benutzer
export const zustand = { benutzer: null, version: "", ich: null };

export function darf(recht) {
  return !!zustand.benutzer?.rechte.includes(recht);
}

