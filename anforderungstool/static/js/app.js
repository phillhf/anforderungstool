// Einstieg: Anmeldung, Navigation und Seitenwechsel (Hash-Routing: #/anforderung/3, #/kataloge …)

import { api, darf, datumText, fehlerMelden, formularDialog, h, leeren, melden, spracheLaden, t, uebersetzen, wennAbgemeldet, zustand } from "./basis.js";
import { zeigeAnforderung, zeigeListe, zeigeTagesliste } from "./anforderungen.js";
import { zeigeBenutzer } from "./benutzer.js";
import { zeigeEinstellungen } from "./einstellungen.js";
import { zeigeKataloge } from "./kataloge.js";
import { zeigeKostenstellen } from "./kostenstellen.js";
import { zeigeStart } from "./start.js";
import { zeigeStatistik } from "./statistik.js";
import { zeigeVertretung } from "./vertretung.js";

const inhalt = document.getElementById("inhalt");

// sichtbar(ich) entscheidet, ob der Menüpunkt erscheint; zaehler(ich) zeigt eine Zahl daneben
const SEITEN = [
  { pfad: "start", menue: "start", zeigen: zeigeStart },
  { pfad: "anforderungen", menue: "meine", zeigen: (w) => zeigeListe(w, "meine"), zaehler: (i) => i.offen.rueckfragen },
  { pfad: "anforderung", zeigen: zeigeAnforderung },
  { pfad: "genehmigen", menue: "genehmigen", sichtbar: (i) => i.genehmiger || i.offen.genehmigen > 0, zeigen: (w) => zeigeListe(w, "genehmigen"), zaehler: (i) => i.offen.genehmigen },
  { pfad: "ausfuehren", menue: "ausfuehren", sichtbar: (i) => i.ausfuehrender, zaehler: (i) => i.offen.ausfuehren,
    zeigen: (w, rest) => (rest[0] === "druck" ? zeigeTagesliste(w, rest[1]) : zeigeListe(w, "ausfuehren")) },
  { pfad: "alle", menue: "alle", sichtbar: () => darf("verwalten"), zeigen: (w) => zeigeListe(w, "alle") },
  { pfad: "kataloge", menue: "kataloge", sichtbar: (i) => darf("verwalten") || i.pfleger, zeigen: zeigeKataloge },
  { pfad: "statistik", menue: "statistik", sichtbar: () => darf("verwalten") || darf("statistik"), zeigen: zeigeStatistik },
  { pfad: "benutzer", menue: "benutzer", sichtbar: () => darf("verwalten"), zeigen: zeigeBenutzer },
  { pfad: "kostenstellen", menue: "kostenstellen", sichtbar: () => darf("verwalten"), zeigen: zeigeKostenstellen },
  { pfad: "einstellungen", menue: "einstellungen", sichtbar: () => darf("verwalten"), zeigen: zeigeEinstellungen },
  { pfad: "vertretung", zeigen: zeigeVertretung },
];

async function start() {
  let status;
  try {
    status = await api("status");
  } catch (e) {
    await spracheLaden("de");
    leeren(inhalt, h("div.mitte", h("p.fehlertext", e.message)));
    return;
  }
  await spracheLaden("de");
  uebersetzen();
  zustand.version = status.version;
  zustand.benutzer = status.benutzer;
  if (status.ersteinrichtung) return zeigeErsteinrichtung();
  if (!status.benutzer) return zeigeAnmeldung();
  await ichLaden();
  kopfAufbauen();
  updateHinweis();
  setInterval(async () => {
    versionPruefen();
    const vorher = JSON.stringify(zustand.ich?.offen);
    try {
      await ichLaden();
    } catch {
      return;
    }
    menueAufbauen();
    // Die Übersicht zeigt neue Aufgaben, ohne dass man neu laden muss
    if (aktuelleSeite() === "start" && JSON.stringify(zustand.ich.offen) !== vorher && !document.querySelector("dialog[open]")) seiteWechseln();
  }, 60000);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && versionPruefen());
  window.addEventListener("hashchange", () => {
    versionPruefen();
    seiteWechseln();
  });
  seiteWechseln();
}

async function ichLaden() {
  zustand.ich = await api("ich");
  zustand.benutzer = { ...zustand.benutzer, ...zustand.ich };
}

// Nach einer Aktion holen die Seiten über zustand.zaehler() die Zahlen im Menü neu
zustand.zaehler = () => ichLaden().then(menueAufbauen).catch(() => {});

let letztePruefung = 0;
async function versionPruefen() {
  if (Date.now() - letztePruefung < 5000) return;
  letztePruefung = Date.now();
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    const { version } = await r.json();
    if (version && zustand.version && version !== zustand.version) location.reload();
  } catch {}
}

wennAbgemeldet(() => location.reload());

// ---------------------------------------------------------------- Anmeldung
function zeigeAnmeldung() {
  const fehler = h("p.fehlertext", { hidden: true });
  const name = h("input", { name: "benutzername", autocomplete: "username", required: true });
  const pw = h("input", { name: "passwort", type: "password", autocomplete: "current-password", required: true });
  const form = h(
    "form.anmeldekarte",
    h("img", { src: "favicon.svg", width: 48, height: 48, alt: "" }),
    h("h1", t("app.name")),
    h("label.feld", h("span", t("anmeldung.benutzername")), name),
    h("label.feld", h("span", t("anmeldung.passwort")), pw),
    fehler,
    h("button.knopf.breit", { type: "submit" }, t("anmeldung.anmelden"))
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("anmelden", { methode: "POST", daten: { benutzername: name.value, passwort: pw.value } });
      location.reload();
    } catch (err) {
      fehler.textContent = err.message;
      fehler.hidden = false;
    }
  });
  leeren(inhalt, h("div.mitte", form));
  name.focus();
}

function zeigeErsteinrichtung() {
  const fehler = h("p.fehlertext", { hidden: true });
  const felder = {
    benutzername: h("input", { required: true, value: "admin", autocomplete: "username" }),
    anzeigename: h("input", { placeholder: t("ersteinrichtung.anzeigename_hilfe") }),
    email: h("input", { type: "email" }),
    passwort: h("input", { type: "password", required: true, autocomplete: "new-password" }),
  };
  const form = h(
    "form.anmeldekarte",
    h("img", { src: "favicon.svg", width: 48, height: 48, alt: "" }),
    h("h1", t("ersteinrichtung.titel")),
    h("p", t("ersteinrichtung.text")),
    Object.entries(felder).map(([k, el]) => h("label.feld", h("span", t(`ersteinrichtung.${k}`)), el)),
    fehler,
    h("button.knopf.breit", { type: "submit" }, t("ersteinrichtung.anlegen"))
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("ersteinrichtung", { methode: "POST", daten: Object.fromEntries(Object.entries(felder).map(([k, el]) => [k, el.value])) });
      location.hash = "#/einstellungen";
      location.reload();
    } catch (err) {
      fehler.textContent = err.message;
      fehler.hidden = false;
    }
  });
  leeren(inhalt, h("div.mitte", form));
}

// ---------------------------------------------------------------- Kopf und Menü
function kopfAufbauen() {
  document.getElementById("kopf").hidden = false;
  menueAufbauen();
  const knopf = document.getElementById("benutzer-knopf");
  const liste = document.getElementById("benutzer-liste");
  knopf.textContent = `${zustand.benutzer.anzeigename} ▾`;
  knopf.onclick = (e) => {
    e.stopPropagation();
    liste.hidden = !liste.hidden;
  };
  document.addEventListener("click", () => (liste.hidden = true));
  liste.querySelector('[data-aktion="passwort"]').hidden = zustand.benutzer.quelle !== "lokal";
  liste.onclick = async (e) => {
    const aktion = e.target.dataset.aktion;
    if (aktion === "abmelden") {
      await api("abmelden", { methode: "POST" });
      location.hash = "";
      location.reload();
    } else if (aktion === "passwort") passwortAendern();
    else if (aktion === "vertretung") location.hash = "#/vertretung";
  };
  const nav = document.getElementById("navigation");
  document.getElementById("menue-knopf").onclick = (e) => {
    e.stopPropagation();
    nav.classList.toggle("offen");
  };
  document.addEventListener("click", () => nav.classList.remove("offen"));
}

function aktuelleSeite() {
  return location.hash.split("/")[1] || "start";
}

function menueAufbauen() {
  const ich = zustand.ich;
  const nav = document.getElementById("navigation");
  const aktuell = aktuelleSeite();
  const update = nav.querySelector(".nav-update");
  leeren(
    nav,
    SEITEN.filter((s) => s.menue && (!s.sichtbar || s.sichtbar(ich))).map((s) => {
      const zahl = s.zaehler ? s.zaehler(ich) : 0;
      const aktiv = aktuell === s.pfad || (s.pfad === "anforderungen" && location.hash.startsWith("#/anforderung/neu"));
      return h("a", { href: `#/${s.pfad}`, class: aktiv ? "aktiv" : "" }, t(`menue.${s.menue}`), zahl ? h("span.zaehler", zahl) : null);
    }),
    update
  );
  // Offene Aufgaben auch im Browser-Tab, wenn das Tool im Hintergrund offen ist
  const offen = ich.offen.genehmigen + ich.offen.ausfuehren + ich.offen.rueckfragen;
  document.title = offen ? `(${offen}) ${t("app.name")}` : t("app.name");
  hinweisleisteAufbauen();
}

/** Leiste unter dem Kopf: laufende Vertretungen – damit klar ist, warum man fremde Anforderungen sieht */
function hinweisleisteAufbauen() {
  const ich = zustand.ich;
  const leiste = document.getElementById("hinweisleiste");
  const bis = (liste) => liste.map((v) => t("hinweisleiste.person_bis", { name: v.name, bis: datumText(v.bis) })).join(", ");
  const punkte = [
    ich.ich_vertrete.length ? h("span", "↪ ", t("hinweisleiste.ich_vertrete", { namen: bis(ich.ich_vertrete) }), " ",
      h("a", { href: "#/genehmigen" }, t("hinweisleiste.zu_genehmigen"))) : null,
    ich.vertreten_durch.length ? h("span", "⏸ ", t("hinweisleiste.vertreten_durch", { namen: bis(ich.vertreten_durch) }), " ",
      h("a", { href: "#/vertretung" }, t("hinweisleiste.aendern"))) : null,
  ].filter(Boolean);
  leeren(leiste, punkte);
  leiste.hidden = !punkte.length;
}

/** Admins sehen im Menü, wenn es eine neue Version gibt */
async function updateHinweis() {
  if (!darf("verwalten")) return;
  let u;
  try {
    u = await api("update");
  } catch {
    return;
  }
  const nav = document.getElementById("navigation");
  nav.querySelector(".nav-update")?.remove();
  if (!u.verfuegbar) return;
  nav.append(h("a.nav-update", { href: "#/einstellungen/update" }, "⬆ " + t("update.nav", { version: u.neueste })));
}

let aufraeumen = null;
async function seiteWechseln() {
  const teile = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const seite = SEITEN.find((s) => s.pfad === teile[0]) || SEITEN[0];
  if (typeof aufraeumen === "function") aufraeumen();
  aufraeumen = null;
  menueAufbauen();
  leeren(inhalt);
  try {
    aufraeumen = await seite.zeigen(inhalt, teile.slice(1));
  } catch (e) {
    fehlerMelden(e);
    leeren(inhalt, h("p.fehlertext", e.message));
  }
}

function passwortAendern() {
  formularDialog({
    titel: t("menue.passwort_aendern"),
    felder: [
      { name: "altes_passwort", label: t("passwort.alt"), typ: "password", pflicht: true },
      { name: "neues_passwort", label: t("passwort.neu"), typ: "password", pflicht: true, hilfe: t("passwort.regel") },
    ],
    speichern: (w) => api("ich/passwort", { methode: "POST", daten: w }),
  }).then((r) => r && melden(t("passwort.geaendert")));
}

start();
