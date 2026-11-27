// Vertretung: wer darf in meinem Namen freigeben (z. B. im Urlaub) – Admins sehen alle

import { api, darf, datumText, fehlerMelden, formularDialog, h, heute, leeren, t, zustand } from "./basis.js";

export async function zeigeVertretung(wurzel) {
  const admin = darf("verwalten");
  const [eigene, alle, benutzer] = await Promise.all([
    api("vertretungen"), admin ? api("vertretungen?alle=true") : Promise.resolve([]), api("benutzer/auswahl"),
  ]);
  const ich = zustand.benutzer.id;
  const neu = () => zeigeVertretung(wurzel);

  const dialog = (fuerAndere) => formularDialog({
    titel: t("vertretung.neu"),
    felder: [
      fuerAndere ? { name: "benutzer_id", label: t("vertretung.wer_abwesend"), typ: "auswahl", optionen: benutzer.map((b) => [b.id, b.anzeigename]) } : null,
      { name: "vertreter_id", label: t("vertretung.vertreter"), typ: "auswahl",
        optionen: benutzer.filter((b) => fuerAndere || b.id !== ich).map((b) => [b.id, b.anzeigename]) },
      { name: "von", label: t("vertretung.von"), typ: "date", wert: heute(), pflicht: true },
      { name: "bis", label: t("vertretung.bis"), typ: "date", wert: heute(), pflicht: true },
    ].filter(Boolean),
    speichern: (w) => api("vertretungen", { methode: "POST", daten: { ...w, benutzer_id: w.benutzer_id ? Number(w.benutzer_id) : null, vertreter_id: Number(w.vertreter_id) } }),
  }).then((r) => r && neu());

  const loeschen = async (v) => {
    try {
      await api(`vertretungen/${v.id}`, { methode: "DELETE" });
      neu();
    } catch (e) {
      fehlerMelden(e);
    }
  };

  const tabelle = (liste, mitPerson) => !liste.length ? h("p.leer", t("vertretung.leer")) : h("table.tabelle",
    h("thead", h("tr", mitPerson ? h("th", t("vertretung.abwesend")) : null, h("th", t("vertretung.vertreter")), h("th", t("vertretung.zeitraum")), h("th"))),
    h("tbody", liste.map((v) => h("tr",
      mitPerson ? h("td", v.benutzer) : null,
      h("td", v.vertreter),
      h("td", `${datumText(v.von)} – ${datumText(v.bis)}`, v.aktiv ? h("span.marke-klein.gelb", t("vertretung.aktiv")) : null),
      h("td.aktionen", admin || v.benutzer_id === ich ? h("button.knopf-flach.gefahr", { onclick: () => loeschen(v) }, t("allgemein.loeschen")) : null)))));

  const meine = eigene.filter((v) => v.benutzer_id === ich);
  const fuerAndere = eigene.filter((v) => v.vertreter_id === ich);
  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("vertretung.titel")), h("button.knopf", { onclick: () => dialog(false) }, t("vertretung.neu"))),
    h("div.box", h("h2", t("vertretung.meine")), h("p.hinweis", t("vertretung.hilfe")), tabelle(meine, false)),
    fuerAndere.length ? h("div.box", h("h2", t("vertretung.ich_vertrete")), tabelle(fuerAndere, true)) : null,
    admin ? h("div.box", h("div.box-kopf", h("h2", t("vertretung.alle")), h("button.knopf.rand", { onclick: () => dialog(true) }, t("vertretung.fuer_andere"))),
      tabelle(alle, true)) : null
  );
}
