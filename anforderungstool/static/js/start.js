// Startseite „Übersicht“: Was muss ich jetzt tun, was läuft bei mir? Es erscheint nur, was die Person betrifft.

import { api, darf, datumText, geld, h, leeren, nummer, seitMarke, statusMarke, t, terminMarke, zustand } from "./basis.js";

const MAX = 8; // je Kachel; der Rest ist über „alle anzeigen“ erreichbar

export async function zeigeStart(wurzel) {
  const ich = zustand.ich;
  const a = await api("aufgaben");
  const offenZahl = a.rueckfragen.length + a.genehmigen.length + a.ausfuehren.length;

  const kopf = h("div.seitenkopf",
    h("div", h("h1", t("start.titel", { name: ich.anzeigename })),
      h("p.untertitel", offenZahl === 1 ? t("start.offen_eins") : offenZahl ? t("start.offen", { n: offenZahl }) : t("start.nichts_offen"))),
    ich.kataloge.length ? h("a.knopf", { href: "#/anforderung/neu" }, t("liste.neu")) : null);

  const kacheln = [
    rueckfragen(a.rueckfragen),
    genehmigen(a.genehmigen),
    ausfuehren(a.ausfuehren),
    entwuerfe(a.entwuerfe),
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
    laufend(a.laufend));
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

function rueckfragen(liste) {
  if (!liste.length) return null;
  return kachel("rot", t("start.rueckfragen"), liste.length, t("start.rueckfragen_hilfe"),
    liste.slice(0, MAX).map((r) => h("li", h("a.aufgabe", { href: `#/anforderung/${r.id}/bearbeiten` },
      h("div.aufgabe-text",
        h("strong", `${nummer(r.id)} · ${r.anlass || t("liste.ohne_anlass")}`),
        h("small", r.im_namen_von ? t("start.frage_von_vertretung", { name: r.von, fuer: r.im_namen_von }) : t("start.frage_von", { name: r.von }), " · ", seitMarke(r.seit)),
        r.notiz ? h("p.notiz", r.notiz) : null),
      h("div.aufgabe-rechts", h("span.knopf.klein", t("start.beantworten")))))),
    liste.length > MAX ? { href: "#/anforderungen", text: t("start.alle_anzeigen") } : null);
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

function entwuerfe(liste) {
  if (!liste.length) return null;
  return kachel("grau", t("start.entwuerfe"), liste.length, t("start.entwuerfe_hilfe"),
    liste.slice(0, MAX).map((z) => zeile(`#/anforderung/${z.id}`,
      `${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`, [t("start.angelegt"), " ", seitMarke(z.erstellt)], h("span.betrag", geld(z.summe)))),
    liste.length > MAX ? { href: "#/anforderungen", text: t("start.alle_anzeigen") } : null);
}

// ---------------------------------------------------------------- Was läuft bei mir?
function laufend(liste) {
  if (!liste.length) return null;
  return h("div.box",
    h("div.box-kopf", h("h2", t("start.laufend")), h("a.knopf-flach", { href: "#/anforderungen" }, t("start.alle_meine"))),
    h("ul.aufgaben", liste.map((z) => zeile(`#/anforderung/${z.id}`,
      `${nummer(z.id)} · ${z.anlass || t("liste.ohne_anlass")}`,
      [statusMarke(z.status), " ", wartetBei(z), " · ", seitMarke(z.seit)],
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
  if (!ich.kataloge.length) {
    return ich.genehmiger || ich.ausfuehrender || ich.pfleger || darf("verwalten") ? null : h("div.info", t("liste.keine_kataloge"));
  }
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

