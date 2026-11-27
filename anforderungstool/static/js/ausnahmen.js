// Ausnahmeanträge: Listen, Antrag stellen/bearbeiten, Ansicht mit Strecke (Weg durch die Stellen) und Verlauf

import {
  ApiFehler, api, bestaetigen, darf, fehlerMelden, formularDialog, geld, h, leeren, melden, seitMarke, statusMarke, t, zeitText, zustand,
} from "./basis.js";

export function aaNummer(id) {
  return `AA-${String(id).padStart(4, "0")}`;
}

const zahlText = (n) => String(n ?? "").replace(".", ",");

// ---------------------------------------------------------------- Listen
const FILTER = {
  meine: ["", "entwurf", "pruefung", "rueckfrage", "freigegeben", "bestellt", "geliefert", "erledigt", "abgelehnt"],
  pruefen: [""],
  bestellung: ["", "erledigt"],
  alle: ["", "pruefung", "rueckfrage", "freigegeben", "bestellt", "geliefert", "erledigt", "abgelehnt"],
};

function ansichten() {
  const ich = zustand.ich;
  return [
    "meine",
    ich.fachstellen.length || ich.genehmiger || ich.offen_ausnahmen.pruefen ? "pruefen" : null,
    ich.ausnahme_ausfuehrend ? "bestellung" : null,
    darf("verwalten") ? "alle" : null,
  ].filter(Boolean);
}

export async function zeigeAusnahmeListe(wurzel, ansicht) {
  const moeglich = ansichten();
  if (!moeglich.includes(ansicht)) ansicht = moeglich[0];
  let status = "";
  let unteransicht = ansicht;
  const ich = zustand.ich;
  const zahl = { pruefen: ich.offen_ausnahmen.pruefen, bestellung: ich.offen_ausnahmen.bestellen, meine: ich.offen_ausnahmen.rueckfragen };

  const box = h("div.box");
  const filter = h("div.reiter.klein");
  leeren(wurzel,
    h("div.seitenkopf",
      h("div", h("h1", t("ausnahme.titel")), h("p.untertitel", t(`ausnahme.liste_hilfe.${ansicht}`))),
      h("a.knopf", { href: "#/ausnahme/neu" }, `+ ${t("ausnahme.neu")}`)),
    moeglich.length > 1 ? h("div.reiter", moeglich.map((a) => h("a", { href: `#/ausnahmen/${a}`, class: a === ansicht ? "aktiv" : "" },
      t(`ausnahme.ansicht.${a}`), zahl[a] ? h("span.zaehler", zahl[a]) : null))) : null,
    filter, box);

  function filterAufbauen() {
    const werte = ansicht === "pruefen" ? null : FILTER[ansicht];
    if (ansicht === "pruefen") {
      leeren(filter, [["pruefen", t("liste.offen")], ["entschieden", t("liste.entschieden")]].map(([w, text]) =>
        h("a", { href: "#", class: unteransicht === w ? "aktiv" : "", onclick: (e) => { e.preventDefault(); unteransicht = w; laden(); } }, text)));
      return;
    }
    leeren(filter, werte.map((s) => h("a", { href: "#", class: status === s ? "aktiv" : "",
      onclick: (e) => { e.preventDefault(); status = s; laden(); } }, s ? t(`status.${s}`) : t(ansicht === "bestellung" ? "ausnahme.offen" : "liste.alle_status"))));
  }

  async function laden() {
    filterAufbauen();
    const server = unteransicht === "bestellung" ? "ausfuehren" : unteransicht;
    let zeilen;
    try {
      zeilen = await api(`ausnahmen?ansicht=${server}${status ? `&status=${status}` : ""}`);
    } catch (e) {
      fehlerMelden(e);
      return;
    }
    if (!zeilen.length) return leeren(box, h("p.leer", t(`ausnahme.leer.${unteransicht}`)));
    const mitAntragsteller = ansicht !== "meine";
    leeren(box, h("div.tabelle-rahmen", h("table.tabelle",
      h("thead", h("tr", h("th", t("feld.nummer")), h("th", t("ausnahme.feld.titel")), h("th.weg-schmal", t("ausnahme.feld.bereich")),
        mitAntragsteller ? h("th", t("feld.antragsteller")) : null, h("th.betrag", t("feld.summe")), h("th", t("feld.status")))),
      h("tbody", zeilen.map((z) => h("tr.klickbar", { onclick: () => (location.hash = `#/ausnahme/${z.id}`) },
        h("td", aaNummer(z.id)),
        h("td", z.titel || h("span.gedimmt", t("liste.ohne_anlass")), z.vertretung_fuer ? h("span.marke-klein.gelb", t("start.fuer", { name: z.vertretung_fuer })) : null),
        h("td.weg-schmal", z.bereich || "–"),
        mitAntragsteller ? h("td", z.antragsteller) : null,
        h("td.betrag", geld(z.summe)),
        h("td.status-zelle",
          unteransicht === "pruefen" ? h("span.status.pruefung", t("ausnahme.als", { station: z.station })) : statusMarke(z.status),
          schritt(z, unteransicht))))))));
  }
  await laden();
}

/** Zweite Zeile: bei wem es liegt und seit wann */
export function schritt(z, ansicht) {
  if (["erledigt", "abgelehnt"].includes(z.status)) return null;
  if (z.status === "entwurf") return h("small.schritt", t("liste.noch_uebermitteln"));
  if (ansicht === "pruefen") return h("small.schritt", t("liste.wartet"), " ", seitMarke(z.seit));
  let text;
  if (z.status === "pruefung") text = t("liste.bei", { name: z.station });
  else if (z.status === "rueckfrage") text = ansicht === "meine" ? h("strong.dran", t("liste.du_bist_dran")) : t("liste.bei", { name: z.antragsteller });
  else text = t("ausnahme.bei_bestellung");
  return h("small.schritt", text, " · ", seitMarke(z.seit));
}

// ---------------------------------------------------------------- Ansicht
export async function zeigeAusnahme(wurzel, [id, modus]) {
  if (id === "neu") return zeigeEditor(wurzel, null);
  const a = await api(`ausnahmen/${id}`);
  if (modus === "bearbeiten" && a.aktionen.includes("bearbeiten")) return zeigeEditor(wurzel, a);
  zeigeAnsicht(wurzel, a);
}

function eintrag(titel, wert) {
  return h("div", h("dt", titel), h("dd", wert === null || wert === undefined || wert === "" ? "–" : wert));
}

function zeigeAnsicht(wurzel, a) {
  const neu = (x) => zeigeAnsicht(wurzel, x);
  leeren(wurzel,
    h("div.seitenkopf",
      h("div", h("a.knopf-flach", { href: "javascript:history.back()" }, `← ${t("allgemein.zurueck")}`),
        h("h1", `${aaNummer(a.id)} · ${a.titel || t("liste.ohne_anlass")} `, statusMarke(a.status)))),
    aktionsleiste(a, neu),
    h("div.ausnahme-spalten",
      h("div.box.strecke-box", h("h2", t("ausnahme.strecke")), strecke(a)),
      h("div.links",
        h("div.box", h("h2", t("anforderung.angaben")), h("dl.kopfdaten",
          eintrag(t("feld.antragsteller"), a.antragsteller),
          eintrag(t("ausnahme.feld.bereich"), a.bereich),
          eintrag(t("feld.kostenstelle"), a.kostenstelle_nummer ? `${a.kostenstelle_nummer} ${a.kostenstelle_bezeichnung || ""}` : ""),
          eintrag(t("ausnahme.feld.uebermittelt"), a.uebermittelt ? zeitText(a.uebermittelt) : "")),
          a.beschreibung ? h("div.textblock", h("h3", t("ausnahme.feld.beschreibung")), h("p.vortext", a.beschreibung)) : null),
        h("div.box", h("h2", t("ausnahme.kosten")), h("dl.kopfdaten",
          eintrag(t("feld.menge"), zahlText(a.menge)),
          eintrag(t("ausnahme.feld.einzelpreis"), geld(a.einzelpreis)),
          eintrag(t("feld.summe"), h("strong", geld(a.summe))),
          eintrag(t("ausnahme.feld.laufende_kosten"), a.laufende_kosten ? `${geld(a.laufende_kosten)} ${t("ausnahme.pro_jahr")}` : ""),
          eintrag(t("ausnahme.feld.lieferant"), a.lieferant))),
        h("div.box", h("h2", t("ausnahme.feld.begruendung")), h("p.vortext", a.begruendung || "–"),
          a.wirtschaftlichkeit ? [h("h3", t("ausnahme.feld.wirtschaftlichkeit")), h("p.vortext", a.wirtschaftlichkeit)] : null),
        anhangBox(a, () => api(`ausnahmen/${a.id}`).then(neu)),
        a.aktionen.includes("notiz") ? notizBox(a, neu) : null),
      h("div.box.verlauf-box", h("h2", t("anforderung.verlauf")), verlauf(a)))
  );
}

/** Der ganze Weg: Stationen (erledigt / jetzt / kommt noch), danach Bestellung bis erledigt */
function strecke(a) {
  const punkte = [];
  const aktuell = a.status === "pruefung" || a.status === "rueckfrage" ? a.stationen.find((s) => s.status === "offen") : null;
  const seit = a.verlauf.length ? a.verlauf[a.verlauf.length - 1].zeit : a.erstellt;
  const abgelehntBei = a.status === "abgelehnt" ? [...a.verlauf].reverse().find((v) => v.aktion === "abgelehnt")?.station : null;
  let abgelehntGesehen = false;
  if (a.status === "entwurf") {
    punkte.push(h("li.jetzt", h("strong", t("ausnahme.strecke_entwurf")), h("small", t("ausnahme.strecke_entwurf_hilfe"))));
    for (const name of a.geplant || []) punkte.push(h("li.spaeter", h("span", name)));
  }
  for (const s of a.stationen) {
    const art = s.art === "vorgesetzter" ? t("ausnahme.vorgesetzter") : t("ausnahme.fachstelle");
    const dazu = s.hinzugefuegt_von ? h("small", t("ausnahme.hinzugezogen_von", { name: s.hinzugefuegt_von })) : null;
    if (s.status === "freigegeben") {
      const wer = s.im_namen_von ? t("verlauf.in_vertretung", { name: s.entschieden_von, fuer: s.im_namen_von }) : s.entschieden_von;
      punkte.push(h("li.gruen", h("strong", `✓ ${s.name}`), h("small", `${art} · ${t("ausnahme.freigegeben_von", { name: wer })} · ${zeitText(s.entschieden_am)}`), dazu));
    } else if (abgelehntBei === s.name && !abgelehntGesehen) {
      abgelehntGesehen = true;
      punkte.push(h("li.rot", h("strong", `✗ ${s.name}`), h("small", `${art} · ${t("status.abgelehnt")}`), dazu));
    } else if (aktuell && s.id === aktuell.id) {
      const text = a.status === "rueckfrage" ? t("ausnahme.strecke_rueckfrage", { name: s.name, antragsteller: a.antragsteller }) : t("ausnahme.strecke_jetzt", { name: s.name });
      punkte.push(h("li.jetzt", h("strong", text), h("small", art, " · ", seitMarke(seit)), dazu));
    } else {
      punkte.push(h(a.status === "abgelehnt" ? "li.spaeter.weg-durch" : "li.spaeter", h("span", s.name), h("small", art), dazu));
    }
  }
  if (a.status !== "abgelehnt") {
    const nach = ["freigegeben", "bestellt", "geliefert", "erledigt"];
    const index = nach.indexOf(a.status);
    for (const [i, s] of nach.slice(1).entries()) {
      const fertig = index >= i + 1;
      const jetzt = index === i;
      if (fertig) punkte.push(h("li.blau", h("strong", `✓ ${t(`status.${s}`)}`)));
      else if (jetzt) punkte.push(h("li.jetzt", h("strong", t(`ausnahme.strecke_${s}`)), h("small", seitMarke(seit))));
      else punkte.push(h("li.spaeter", h("span", t(`status.${s}`))));
    }
  }
  return h("ol.zeitleiste", punkte);
}

const FARBE = { uebermittelt: "blau", erneut_uebermittelt: "blau", freigegeben: "gruen", endgueltig_freigegeben: "gruen", rueckfrage: "gelb",
  abgelehnt: "rot", hinzugezogen: "gelb", bestellt: "blau", geliefert: "blau", erledigt: "blau" };

function verlauf(a) {
  if (!a.verlauf.length) return h("p.leer", t("verlauf.leer"));
  return h("ol.zeitleiste", a.verlauf.map((v) => {
    let titel = t(`ausnahme.verlauf.${v.aktion}`, { station: v.station, weiter_an: v.weiter_an });
    if (v.weiter_an && ["uebermittelt", "erneut_uebermittelt", "freigegeben"].includes(v.aktion)) titel += ` – ${t("verlauf.weiter_an", { name: v.weiter_an })}`;
    const wer = !v.benutzer ? t("ausnahme.system") : v.im_namen_von ? t("verlauf.in_vertretung", { name: v.benutzer, fuer: v.im_namen_von }) : v.benutzer;
    const notizAlsText = ["anhang", "anhang_entfernt"].includes(v.aktion);
    return h(`li.${FARBE[v.aktion] || ""}`, h("strong", titel, notizAlsText ? `: ${v.notiz}` : ""), h("small", `${wer} · ${zeitText(v.zeit)}`),
      v.notiz && !notizAlsText ? h("p.notiz", v.notiz) : null);
  }));
}

function aktionsleiste(a, neu) {
  const k = a.aktionen;
  const knoepfe = [];
  let text = null;
  const senden = async (pfad, daten, erfolg) => {
    try {
      const r = await api(`ausnahmen/${a.id}/${pfad}`, { methode: "POST", daten });
      zustand.zaehler?.();
      if (erfolg) melden(erfolg);
      neu(r);
    } catch (e) {
      fehlerMelden(e);
    }
  };
  if (k.includes("bearbeiten")) {
    text = t(a.status === "rueckfrage" ? "ausnahme.rueckfrage_text" : "ausnahme.entwurf_text");
    knoepfe.push(h("a.knopf.rand", { href: `#/ausnahme/${a.id}/bearbeiten` }, t("aktion.bearbeiten")));
    knoepfe.push(h("button.knopf", { onclick: () => uebermittelnDialog(a).then((r) => r && neu(r)) },
      t(a.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln")));
  }
  if (k.includes("loeschen")) {
    knoepfe.push(h("button.knopf-flach.gefahr", {
      onclick: async () => {
        if (!(await bestaetigen(t("anforderung.loeschen_frage")))) return;
        try {
          await api(`ausnahmen/${a.id}`, { methode: "DELETE" });
          location.hash = "#/ausnahmen";
        } catch (e) {
          fehlerMelden(e);
        }
      },
    }, t("allgemein.loeschen")));
  }
  if (k.includes("freigeben")) {
    const offen = a.stationen.filter((s) => s.status === "offen");
    const jetzt = offen[0];
    const naechste = offen[1];
    text = [
      h("strong", t("ausnahme.du_pruefst", { station: jetzt.name }), a.vertretung_fuer ? ` ${t("ausnahme.in_vertretung", { name: a.vertretung_fuer })}` : "", " "),
      naechste ? t("ausnahme.freigeben_weiter", { name: naechste.name }) : t("ausnahme.freigeben_ende"),
    ];
    const entscheiden = (aktion, pflicht) => formularDialog({
      titel: t(`ausnahme.aktion.${aktion}`),
      felder: [{ name: "notiz", label: t(pflicht ? "anforderung.begruendung" : "anforderung.notiz_optional"), typ: "textfeld" }],
      speichernText: t(`ausnahme.aktion.${aktion}`),
      speichern: (w) => {
        if (pflicht && !w.notiz.trim()) throw new Error(t("fehler.notiz_fehlt"));
        return api(`ausnahmen/${a.id}/entscheidung`, { methode: "POST", daten: { aktion, notiz: w.notiz } });
      },
    }).then((r) => {
      if (r && r.id) {
        zustand.zaehler?.();
        melden(t(`ausnahme.erfolg.${aktion === "freigeben" && r.status === "freigegeben" ? "endgueltig" : aktion}`));
        neu(r);
      }
    });
    knoepfe.push(h("button.knopf.gruen", { onclick: () => entscheiden("freigeben", false) }, t("ausnahme.aktion.freigeben")));
    knoepfe.push(h("button.knopf.rand", { onclick: () => entscheiden("rueckfrage", true) }, t("ausnahme.aktion.rueckfrage")));
    knoepfe.push(h("button.knopf.rand", { onclick: () => hinzuziehenDialog(a, neu) }, `+ ${t("ausnahme.aktion.hinzuziehen")}`));
    knoepfe.push(h("button.knopf.gefahr", { onclick: () => entscheiden("ablehnen", true) }, t("ausnahme.aktion.ablehnen")));
  }
  if (k.includes("status")) {
    const folge = ["bestellt", "geliefert", "erledigt"].filter((s) => ["freigegeben", "bestellt", "geliefert", "erledigt"].indexOf(s) > ["freigegeben", "bestellt", "geliefert", "erledigt"].indexOf(a.status));
    text = t(`ausnahme.status_text.${a.status}`);
    folge.forEach((s, i) => knoepfe.push(h(i === 0 ? "button.knopf.gruen" : "button.knopf.rand", {
      onclick: () => formularDialog({
        titel: t(`ausnahme.melden.${s}`),
        felder: [{ name: "notiz", label: t(`ausnahme.melden_notiz.${s}`), typ: "textfeld" }],
        speichernText: t(`ausnahme.melden.${s}`),
        speichern: (w) => api(`ausnahmen/${a.id}/status`, { methode: "POST", daten: { status: s, notiz: w.notiz } }),
      }).then((r) => {
        if (r && r.id) {
          zustand.zaehler?.();
          melden(t("allgemein.gespeichert"));
          neu(r);
        }
      }),
    }, t(`ausnahme.melden.${s}`))));
  }
  if (!knoepfe.length) return null;
  return h("div.aktionsleiste", text ? h("p", text) : null, knoepfe);
}

async function hinzuziehenDialog(a, neu) {
  const stellen = await api("fachstellen");
  const dabei = new Set(a.stationen.map((s) => s.fachstelle_id).filter(Boolean));
  const moeglich = stellen.filter((s) => !dabei.has(s.id));
  if (!moeglich.length) return melden(t("ausnahme.alle_dabei"));
  const r = await formularDialog({
    titel: t("ausnahme.aktion.hinzuziehen"),
    felder: [
      { typ: "element", name: "_", lesen: () => null, element: h("p.hinweis", t("ausnahme.hinzuziehen_hilfe")) },
      { name: "fachstelle_id", label: t("ausnahme.fachstelle"), typ: "auswahl", optionen: moeglich.map((s) => [s.id, s.name]) },
      { name: "notiz", label: t("ausnahme.hinzuziehen_grund"), typ: "textfeld" },
    ],
    speichernText: t("ausnahme.aktion.hinzuziehen"),
    speichern: (w) => api(`ausnahmen/${a.id}/hinzuziehen`, { methode: "POST", daten: { fachstelle_id: Number(w.fachstelle_id), notiz: w.notiz } }),
  });
  if (r && r.id) {
    melden(t("ausnahme.erfolg.hinzuziehen"));
    neu(r);
  }
}

async function uebermittelnDialog(a) {
  const felder = a.status === "rueckfrage" ? [{ name: "notiz", label: t("anforderung.antwort"), typ: "textfeld" }] : [];
  const r = await formularDialog({
    titel: t(a.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln"),
    felder: [{ typ: "element", name: "_", lesen: () => null, element: h("p", t("ausnahme.uebermitteln_frage", { summe: geld(a.summe) })) }, ...felder],
    speichernText: t("aktion.uebermitteln"),
    speichern: (w) => api(`ausnahmen/${a.id}/uebermitteln`, { methode: "POST", daten: { notiz: w.notiz || "" } }),
  });
  if (r && r.id) {
    zustand.zaehler?.();
    melden(t("ausnahme.erfolg.uebermittelt"));
    return r;
  }
  return null;
}

function notizBox(a, neu) {
  const feld = h("textarea", { rows: 2, maxLength: 5000, placeholder: t("ausnahme.notiz_platzhalter") });
  return h("div.box", h("h2", t("ausnahme.notiz_titel")), h("p.hinweis", t("ausnahme.notiz_hilfe")), feld,
    h("div.knopfreihe", { style: { marginTop: "8px" } }, h("button.knopf.rand", {
      onclick: async () => {
        if (!feld.value.trim()) return;
        try {
          neu(await api(`ausnahmen/${a.id}/notiz`, { methode: "POST", daten: { notiz: feld.value } }));
          melden(t("allgemein.gespeichert"));
        } catch (e) {
          fehlerMelden(e);
        }
      },
    }, t("ausnahme.notiz_senden"))));
}

// ---------------------------------------------------------------- Anhänge
async function hochladen(aid, datei) {
  const r = await fetch(`api/ausnahmen/${aid}/anhaenge?name=${encodeURIComponent(datei.name)}`, {
    method: "POST", body: datei, headers: { "Content-Type": "application/octet-stream" },
  });
  if (!r.ok) {
    let detail = null;
    try {
      detail = (await r.json()).detail;
    } catch {}
    throw new ApiFehler(r.status, detail);
  }
  return r.json();
}

/** Anhänge anzeigen; hochladen = (Dateien) => Promise, wenn Hochladen erlaubt ist */
function anhangListe(anhaenge, { loeschbar, neuLaden }) {
  if (!anhaenge.length) return h("p.leer", t("ausnahme.keine_anhaenge"));
  return h("ul.anhaenge", anhaenge.map((d) => h("li",
    h("a", { href: `api/anhaenge/${d.id}` }, `📎 ${d.name}`),
    h("small.gedimmt", ` ${Math.max(1, Math.round(d.groesse / 1024))} KB · ${d.benutzer || ""} · ${zeitText(d.erstellt)}`),
    loeschbar(d) ? h("button.knopf-flach.gefahr", {
      onclick: async () => {
        if (!(await bestaetigen(t("ausnahme.anhang_loeschen", { name: d.name })))) return;
        try {
          await api(`anhaenge/${d.id}`, { methode: "DELETE" });
          neuLaden();
        } catch (e) {
          fehlerMelden(e);
        }
      },
    }, "✕") : null)));
}

function dateiAuswahl(beiDateien) {
  const eingabe = h("input", { type: "file", multiple: true, hidden: true, onchange: async () => {
    const dateien = [...eingabe.files];
    eingabe.value = "";
    await beiDateien(dateien);
  } });
  return h("div.knopfreihe", eingabe, h("button.knopf.rand", { type: "button", onclick: () => eingabe.click() }, `📎 ${t("ausnahme.anhang_hinzu")}`),
    h("small.gedimmt", t("ausnahme.anhang_regel")));
}

function anhangBox(a, neuLaden) {
  const ich = zustand.ich;
  const abgeschlossen = ["erledigt", "abgelehnt"].includes(a.status);
  const loeschbar = (d) => darf("verwalten") || (d.benutzer_id === ich.id && !abgeschlossen &&
    (d.benutzer_id !== a.antragsteller_id || ["entwurf", "rueckfrage"].includes(a.status)));
  return h("div.box", h("h2", t("ausnahme.anhaenge")),
    anhangListe(a.anhaenge, { loeschbar, neuLaden }),
    a.aktionen.includes("anhang") ? dateiAuswahl(async (dateien) => {
      for (const d of dateien) {
        try {
          await hochladen(a.id, d);
        } catch (e) {
          fehlerMelden(e);
        }
      }
      neuLaden();
    }) : null);
}

// ---------------------------------------------------------------- Antrag stellen und bearbeiten
async function zeigeEditor(wurzel, a) {
  const ich = zustand.ich;
  const [kostenstellen, stellen] = await Promise.all([api("kostenstellen"), api("fachstellen")]);
  const auswahl = new Set(a?.auswahl || []);
  const feld = (name, el, pflicht = false, hilfe = null) => h(`label.feld${pflicht ? ".pflicht" : ""}`, h("span", t(`ausnahme.feld.${name}`)), el, hilfe ? h("small", hilfe) : null);
  const e = {
    titel: h("input", { value: a?.titel || "", maxLength: 200, placeholder: t("ausnahme.beispiel.titel") }),
    beschreibung: h("textarea", { rows: 3, maxLength: 5000, placeholder: t("ausnahme.beispiel.beschreibung") }, a?.beschreibung || ""),
    bereich: h("input", { value: a?.bereich || "", maxLength: 200, placeholder: t("ausnahme.beispiel.bereich") }),
    kostenstelle_id: h("select", h("option", { value: "" }, t("editor.bitte_waehlen")),
      kostenstellen.map((k) => h("option", { value: k.id, selected: k.id === (a ? a.kostenstelle_id : ich.kostenstelle_id) }, `${k.nummer} ${k.bezeichnung}`))),
    menge: h("input", { type: "number", min: 0, step: "any", value: a?.menge ?? 1 }),
    einzelpreis: h("input", { type: "number", min: 0, step: "0.01", value: a?.einzelpreis || "", placeholder: "0,00" }),
    laufende_kosten: h("input", { type: "number", min: 0, step: "0.01", value: a?.laufende_kosten ?? "" }),
    lieferant: h("input", { value: a?.lieferant || "", maxLength: 500 }),
    begruendung: h("textarea", { rows: 4, maxLength: 5000, placeholder: t("ausnahme.beispiel.begruendung") }, a?.begruendung || ""),
    wirtschaftlichkeit: h("textarea", { rows: 4, maxLength: 10000, placeholder: t("ausnahme.beispiel.wirtschaftlichkeit") }, a?.wirtschaftlichkeit || ""),
  };
  const summeEl = h("div.summe");
  const wegEl = h("div");
  const fehlerEl = h("p.fehlertext", { hidden: true });
  const anhangEl = h("div");
  let anhaenge = a?.anhaenge || [];

  const zahlWert = (el) => (el.value === "" ? null : Number(String(el.value).replace(",", ".")));
  function summeZeigen() {
    const s = Math.round((zahlWert(e.menge) || 0) * (zahlWert(e.einzelpreis) || 0) * 100) / 100;
    summeEl.textContent = `${t("feld.summe")}: ${geld(s)}`;
  }
  e.menge.addEventListener("input", summeZeigen);
  e.einzelpreis.addEventListener("input", summeZeigen);

  function wegZeigen() {
    const stationen = [ich.vorgesetzter ? `${ich.vorgesetzter}` : null,
      ...stellen.filter((s) => s.art === "immer" || auswahl.has(s.id)).map((s) => s.name)].filter(Boolean);
    leeren(wegEl, stationen.length
      ? h("p.weg-hinweis", t("ausnahme.weg"), " ", h("span.weg", stationen.map((n, i) => [i ? h("span.pfeil", " → ") : null, h("strong", n)])),
        a?.status === "rueckfrage" ? h("small", { style: { display: "block" } }, t("ausnahme.weg_rueckfrage")) : null)
      : h("p.weg-hinweis.problem", t("ausnahme.kein_weg")));
  }

  const bedarf = stellen.filter((s) => s.art === "bedarf");
  const immer = stellen.filter((s) => s.art === "immer");
  const stellenBox = h("div.stellen-auswahl", bedarf.map((s) => h("label.stelle",
    h("input", { type: "checkbox", checked: auswahl.has(s.id), onchange: (ev) => { ev.target.checked ? auswahl.add(s.id) : auswahl.delete(s.id); wegZeigen(); } }),
    h("span", h("strong", s.name), s.hinweis ? h("small", s.hinweis) : null))));

  function daten() {
    return {
      titel: e.titel.value.trim(), beschreibung: e.beschreibung.value.trim(), bereich: e.bereich.value.trim(),
      kostenstelle_id: e.kostenstelle_id.value ? Number(e.kostenstelle_id.value) : null,
      menge: zahlWert(e.menge) ?? 0, einzelpreis: zahlWert(e.einzelpreis) ?? 0, laufende_kosten: zahlWert(e.laufende_kosten),
      lieferant: e.lieferant.value.trim(), begruendung: e.begruendung.value.trim(), wirtschaftlichkeit: e.wirtschaftlichkeit.value.trim(),
      fachstellen: [...auswahl],
    };
  }

  async function speichern() {
    fehlerEl.hidden = true;
    const d = daten();
    if (a) {
      await api(`ausnahmen/${a.id}`, { methode: "PUT", daten: d });
      return a.id;
    }
    const { id } = await api("ausnahmen", { methode: "POST", daten: d });
    a = { id, status: "entwurf", antragsteller_id: ich.id };
    history.replaceState(null, "", `#/ausnahme/${id}/bearbeiten`);
    return id;
  }

  function pflichtPruefen() {
    const d = daten();
    const fehlt = [];
    const pruefen = (name, leer, el) => {
      el.classList.toggle("fehlt", leer);
      if (leer) fehlt.push(t(`ausnahme.feld.${name}`));
    };
    pruefen("titel", !d.titel, e.titel);
    pruefen("kostenstelle_id", !d.kostenstelle_id, e.kostenstelle_id);
    pruefen("menge", !(d.menge > 0), e.menge);
    pruefen("einzelpreis", !(d.einzelpreis > 0), e.einzelpreis);
    pruefen("begruendung", !d.begruendung, e.begruendung);
    return fehlt;
  }

  function anhaengeZeigen() {
    leeren(anhangEl,
      anhangListe(anhaenge, { loeschbar: (x) => x.benutzer_id === ich.id, neuLaden: async () => { anhaenge = (await api(`ausnahmen/${a.id}`)).anhaenge; anhaengeZeigen(); } }),
      dateiAuswahl(async (dateien) => {
        try {
          await speichern(); // Anhänge brauchen einen gespeicherten Antrag
        } catch (err) {
          fehlerEl.textContent = err.message;
          fehlerEl.hidden = false;
          return;
        }
        for (const d of dateien) {
          try {
            await hochladen(a.id, d);
          } catch (err) {
            fehlerMelden(err);
          }
        }
        anhaenge = (await api(`ausnahmen/${a.id}`)).anhaenge;
        anhaengeZeigen();
      }));
  }

  const rueckfrage = a?.status === "rueckfrage" ? [...a.verlauf].reverse().find((v) => v.aktion === "rueckfrage") : null;
  leeren(wurzel,
    h("div.seitenkopf", h("div", h("h1", a ? `${aaNummer(a.id)} ${t("editor.bearbeiten")}` : t("ausnahme.neu")),
      h("p.untertitel", t("ausnahme.editor_hilfe")))),
    rueckfrage ? h("div.warnung", h("strong", t("ausnahme.rueckfrage_von", { name: rueckfrage.im_namen_von || rueckfrage.benutzer, station: rueckfrage.station })),
      h("p.notiz", rueckfrage.notiz)) : null,
    h("div.box", h("h2", t("ausnahme.schritt.was")),
      feld("titel", e.titel, true), feld("beschreibung", e.beschreibung),
      h("div.raster", feld("bereich", e.bereich), feld("kostenstelle_id", e.kostenstelle_id, true))),
    h("div.box", h("h2", t("ausnahme.schritt.kosten")),
      h("div.raster", feld("menge", e.menge, true), feld("einzelpreis", e.einzelpreis, true),
        feld("laufende_kosten", e.laufende_kosten, false, t("ausnahme.laufende_kosten_hilfe")), feld("lieferant", e.lieferant)),
      summeEl),
    h("div.box", h("h2", t("ausnahme.schritt.warum")),
      feld("begruendung", e.begruendung, true),
      feld("wirtschaftlichkeit", e.wirtschaftlichkeit, false, t("ausnahme.wirtschaftlichkeit_hilfe"))),
    h("div.box", h("h2", t("ausnahme.schritt.wer")),
      h("p.hinweis", t("ausnahme.stellen_hilfe")),
      bedarf.length ? stellenBox : h("p.leer", t("ausnahme.keine_bedarfsstellen")),
      immer.length ? h("p.hinweis", t("ausnahme.immer_dabei", { namen: immer.map((s) => s.name).join(", ") })) : null,
      wegEl),
    h("div.box", h("h2", t("ausnahme.anhaenge")), h("p.hinweis", t("ausnahme.anhaenge_hilfe")), anhangEl),
    fehlerEl,
    h("div.knopfreihe",
      h("button.knopf", {
        onclick: async () => {
          const fehlt = pflichtPruefen();
          if (fehlt.length) {
            fehlerEl.textContent = t("editor.fehlt", { felder: fehlt.join(", ") });
            fehlerEl.hidden = false;
            return;
          }
          try {
            const id = await speichern();
            const r = await uebermittelnDialog(await api(`ausnahmen/${id}`));
            if (r) location.hash = `#/ausnahme/${id}`;
          } catch (err) {
            fehlerEl.textContent = err.message;
            fehlerEl.hidden = false;
          }
        },
      }, t(a?.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln")),
      h("button.knopf.rand", {
        onclick: async () => {
          try {
            const id = await speichern();
            melden(t("editor.gespeichert"));
            location.hash = `#/ausnahme/${id}`;
          } catch (err) {
            fehlerEl.textContent = err.message;
            fehlerEl.hidden = false;
          }
        },
      }, t("editor.entwurf_speichern")),
      h("a.knopf-flach", { href: a ? `#/ausnahme/${a.id}` : "#/ausnahmen" }, t("allgemein.abbrechen")))
  );
  summeZeigen();
  wegZeigen();
  anhaengeZeigen();
}
