// Fachstellen für Ausnahmeanträge (nur Admins): anlegen, Mitglieder, „immer“ oder „bei Bedarf“, Reihenfolge

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, melden, t } from "./basis.js";

export async function zeigeFachstellen(wurzel) {
  const [stellen, benutzer] = await Promise.all([api("fachstellen"), api("benutzer/auswahl")]);
  const namen = new Map(benutzer.map((b) => [b.id, b.anzeigename]));
  const neu = () => zeigeFachstellen(wurzel);

  const dialog = (f) => formularDialog({
    titel: f ? t("fachstelle.bearbeiten") : t("fachstelle.neu"),
    gross: true,
    felder: [
      { name: "name", label: t("feld.name"), wert: f?.name, pflicht: true, attr: { maxLength: 100 } },
      { name: "art", label: t("fachstelle.art"), typ: "auswahl", wert: f?.art || "bedarf",
        optionen: [["bedarf", t("fachstelle.art_bedarf")], ["immer", t("fachstelle.art_immer")]], hilfe: t("fachstelle.art_hilfe") },
      { name: "hinweis", label: t("fachstelle.hinweis"), typ: "textfeld", wert: f?.hinweis, hilfe: t("fachstelle.hinweis_hilfe") },
      { name: "mitglieder", label: t("fachstelle.mitglieder"), typ: "mehrfach", wert: f?.mitglieder || [],
        optionen: benutzer.map((b) => [b.id, b.anzeigename]), hilfe: t("fachstelle.mitglieder_hilfe") },
      { name: "email", label: t("fachstelle.email"), typ: "text", wert: f?.email, hilfe: t("fachstelle.email_hilfe") },
      { name: "ausfuehrend", label: t("fachstelle.ausfuehrend"), typ: "haken", wert: f?.ausfuehrend, hilfe: t("fachstelle.ausfuehrend_hilfe") },
      { name: "aktiv", label: t("fachstelle.aktiv"), typ: "haken", wert: f ? f.aktiv : true },
    ],
    speichern: (w) => {
      const daten = { ...w, reihenfolge: f ? f.reihenfolge : (stellen.length + 1) * 10 };
      return f ? api(`fachstellen/${f.id}`, { methode: "PUT", daten }) : api("fachstellen", { methode: "POST", daten });
    },
  }).then((r) => r && neu());

  const verschieben = async (i, richtung) => {
    const ids = stellen.map((s) => s.id);
    [ids[i], ids[i + richtung]] = [ids[i + richtung], ids[i]];
    try {
      await api("fachstellen-reihenfolge", { methode: "PUT", daten: ids });
      neu();
    } catch (e) {
      fehlerMelden(e);
    }
  };

  const loeschen = async (f) => {
    if (!(await bestaetigen(t("fachstelle.loeschen_frage", { name: f.name })))) return;
    try {
      await api(`fachstellen/${f.id}`, { methode: "DELETE" });
      melden(t("allgemein.gespeichert"));
      neu();
    } catch (e) {
      fehlerMelden(e);
    }
  };

  // Beispielweg: so läuft ein Antrag, wenn alle „bei Bedarf“-Stellen angekreuzt sind
  const aktive = stellen.filter((s) => s.aktiv);
  const beispiel = aktive.length ? h("p.weg-hinweis", t("fachstelle.weg"), " ",
    h("span.weg", [h("span", t("ausnahme.vorgesetzter")), aktive.map((s) => [h("span.pfeil", " → "),
      h(s.art === "immer" ? "strong" : "span", s.name + (s.art === "bedarf" ? "*" : ""))])]),
    h("small.gedimmt", ` (${t("fachstelle.stern")})`)) : null;

  leeren(
    wurzel,
    h("div.seitenkopf",
      h("div", h("h1", t("fachstelle.titel")), h("p.untertitel", t("fachstelle.hilfe"))),
      h("button.knopf", { onclick: () => dialog(null) }, `+ ${t("fachstelle.neu")}`)),
    !stellen.length ? h("div.info", t("fachstelle.leer")) : null,
    beispiel,
    !aktive.some((s) => s.ausfuehrend) && stellen.length ? h("div.warnung", t("fachstelle.kein_ausfuehrender")) : null,
    stellen.length ? h("div.box", h("div.tabelle-rahmen", h("table.tabelle",
      h("thead", h("tr", h("th", t("fachstelle.reihenfolge")), h("th", t("feld.name")), h("th", t("fachstelle.art")),
        h("th", t("fachstelle.mitglieder")), h("th"))),
      h("tbody", stellen.map((f, i) => h(f.aktiv ? "tr" : "tr.inaktiv",
        h("td.aktionen", { style: { textAlign: "left" } },
          h("button.knopf-flach", { disabled: i === 0, title: t("fachstelle.hoch"), onclick: () => verschieben(i, -1) }, "↑"),
          h("button.knopf-flach", { disabled: i === stellen.length - 1, title: t("fachstelle.runter"), onclick: () => verschieben(i, 1) }, "↓")),
        h("td", h("strong", f.name), f.ausfuehrend ? h("span.marke-klein", t("fachstelle.bestellt")) : null,
          !f.aktiv ? h("span.marke-klein.grau", t("allgemein.inaktiv")) : null, f.hinweis ? h("small.gedimmt", { style: { display: "block" } }, f.hinweis) : null),
        h("td", t(f.art === "immer" ? "fachstelle.art_immer_kurz" : "fachstelle.art_bedarf_kurz")),
        h("td", f.mitglieder.length ? f.mitglieder.map((m) => namen.get(m) || "?").join(", ") : h("span.fehlertext", t("fachstelle.keine_mitglieder"))),
        h("td.aktionen",
          h("button.knopf-flach", { onclick: () => dialog(f) }, t("allgemein.bearbeiten")),
          h("button.knopf-flach.gefahr", { onclick: () => loeschen(f) }, t("allgemein.loeschen")))))))))
      : null
  );
}
