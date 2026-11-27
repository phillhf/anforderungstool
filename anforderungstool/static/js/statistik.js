// Statistik: wer hat wie viel angefordert (Zeitraum, Person, Katalog, Kostenstelle)

import { api, fehlerMelden, geld, h, heute, leeren, t } from "./basis.js";

export async function zeigeStatistik(wurzel) {
  const filter = await api("statistik/filter");
  const jahr = heute().slice(0, 4);
  const von = h("input", { type: "date", value: `${jahr}-01-01` });
  const bis = h("input", { type: "date", value: heute() });
  const auswahl = (liste, text) => h("select", h("option", { value: "" }, t("statistik.alle")), liste.map((x) => h("option", { value: x.id }, text(x))));
  const person = auswahl(filter.benutzer, (b) => b.anzeigename);
  const katalog = auswahl(filter.kataloge, (k) => k.name);
  const ks = auswahl(filter.kostenstellen, (k) => `${k.nummer} ${k.bezeichnung}`);
  const ergebnis = h("div.box");
  const feld = (name, el) => h("label.feld", h("span", t(`statistik.${name}`)), el);

  async function laden() {
    const p = new URLSearchParams();
    if (von.value) p.set("von", von.value);
    if (bis.value) p.set("bis", bis.value);
    if (person.value) p.set("benutzer_id", person.value);
    if (katalog.value) p.set("katalog_id", katalog.value);
    if (ks.value) p.set("kostenstelle_id", ks.value);
    let s;
    try {
      s = await api(`statistik?${p}`);
    } catch (e) {
      fehlerMelden(e);
      return;
    }
    if (!s.zeilen.length) {
      leeren(ergebnis, h("p.leer", t("statistik.leer")));
      return;
    }
    const paar = (anzahl, summe) => [h("td.betrag", anzahl || 0), h("td.betrag", geld(summe || 0))];
    leeren(ergebnis, h("div.tabelle-rahmen", h("table.tabelle",
      h("thead",
        h("tr", h("th"), h("th.betrag", { colSpan: 2 }, t("statistik.gesamt")), h("th.betrag", { colSpan: 2 }, t("statistik.genehmigt")),
          h("th.betrag", { colSpan: 2 }, t("statistik.abgelehnt")), h("th.betrag", { colSpan: 2 }, t("statistik.offen"))),
        h("tr", h("th", t("feld.antragsteller")), [1, 2, 3, 4].map(() => [h("th.betrag", t("statistik.anzahl")), h("th.betrag", t("statistik.summe"))]))),
      h("tbody", s.zeilen.map((z) => h("tr", h("td", z.name), paar(z.anzahl, z.summe), paar(z.anzahl_genehmigt, z.summe_genehmigt),
        paar(z.anzahl_abgelehnt, z.summe_abgelehnt), paar(z.anzahl_offen, z.summe_offen)))),
      h("tfoot", h("tr", h("td", t("statistik.summe_alle")), paar(s.gesamt.anzahl, s.gesamt.summe), paar(s.gesamt.anzahl_genehmigt, s.gesamt.summe_genehmigt),
        paar(s.gesamt.anzahl_abgelehnt, s.gesamt.summe_abgelehnt), paar(s.gesamt.anzahl_offen, s.gesamt.summe_offen)))
    )), h("p.hinweis", t("statistik.hilfe")));
  }

  for (const el of [von, bis, person, katalog, ks]) el.addEventListener("change", laden);
  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("statistik.titel"))),
    h("div.box", h("div.raster", feld("von", von), feld("bis", bis), feld("person", person), feld("katalog", katalog), feld("kostenstelle", ks))),
    ergebnis
  );
  await laden();
}
