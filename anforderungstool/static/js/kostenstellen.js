// Kostenstellen: Liste mit Nummer und Bezeichnung

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, t } from "./basis.js";

export async function zeigeKostenstellen(wurzel) {
  const liste = await api("kostenstellen");
  const neu = () => zeigeKostenstellen(wurzel);
  const dialog = (k) => formularDialog({
    titel: k ? t("kostenstelle.bearbeiten") : t("kostenstelle.neu"),
    felder: [
      { name: "nummer", label: t("kostenstelle.nummer"), wert: k?.nummer, pflicht: true, attr: { maxLength: 40 } },
      { name: "bezeichnung", label: t("kostenstelle.bezeichnung"), wert: k?.bezeichnung, attr: { maxLength: 200 } },
      { name: "aktiv", label: t("kostenstelle.aktiv"), typ: "haken", wert: k ? !!k.aktiv : true },
    ],
    speichern: (w) => (k ? api(`kostenstellen/${k.id}`, { methode: "PUT", daten: w }) : api("kostenstellen", { methode: "POST", daten: w })),
  }).then((r) => r && neu());

  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("kostenstelle.titel")), h("button.knopf", { onclick: () => dialog(null) }, t("kostenstelle.neu"))),
    h("div.box",
      h("p.hinweis", t("kostenstelle.hilfe")),
      !liste.length ? h("p.leer", t("kostenstelle.leer")) : h("table.tabelle",
        h("thead", h("tr", h("th", t("kostenstelle.nummer")), h("th", t("kostenstelle.bezeichnung")), h("th"))),
        h("tbody", liste.map((k) => h(`tr${k.aktiv ? "" : ".inaktiv"}`,
          h("td", k.nummer, k.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv"))),
          h("td", k.bezeichnung),
          h("td.aktionen",
            h("button.knopf-flach", { onclick: () => dialog(k) }, t("allgemein.bearbeiten")),
            h("button.knopf-flach.gefahr", {
              onclick: async () => {
                if (!(await bestaetigen(t("kostenstelle.loeschen_frage", { nummer: k.nummer })))) return;
                try {
                  await api(`kostenstellen/${k.id}`, { methode: "DELETE" });
                  neu();
                } catch (e) {
                  fehlerMelden(e);
                }
              },
            }, t("allgemein.loeschen"))))))))
  );
}
