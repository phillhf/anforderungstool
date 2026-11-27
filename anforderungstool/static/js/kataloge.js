// Kataloge: Übersicht, Produkte mit Preisen, Zuordnung (wer darf anfordern, pflegen, ausführen)

import { api, bestaetigen, darf, fehlerMelden, formularDialog, geld, h, leeren, melden, t } from "./basis.js";

export async function zeigeKataloge(wurzel, [id]) {
  if (id) return zeigeKatalog(wurzel, Number(id));
  const liste = await api("kataloge");
  const admin = darf("verwalten");
  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("katalog.titel")),
      admin ? h("button.knopf", { onclick: () => katalogDialog(null).then((r) => r && (location.hash = `#/kataloge/${r.id}`)) }, t("katalog.neu")) : null),
    h("div.box", !liste.length ? h("p.leer", t("katalog.leer")) : h("div.tabelle-rahmen", h("table.tabelle",
      h("thead", h("tr", h("th", t("feld.name")), h("th", t("katalog.produkte")), h("th", t("katalog.nutzer")), h("th", t("katalog.email")))),
      h("tbody", liste.map((k) => h(`tr.klickbar${k.aktiv ? "" : ".inaktiv"}`, { onclick: () => (location.hash = `#/kataloge/${k.id}`) },
        h("td", k.name, k.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv"))),
        h("td", k.produkte), h("td", k.nutzer), h("td", k.email || h("span.gedimmt", "–")))))))));
}

function katalogDialog(k) {
  return formularDialog({
    titel: k ? t("katalog.bearbeiten") : t("katalog.neu"),
    felder: [
      { name: "name", label: t("feld.name"), wert: k?.name, pflicht: true, attr: { maxLength: 100 } },
      { name: "beschreibung", label: t("katalog.beschreibung"), typ: "textfeld", wert: k?.beschreibung, hilfe: t("katalog.beschreibung_hilfe") },
      { name: "email", label: t("katalog.email"), wert: k?.email, hilfe: t("katalog.email_hilfe") },
      { name: "aktiv", label: t("katalog.aktiv"), typ: "haken", wert: k ? !!k.aktiv : true },
    ],
    speichern: (w) => (k ? api(`kataloge/${k.id}`, { methode: "PUT", daten: w }).then(() => ({ id: k.id })) : api("kataloge", { methode: "POST", daten: w })),
  });
}

function produktDialog(katalogId, p) {
  return formularDialog({
    titel: p ? t("produkt.bearbeiten") : t("produkt.neu"),
    felder: [
      { name: "name", label: t("feld.name"), wert: p?.name, pflicht: true, attr: { maxLength: 200 } },
      { name: "beschreibung", label: t("produkt.beschreibung"), wert: p?.beschreibung, attr: { maxLength: 1000 } },
      { name: "preis", label: t("produkt.preis"), typ: "number", wert: p?.preis ?? "", pflicht: true, attr: { min: 0, step: "0.01" } },
      { name: "einheit", label: t("produkt.einheit"), wert: p?.einheit ?? t("produkt.stueck"), pflicht: true, attr: { maxLength: 40 } },
      { name: "reihenfolge", label: t("produkt.reihenfolge"), typ: "number", wert: p?.reihenfolge ?? 0, hilfe: t("produkt.reihenfolge_hilfe") },
      { name: "aktiv", label: t("produkt.aktiv"), typ: "haken", wert: p ? !!p.aktiv : true },
    ],
    speichern: (w) => {
      const daten = { ...w, preis: w.preis ?? 0, reihenfolge: w.reihenfolge ?? 0 };
      return p ? api(`produkte/${p.id}`, { methode: "PUT", daten }) : api(`kataloge/${katalogId}/produkte`, { methode: "POST", daten });
    },
  });
}

async function zeigeKatalog(wurzel, id) {
  const k = await api(`kataloge/${id}`);
  const admin = darf("verwalten");
  const neu = () => zeigeKatalog(wurzel, id);

  const produkte = h("div.box",
    h("div.box-kopf", h("h2", t("katalog.produkte")),
      k.darf_pflegen ? h("button.knopf", { onclick: () => produktDialog(id, null).then((r) => r && neu()) }, t("produkt.neu")) : null),
    !k.produkte.length ? h("p.leer", t("katalog.keine_produkte")) : h("div.tabelle-rahmen", h("table.tabelle",
      h("thead", h("tr", h("th", t("feld.name")), h("th.betrag", t("feld.preis")), h("th", t("produkt.einheit")), h("th"))),
      h("tbody", k.produkte.map((p) => h(`tr${p.aktiv ? "" : ".inaktiv"}`,
        h("td.produkt-name", p.name, p.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv")), p.beschreibung ? h("small", p.beschreibung) : null),
        h("td.betrag", geld(p.preis)), h("td", p.einheit),
        h("td.aktionen", k.darf_pflegen ? [
          h("button.knopf-flach", { onclick: () => produktDialog(id, p).then((r) => r && neu()) }, t("allgemein.bearbeiten")),
          h("button.knopf-flach.gefahr", {
            onclick: async () => {
              if (!(await bestaetigen(t("produkt.loeschen_frage", { name: p.name })))) return;
              try {
                await api(`produkte/${p.id}`, { methode: "DELETE" });
                neu();
              } catch (e) {
                fehlerMelden(e);
              }
            },
          }, t("allgemein.loeschen")),
        ] : null)))))));

  let zuordnung = null;
  if (admin) {
    const benutzer = await api("benutzer/auswahl");
    const name = (bid) => benutzer.find((b) => b.id === bid)?.anzeigename || `#${bid}`;
    const zeile = (rolle) => h("tr",
      h("th", t(`katalog.rolle.${rolle}`), h("br"), h("small.gedimmt", t(`katalog.rolle_hilfe.${rolle}`))),
      h("td", k.zuordnung[rolle].length ? k.zuordnung[rolle].map(name).join(", ") : h("span.gedimmt", t("katalog.niemand"))));
    zuordnung = h("div.box",
      h("div.box-kopf", h("h2", t("katalog.zuordnung")),
        h("button.knopf.rand", {
          onclick: () => formularDialog({
            titel: t("katalog.zuordnung"),
            gross: true,
            felder: ["nutzer", "pfleger", "ausfuehrender"].map((rolle) => ({
              name: rolle, label: t(`katalog.rolle.${rolle}`), typ: "mehrfach", wert: k.zuordnung[rolle], hilfe: t(`katalog.rolle_hilfe.${rolle}`),
              optionen: benutzer.map((b) => [b.id, `${b.anzeigename} (${b.benutzername})`]),
            })),
            speichern: (w) => api(`kataloge/${id}/zuordnung`, { methode: "PUT", daten: w }),
          }).then((r) => r && (melden(t("allgemein.gespeichert")), neu())),
        }, t("allgemein.bearbeiten"))),
      h("table.tabelle", h("tbody", ["nutzer", "pfleger", "ausfuehrender"].map(zeile))));
  }

  leeren(
    wurzel,
    h("div.seitenkopf",
      h("div", h("a.knopf-flach", { href: "#/kataloge" }, `← ${t("katalog.titel")}`),
        h("h1", k.name, k.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv")))),
      admin ? h("div.knopfreihe",
        h("button.knopf.rand", { onclick: () => katalogDialog(k).then((r) => r && neu()) }, t("katalog.bearbeiten")),
        h("button.knopf-flach.gefahr", {
          onclick: async () => {
            if (!(await bestaetigen(t("katalog.loeschen_frage", { name: k.name })))) return;
            try {
              await api(`kataloge/${id}`, { methode: "DELETE" });
              location.hash = "#/kataloge";
            } catch (e) {
              fehlerMelden(e);
            }
          },
        }, t("allgemein.loeschen"))) : null),
    k.beschreibung || k.email ? h("div.info", k.beschreibung ? h("div", k.beschreibung) : null,
      k.email ? h("div", h("small", `${t("katalog.email")}: ${k.email}`)) : null) : null,
    produkte,
    zuordnung
  );
}
