// Anforderungen: Listen (meine, genehmigen, ausführen, alle), Anlegen/Bearbeiten und Ansicht mit Verlauf

import { api, datumText, fehlerMelden, formularDialog, geld, h, leeren, melden, nummer, statusMarke, t, zeitText, zustand, bestaetigen } from "./basis.js";

// ---------------------------------------------------------------- Listen
const FILTER = {
  meine: ["", "entwurf", "genehmigung", "rueckfrage", "genehmigt", "erledigt", "abgelehnt"],
  genehmigen: null,
  ausfuehren: ["genehmigt", "erledigt"],
  alle: ["", "genehmigung", "rueckfrage", "genehmigt", "erledigt", "abgelehnt"],
};

export async function zeigeListe(wurzel, ansicht) {
  const ich = zustand.ich;
  let status = FILTER[ansicht]?.[0] ?? "";
  // Genehmiger sehen offene Aufgaben und darunter, was sie schon entschieden haben
  let unteransicht = ansicht;

  const kopf = h(
    "div.seitenkopf",
    h("h1", t(`liste.titel.${ansicht}`)),
    ansicht === "meine" && ich.kataloge.length ? h("a.knopf", { href: "#/anforderung/neu" }, t("liste.neu")) : null
  );
  const hinweis = ansicht === "meine" && !ich.kataloge.length ? h("div.info", t("liste.keine_kataloge")) : null;
  const reiter = h("div.reiter");
  const box = h("div.box");
  leeren(wurzel, kopf, hinweis, reiter, box);

  function reiterAufbauen() {
    if (ansicht === "genehmigen") {
      leeren(reiter, [["genehmigen", t("liste.offen")], ["entschieden", t("liste.entschieden")]].map(([wert, text]) =>
        h("a", { href: "#", class: unteransicht === wert ? "aktiv" : "", onclick: (e) => { e.preventDefault(); unteransicht = wert; laden(); } }, text)));
      return;
    }
    leeren(reiter, FILTER[ansicht].map((s) =>
      h("a", { href: "#", class: status === s ? "aktiv" : "", onclick: (e) => { e.preventDefault(); status = s; laden(); } },
        s ? t(`status.${s}`) : t("liste.alle_status"))));
  }

  async function laden() {
    reiterAufbauen();
    let zeilen;
    try {
      zeilen = await api(`anforderungen?ansicht=${unteransicht}${status && ansicht !== "genehmigen" ? `&status=${status}` : ""}`);
    } catch (e) {
      fehlerMelden(e);
      return;
    }
    if (!zeilen.length) {
      leeren(box, h("p.leer", t(`liste.leer.${unteransicht}`)));
      return;
    }
    const mitAntragsteller = ansicht !== "meine";
    leeren(
      box,
      h(
        "div.tabelle-rahmen",
        h(
          "table.tabelle",
          h("thead", h("tr",
            h("th", t("feld.nummer")), h("th", t("feld.anlass")), h("th.weg-schmal", t("feld.katalog")),
            mitAntragsteller ? h("th", t("feld.antragsteller")) : null,
            h("th.weg-schmal", t("feld.termin")), h("th.betrag", t("feld.summe")), h("th", t("feld.status")))),
          h("tbody", zeilen.map((z) =>
            h("tr.klickbar", { onclick: () => (location.hash = `#/anforderung/${z.id}`) },
              h("td", nummer(z.id)),
              h("td", z.anlass || h("span.gedimmt", t("liste.ohne_anlass")), z.vertretung ? h("span.marke-klein.gelb", t("liste.vertretung")) : null),
              h("td.weg-schmal", z.katalog),
              mitAntragsteller ? h("td", z.antragsteller) : null,
              h("td.weg-schmal", z.datum ? `${datumText(z.datum)}${z.uhrzeit ? `, ${z.uhrzeit}` : ""}` : "–"),
              h("td.betrag", geld(z.summe)),
              h("td", statusMarke(z.status), z.status === "genehmigung" && z.bearbeiter ? h("small.gedimmt", ` ${t("liste.bei", { name: z.bearbeiter })}`) : null)
            )))
        )
      )
    );
  }
  await laden();
}

// ---------------------------------------------------------------- Einzelne Anforderung
export async function zeigeAnforderung(wurzel, [id, modus]) {
  if (id === "neu") return zeigeEditor(wurzel, null);
  const a = await api(`anforderungen/${id}`);
  if (modus === "bearbeiten" && a.aktionen.includes("bearbeiten")) return zeigeEditor(wurzel, a);
  zeigeAnsicht(wurzel, a);
}

function kopfdaten(a) {
  const eintrag = (titel, wert) => h("div", h("dt", titel), h("dd", wert || "–"));
  return h(
    "dl.kopfdaten",
    eintrag(t("feld.anlass"), a.anlass),
    eintrag(t("feld.termin"), a.datum ? `${datumText(a.datum)}${a.uhrzeit ? `, ${a.uhrzeit}` : ""}` : ""),
    eintrag(t("feld.ort"), a.ort),
    eintrag(t("feld.katalog"), a.katalog),
    eintrag(t("feld.kostenstelle"), a.kostenstelle_nummer ? `${a.kostenstelle_nummer} ${a.kostenstelle_bezeichnung || ""}` : ""),
    eintrag(t("feld.antragsteller"), a.antragsteller),
    a.bemerkung ? eintrag(t("feld.bemerkung"), a.bemerkung) : null
  );
}

function positionstabelle(positionen, summe) {
  return h(
    "div.tabelle-rahmen",
    h(
      "table.tabelle",
      h("thead", h("tr", h("th", t("feld.produkt")), h("th.betrag", t("feld.menge")), h("th.betrag", t("feld.preis")), h("th.betrag", t("feld.betrag")))),
      h("tbody", positionen.map((p) =>
        h("tr", h("td", p.name), h("td.betrag", `${String(p.menge).replace(".", ",")} ${p.einheit}`), h("td.betrag", geld(p.preis)), h("td.betrag", geld(p.preis * p.menge))))),
      h("tfoot", h("tr", h("td", { colSpan: 3 }, t("feld.summe")), h("td.betrag", geld(summe))))
    )
  );
}

const FARBE = { uebermittelt: "blau", erneut_uebermittelt: "blau", selbst_genehmigt: "gruen", genehmigt: "gruen", befuerwortet: "gelb",
  rueckfrage: "gelb", abgelehnt: "rot", erledigt: "blau" };

function zeitleiste(a) {
  const punkte = a.verlauf.map((v) => {
    let titel = t(`verlauf.${v.aktion}`);
    if (v.weiter_an) titel += ` – ${t("verlauf.weiter_an", { name: v.weiter_an })}`;
    if (v.summe !== null && v.summe !== undefined && v.aktion.endsWith("uebermittelt")) titel += ` (${geld(v.summe)})`;
    const wer = v.im_namen_von ? t("verlauf.in_vertretung", { name: v.benutzer, fuer: v.im_namen_von }) : v.benutzer;
    return h(`li.${FARBE[v.aktion] || ""}`, h("strong", titel), h("small", `${wer} · ${zeitText(v.zeit)}`), v.notiz ? h("p.notiz", v.notiz) : null);
  });
  // offener nächster Schritt
  let offen = null;
  if (a.status === "genehmigung") offen = t("verlauf.wartet_auf", { name: a.bearbeiter });
  else if (a.status === "rueckfrage") offen = t("verlauf.wartet_antragsteller", { name: a.antragsteller });
  else if (a.status === "genehmigt") offen = t("verlauf.wartet_ausfuehrung", { katalog: a.katalog });
  if (offen) {
    const zusatz = a.status === "genehmigung" && a.bearbeiter_vertretung?.length ? t("verlauf.vertretung_aktiv", { namen: a.bearbeiter_vertretung.join(", ") }) : null;
    punkte.push(h("li.jetzt", h("strong", offen), zusatz ? h("small", zusatz) : null));
  }
  if (!punkte.length) return h("p.leer", t("verlauf.leer"));
  return h("ol.zeitleiste", punkte);
}

function zeigeAnsicht(wurzel, a) {
  const aktionen = aktionsleiste(a, (neu) => zeigeAnsicht(wurzel, neu));
  leeren(
    wurzel,
    h("div.seitenkopf",
      h("div", h("a.knopf-flach", { href: "javascript:history.back()" }, `← ${t("allgemein.zurueck")}`),
        h("h1", `${nummer(a.id)} · ${a.anlass || t("liste.ohne_anlass")} `, statusMarke(a.status)))),
    aktionen,
    h("div.spalten",
      h("div", h("div.box", h("h2", t("anforderung.angaben")), kopfdaten(a)), h("div.box", h("h2", t("anforderung.positionen")), positionstabelle(a.positionen, a.summe))),
      h("div.box", h("h2", t("anforderung.verlauf")), zeitleiste(a)))
  );
}

function aktionsleiste(a, neu) {
  const k = a.aktionen;
  if (!k.length) return null;
  const knoepfe = [];
  let text = null;
  const ausfuehren = async (pfad, daten) => {
    try {
      const ergebnis = await api(`anforderungen/${a.id}/${pfad}`, { methode: "POST", daten });
      zustand.zaehler?.();
      return ergebnis;
    } catch (e) {
      fehlerMelden(e);
      return null;
    }
  };
  if (k.includes("bearbeiten")) {
    if (a.status === "rueckfrage") text = t("anforderung.rueckfrage_text");
    knoepfe.push(h("a.knopf.rand", { href: `#/anforderung/${a.id}/bearbeiten` }, t("aktion.bearbeiten")));
    knoepfe.push(h("button.knopf", { onclick: () => uebermittelnDialog(a).then((r) => r && neu(r)) }, t(a.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln")));
  }
  if (k.includes("loeschen")) {
    knoepfe.push(h("button.knopf-flach.gefahr", {
      onclick: async () => {
        if (!(await bestaetigen(t("anforderung.loeschen_frage")))) return;
        try {
          await api(`anforderungen/${a.id}`, { methode: "DELETE" });
          location.hash = "#/anforderungen";
        } catch (e) {
          fehlerMelden(e);
        }
      },
    }, t("allgemein.loeschen")));
  }
  if (k.includes("genehmigen")) {
    const grenze = a.bearbeiter_grenze;
    const reicht = grenze === null || grenze === undefined || a.summe <= grenze + 1e-9;
    text = [
      a.vertretung_fuer ? h("strong", `${t("anforderung.du_vertrittst", { name: a.vertretung_fuer })} `) : null,
      reicht ? t("anforderung.grenze_reicht", { grenze: grenze === null ? t("benutzer.unbegrenzt") : geld(grenze) })
             : t("anforderung.grenze_reicht_nicht", { grenze: geld(grenze) }),
    ];
    const entscheiden = (aktion, pflicht) => {
      const name = aktion === "genehmigen" && !reicht ? t("aktion.befuerworten") : t(`aktion.${aktion}`);
      return formularDialog({
        titel: name,
        felder: [{ name: "notiz", label: t(pflicht ? "anforderung.begruendung" : "anforderung.notiz_optional"), typ: "textfeld", pflicht }],
        speichernText: name,
        speichern: async (w) => {
          if (pflicht && !w.notiz.trim()) throw new Error(t("fehler.notiz_fehlt"));
          return api(`anforderungen/${a.id}/entscheidung`, { methode: "POST", daten: { aktion, notiz: w.notiz } });
        },
      }).then((r) => {
        if (r && r.id) {
          zustand.zaehler?.();
          melden(t(`anforderung.erfolg.${aktion === "genehmigen" && r.status === "genehmigung" ? "befuerwortet" : aktion}`));
          neu(r);
        }
      });
    };
    knoepfe.push(h("button.knopf.gruen", { onclick: () => entscheiden("genehmigen", false) }, reicht ? t("aktion.genehmigen") : t("aktion.befuerworten")));
    knoepfe.push(h("button.knopf.rand", { onclick: () => entscheiden("rueckfrage", true) }, t("aktion.rueckfrage")));
    knoepfe.push(h("button.knopf.gefahr", { onclick: () => entscheiden("ablehnen", true) }, t("aktion.ablehnen")));
  }
  if (k.includes("erledigen")) {
    text = t("anforderung.erledigen_text");
    knoepfe.push(h("button.knopf.gruen", {
      onclick: () => formularDialog({
        titel: t("aktion.erledigen"),
        felder: [{ name: "notiz", label: t("anforderung.notiz_optional"), typ: "textfeld" }],
        speichernText: t("aktion.erledigen"),
        speichern: (w) => api(`anforderungen/${a.id}/erledigt`, { methode: "POST", daten: w }),
      }).then((r) => {
        if (r && r.id) {
          zustand.zaehler?.();
          melden(t("anforderung.erfolg.erledigt"));
          neu(r);
        }
      }),
    }, t("aktion.erledigen")));
  }
  return h("div.aktionsleiste", text ? h("p", text) : null, knoepfe);
}

async function uebermittelnDialog(a) {
  const felder = a.status === "rueckfrage" ? [{ name: "notiz", label: t("anforderung.antwort"), typ: "textfeld" }] : [];
  const ergebnis = await formularDialog({
    titel: t(a.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln"),
    felder: [{ typ: "element", name: "_info", element: h("p", t("anforderung.uebermitteln_frage", { summe: geld(a.summe) })), lesen: () => null }, ...felder],
    speichernText: t("aktion.uebermitteln"),
    speichern: (w) => api(`anforderungen/${a.id}/uebermitteln`, { methode: "POST", daten: { notiz: w.notiz || "" } }),
  });
  if (ergebnis && ergebnis.id) {
    zustand.zaehler?.();
    melden(t(ergebnis.status === "genehmigt" ? "anforderung.erfolg.selbst_genehmigt" : "anforderung.erfolg.uebermittelt"));
    return ergebnis;
  }
  return null;
}

// ---------------------------------------------------------------- Anlegen und Bearbeiten
async function zeigeEditor(wurzel, a) {
  const ich = zustand.ich;
  const kostenstellen = await api("kostenstellen");
  const kataloge = ich.kataloge;
  if (!kataloge.length) {
    leeren(wurzel, h("div.info", t("liste.keine_kataloge")));
    return;
  }
  let katalogId = a?.katalog_id ?? (kataloge.length === 1 ? kataloge[0].id : null);
  const mengen = new Map((a?.positionen || []).map((p) => [p.produkt_id, p.menge]));

  const feld = (name, el, pflicht = false) => h(`label.feld${pflicht ? ".pflicht" : ""}`, h("span", t(`feld.${name}`)), el);
  const eingaben = {
    anlass: h("input", { value: a?.anlass || "", maxLength: 200, placeholder: t("editor.anlass_beispiel") }),
    datum: h("input", { type: "date", value: a?.datum || "" }),
    uhrzeit: h("input", { type: "time", value: a?.uhrzeit || "" }),
    ort: h("input", { value: a?.ort || "", maxLength: 200, placeholder: t("editor.ort_beispiel") }),
    kostenstelle_id: h("select",
      h("option", { value: "" }, t("editor.bitte_waehlen")),
      kostenstellen.map((k) => h("option", { value: k.id, selected: k.id === (a ? a.kostenstelle_id : ich.kostenstelle_id) }, `${k.nummer} ${k.bezeichnung}`))),
    bemerkung: h("textarea", { maxLength: 2000, rows: 3 }, a?.bemerkung || ""),
  };
  const katalogAuswahl = h("select", {
    onchange: async (e) => {
      if (mengen.size && !(await bestaetigen(t("editor.katalog_wechseln"), t("editor.wechseln")))) {
        e.target.value = katalogId ?? "";
        return;
      }
      mengen.clear();
      katalogId = e.target.value ? Number(e.target.value) : null;
      produkteLaden();
    },
  }, katalogId === null ? h("option", { value: "" }, t("editor.bitte_waehlen")) : null,
  kataloge.map((k) => h("option", { value: k.id, selected: k.id === katalogId }, k.name)));

  const produktBox = h("div");
  const summeEl = h("div.summe");
  const fehlerEl = h("p.fehlertext", { hidden: true });
  let produkte = [];

  function summeZeigen() {
    let s = 0;
    for (const p of produkte) s += (mengen.get(p.id) || 0) * p.preis;
    summeEl.textContent = `${t("feld.summe")}: ${geld(Math.round(s * 100) / 100)}`;
  }

  async function produkteLaden() {
    if (!katalogId) {
      leeren(produktBox, h("p.leer", t("editor.erst_katalog")));
      summeEl.textContent = "";
      return;
    }
    const k = await api(`kataloge/${katalogId}`);
    produkte = k.produkte.filter((p) => p.aktiv);
    if (!produkte.length) {
      leeren(produktBox, h("p.leer", t("editor.keine_produkte")));
      summeZeigen();
      return;
    }
    leeren(
      produktBox,
      k.beschreibung ? h("p.hinweis", k.beschreibung) : null,
      h("div.tabelle-rahmen", h("table.tabelle",
        h("thead", h("tr", h("th", t("feld.produkt")), h("th.betrag", t("feld.preis")), h("th.betrag", t("feld.menge")), h("th.betrag", t("feld.betrag")))),
        h("tbody", produkte.map((p) => {
          const betrag = h("td.betrag", geld((mengen.get(p.id) || 0) * p.preis));
          const menge = h("input.menge", {
            type: "number", min: 0, step: "any", value: mengen.get(p.id) || "", placeholder: "0",
            oninput: (e) => {
              const m = Number(e.target.value.replace(",", ".")) || 0;
              if (m > 0) mengen.set(p.id, m);
              else mengen.delete(p.id);
              betrag.textContent = geld(m * p.preis);
              summeZeigen();
            },
          });
          return h("tr", h("td.produkt-name", p.name, p.beschreibung ? h("small", p.beschreibung) : null),
            h("td.betrag", `${geld(p.preis)} / ${p.einheit}`), h("td.betrag", menge), betrag);
        }))))
    );
    // Produkte, die es nicht mehr gibt, fallen aus der Anforderung
    for (const pid of [...mengen.keys()]) if (!produkte.some((p) => p.id === pid)) mengen.delete(pid);
    summeZeigen();
  }

  function daten() {
    return {
      katalog_id: katalogId,
      kostenstelle_id: eingaben.kostenstelle_id.value ? Number(eingaben.kostenstelle_id.value) : null,
      anlass: eingaben.anlass.value.trim(),
      datum: eingaben.datum.value || null,
      uhrzeit: eingaben.uhrzeit.value,
      ort: eingaben.ort.value.trim(),
      bemerkung: eingaben.bemerkung.value.trim(),
      positionen: [...mengen].map(([produkt_id, menge]) => ({ produkt_id, menge })),
    };
  }

  async function speichern() {
    fehlerEl.hidden = true;
    const d = daten();
    if (!d.katalog_id) throw new Error(t("editor.erst_katalog"));
    if (a) {
      await api(`anforderungen/${a.id}`, { methode: "PUT", daten: d });
      return a.id;
    }
    const { id } = await api("anforderungen", { methode: "POST", daten: d });
    a = { id, status: "entwurf" };
    history.replaceState(null, "", `#/anforderung/${id}/bearbeiten`);
    return id;
  }

  function pflichtPruefen() {
    const d = daten();
    const fehlt = [];
    for (const [name, el] of [["anlass", eingaben.anlass], ["datum", eingaben.datum], ["ort", eingaben.ort], ["kostenstelle", eingaben.kostenstelle_id]]) {
      const leer = name === "kostenstelle" ? !d.kostenstelle_id : !d[name];
      el.classList.toggle("fehlt", leer);
      if (leer) fehlt.push(t(`feld.${name}`));
    }
    if (!d.positionen.length) fehlt.push(t("editor.mindestens_ein_produkt"));
    return fehlt;
  }

  const knopfSpeichern = h("button.knopf.rand", {
    onclick: async () => {
      try {
        const id = await speichern();
        melden(t("editor.gespeichert"));
        location.hash = `#/anforderung/${id}`;
      } catch (e) {
        fehlerEl.textContent = e.message;
        fehlerEl.hidden = false;
      }
    },
  }, t("editor.entwurf_speichern"));
  const knopfUebermitteln = h("button.knopf", {
    onclick: async () => {
      const fehlt = pflichtPruefen();
      if (fehlt.length) {
        fehlerEl.textContent = t("editor.fehlt", { felder: fehlt.join(", ") });
        fehlerEl.hidden = false;
        return;
      }
      try {
        const id = await speichern();
        const aktuell = await api(`anforderungen/${id}`);
        const r = await uebermittelnDialog(aktuell);
        if (r) location.hash = `#/anforderung/${id}`;
      } catch (e) {
        fehlerEl.textContent = e.message;
        fehlerEl.hidden = false;
      }
    },
  }, t(a?.status === "rueckfrage" ? "aktion.erneut_uebermitteln" : "aktion.uebermitteln"));

  const rueckfrage = a?.status === "rueckfrage" ? [...a.verlauf].reverse().find((v) => v.aktion === "rueckfrage") : null;
  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", a ? `${nummer(a.id)} ${t("editor.bearbeiten")}` : t("editor.neu"))),
    rueckfrage ? h("div.warnung", h("strong", t("editor.rueckfrage_von", { name: rueckfrage.im_namen_von || rueckfrage.benutzer })), h("p.notiz", rueckfrage.notiz)) : null,
    h("div.box",
      h("h2", t("editor.schritt_katalog")),
      kataloge.length > 1 || !katalogId ? feld("katalog", katalogAuswahl, true) : h("p", h("strong", kataloge[0].name)),
      produktBox, summeEl),
    h("div.box",
      h("h2", t("editor.schritt_angaben")),
      h("div.raster", feld("anlass", eingaben.anlass, true), feld("datum", eingaben.datum, true), feld("uhrzeit", eingaben.uhrzeit),
        feld("ort", eingaben.ort, true), feld("kostenstelle", eingaben.kostenstelle_id, true)),
      feld("bemerkung", eingaben.bemerkung)),
    fehlerEl,
    h("div.knopfreihe", knopfUebermitteln, knopfSpeichern, h("a.knopf-flach", { href: a ? `#/anforderung/${a.id}` : "#/anforderungen" }, t("allgemein.abbrechen")))
  );
  await produkteLaden();
}
