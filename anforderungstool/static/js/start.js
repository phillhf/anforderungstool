// Startseite „Übersicht“: Was muss ich jetzt tun, was läuft bei mir? Es erscheint nur, was die Person betrifft.

import { aaNummer, schritt } from "./ausnahmen.js";
import { api, darf, datumText, geld, h, leeren, nummer, seitMarke, statusMarke, t, terminMarke, zustand } from "./basis.js";

const MAX = 8; // je Kachel; der Rest ist über „alle anzeigen“ erreichbar

export async function zeigeStart(wurzel) {
  const ich = zustand.ich;
  const a = await api("aufgaben");
  const aa = a.ausnahmen;
  const offenZahl = a.rueckfragen.length + a.genehmigen.length + a.ausfuehren.length + aa.rueckfragen.length + aa.pruefen.length + aa.bestellen.length;

  const kopf = h("div.seitenkopf",
    h("div", h("h1", t("start.titel", { name: ich.anzeigename })),
      h("p.untertitel", offenZahl === 1 ? t("start.offen_eins") : offenZahl ? t("start.offen", { n: offenZahl }) : t("start.nichts_offen"))),
    h("div.knopfreihe",
      ich.kataloge.length ? h("a.knopf", { href: "#/anforderung/neu" }, t("liste.neu")) : null,
      h("a.knopf.rand", { href: "#/ausnahme/neu" }, `+ ${t("ausnahme.neu")}`)));

  const kacheln = [
    rueckfragen(a.rueckfragen, aa.rueckfragen),
    genehmigen(a.genehmigen),
    pruefen(aa.pruefen),
    ausfuehren(a.ausfuehren),
    bestellen(aa.bestellen),
    entwuerfe(a.entwuerfe, aa.entwuerfe),
  ].filter(Boolean);

  const nichtsZuTun = !kacheln.length ? h("div.kachel.ruhig",
    h("div.ruhig-symbol", "✓"),
    h("h2", t("start.nichts_titel")),
    h("p", t(ich.kataloge.length ? "start.nichts_text" : "start.nichts_text_ohne_katalog"))) : null;

  leeren(wurzel,
    kopf,
    verwaltung(a.verwaltung),
    hinweiseFuerMich(ich),
    h("div.kacheln", kacheln, nichtsZuTun),
    laufend(a.laufend, aa.laufend));
}

// ---------------------------------------------------------------- Kacheln „zu tun“
function kachel(art, titel, anzahl, hilfe, inhalt, mehr) {
  return h(`section.kachel.${art}`,
    h("div.kachel-kopf", h("h2", titel), h("span.kachel-zahl", anzahl)),
    hilfe ? h("p.hinweis", hilfe) : null,
    h("ul.aufgaben", inhalt),
    mehr ? h("a.kachel-mehr", { href: mehr.href }, mehr.text) : null);
}

function zeile(href, haupt, neben, rechts) {
  return h("li", h("a.aufgabe", { href },
    h("div.aufgabe-text", h("strong", haupt), neben ? h("small", neben) : null),
    rechts ? h("div.aufgabe-rechts", rechts) : null));
}

function rueckfragen(liste, ausnahmen) {
  const alle = [
    ...liste.map((r) => ({ ...r, href: `#/anforderung/${r.id}/bearbeiten`, titel: `${nummer(r.id)} · ${r.anlass || t("liste.ohne_anlass")}` })),
    ...ausnahmen.map((r) => ({ ...r, href: `#/ausnahme/${r.id}/bearbeiten`, titel: `${aaNummer(r.id)} · ${r.titel || t("liste.ohne_anlass")}` })),
  ];
  if (!alle.length) return null;
  return kachel("rot", t("start.rueckfragen"), alle.length, t("start.rueckfragen_hilfe"),
    alle.slice(0, MAX).map((r) => h("li", h("a.aufgabe", { href: r.href },
      h("div.aufgabe-text",
        h("strong", r.titel),
        h("small", r.im_namen_von ? t("start.frage_von_vertretung", { name: r.von, fuer: r.im_namen_von }) : t("start.frage_von", { name: r.von }),
          r.station ? ` (${r.station})` : "", " · ", seitMarke(r.seit)),
        r.notiz ? h("p.notiz", r.notiz) : null),
      h("div.aufgabe-rechts", h("span.knopf.klein", t("start.beantworten")))))),
    alle.length > MAX ? { href: "#/anforderungen", text: t("start.alle_anzeigen") } : null);
}

function pruefen(liste) {
  if (!liste.length) return null;
  return kachel("gelb", t("start.pruefen"), liste.length, t("start.pruefen_hilfe"),
    liste.slice(0, MAX).map((z) => zeile(`#/ausnahme/${z.id}`,
      `${aaNummer(z.id)} · ${z.titel || t("liste.ohne_anlass")}`,
      [z.antragsteller, " · ", t("ausnahme.als", { station: z.station }), " · ", seitMarke(z.seit),
        z.vertretung_fuer ? h("span.marke-klein.gelb", t("start.fuer", { name: z.vertretung_fuer })) : null],
      [h("span.betrag", geld(z.summe)), h("span.knopf.klein.gruen", t("start.pruefen_knopf"))])),
    liste.length > MAX ? { href: "#/ausnahmen/pruefen", text: t("start.alle_anzeigen") } : null);
}

function bestellen(liste) {
  if (!liste.length) return null;
  return kachel("blau", t("start.bestellen"), liste.length, t("start.bestellen_hilfe"),
    liste.slice(0, MAX).map((z) => zeile(`#/ausnahme/${z.id}`,
      `${aaNummer(z.id)} · ${z.titel || t("liste.ohne_anlass")}`,
      [z.antragsteller, " · ", z.bereich || "–", " · ", t("ausnahme.freigegeben"), " ", seitMarke(z.seit)],
      [h("span.betrag", geld(z.summe)), h("span.knopf.klein.gruen", t("ausnahme.melden.bestellt"))])),
    { href: "#/ausnahmen/bestellung", text: liste.length > MAX ? t("start.alle_anzeigen") : t("start.zur_bestellung") });
}

function genehmigen(liste) {
  if (!liste.length) return null;
  return kachel("gelb", t("start.genehmigen"), liste.length, t("start.genehmigen_hilfe"),
    liste.slice(0, MAX).map((z) => zeile(`#/anforderung/${z.id}`,
      `${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`,
      [z.antragsteller, " · ", seitMarke(z.seit), z.vertretung ? h("span.marke-klein.gelb", t("start.fuer", { name: z.bearbeiter })) : null],
      [h("span.betrag", geld(z.summe)), h("span.knopf.klein.gruen", t(z.endgueltig ? "aktion.genehmigen" : "aktion.befuerworten"))])),
    liste.length > MAX ? { href: "#/genehmigen", text: t("start.alle_anzeigen") } : null);
}

function ausfuehren(liste) {
  if (!liste.length) return null;
  return kachel("blau", t("start.ausfuehren"), liste.length, t("start.ausfuehren_hilfe"),
    liste.slice(0, MAX).map((z) => zeile(`#/anforderung/${z.id}`,
      [`${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`, terminMarke(z.datum)],
      `${z.datum ? datumText(z.datum) : "–"}${z.uhrzeit ? `, ${z.uhrzeit}` : ""} · ${z.ort || "–"} · ${z.katalog}`,
      h("span.knopf.klein.gruen", t("aktion.erledigen")))),
    { href: "#/ausfuehren", text: liste.length > MAX ? t("start.alle_anzeigen") : t("start.zur_liste") });
}

function entwuerfe(liste, ausnahmen) {
  const alle = [
    ...liste.map((z) => zeile(`#/anforderung/${z.id}`, `${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`,
      [t("start.angelegt"), " ", seitMarke(z.erstellt)], h("span.betrag", geld(z.summe)))),
    ...ausnahmen.map((z) => zeile(`#/ausnahme/${z.id}`, `${aaNummer(z.id)} · ${z.titel || t("liste.ohne_anlass")}`,
      [t("start.angelegt"), " ", seitMarke(z.erstellt)], h("span.betrag", geld(z.summe)))),
  ];
  if (!alle.length) return null;
  return kachel("grau", t("start.entwuerfe"), alle.length, t("start.entwuerfe_hilfe"), alle.slice(0, MAX),
    alle.length > MAX ? { href: "#/anforderungen", text: t("start.alle_anzeigen") } : null);
}

// ---------------------------------------------------------------- Was läuft bei mir?
function laufend(liste, ausnahmen) {
  if (!liste.length && !ausnahmen.length) return null;
  return h("div.box",
    h("div.box-kopf", h("h2", t("start.laufend")),
      h("div.knopfreihe", h("a.knopf-flach", { href: "#/anforderungen" }, t("start.alle_meine")),
        h("a.knopf-flach", { href: "#/ausnahmen/meine" }, t("start.alle_ausnahmen")))),
    h("ul.aufgaben",
      liste.map((z) => zeile(`#/anforderung/${z.id}`,
        `${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`,
        [statusMarke(z.status), " ", wartetBei(z), " · ", seitMarke(z.seit)],
        h("span.betrag", geld(z.summe)))),
      ausnahmen.map((z) => zeile(`#/ausnahme/${z.id}`,
        `${aaNummer(z.id)} · ${z.titel || t("liste.ohne_anlass")}`,
        [statusMarke(z.status), " ", schritt(z, "laufend")],
        h("span.betrag", geld(z.summe))))));
}

/** „bei Chef“, „Ausführung: Cafeteria“ … für eine Listenzeile */
export function wartetBei(z) {
  if (z.status === "genehmigung") return t("liste.bei", { name: z.bearbeiter });
  if (z.status === "rueckfrage") return t("liste.bei", { name: z.antragsteller });
  if (z.status === "genehmigt") return t("liste.bei_ausfuehrung", { katalog: z.katalog });
  return "";
}

// ---------------------------------------------------------------- Hinweise
function hinweiseFuerMich(ich) {
  // Ohne Katalog kann man trotzdem Ausnahmeanträge stellen – der Hinweis steht dann nur unter „Meine Anforderungen“
  if (!ich.kataloge.length) return null;
  // Kann eine Anforderung dieser Person überhaupt genehmigt werden?
  if (ich.grenze !== null && !ich.kette.length) return h("div.warnung", t("start.kein_vorgesetzter"));
  if (ich.kette.some((p) => p.aktiv === false)) return h("div.warnung", t("start.vorgesetzter_inaktiv"));
  return null;
}

function verwaltung(v) {
  if (!v) return null;
  const punkte = [
    v.mail_fehlt ? [t("start.admin.mail_fehlt"), "#/einstellungen/email"] : null,
    v.mail_fehler ? [t("start.admin.mail_fehler", { n: v.mail_fehler }), "#/einstellungen/email"] : null,
    v.adresse_fehlt ? [t("start.admin.adresse_fehlt"), "#/einstellungen"] : null,
    v.hierarchie ? [t("start.admin.hierarchie", { n: v.hierarchie }), "#/benutzer/hierarchie"] : null,
  ].filter(Boolean);
  if (!punkte.length) return null;
  return h("div.warnung", h("strong", t("start.admin.titel")),
    h("ul", punkte.map(([text, href]) => h("li", h("a", { href }, text)))));
}

