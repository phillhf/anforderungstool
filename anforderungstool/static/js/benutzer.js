// Benutzer und Hierarchie: wer ist wessen Vorgesetzter, Freigabegrenze, Kostenstelle, Kataloge, Rechte

import { api, bestaetigen, fehlerMelden, formularDialog, geld, h, leeren, melden, t, zustand } from "./basis.js";

export async function zeigeBenutzer(wurzel, [ansicht = "liste"]) {
  const [liste, hinweise, kataloge, kostenstellen] = await Promise.all([api("benutzer"), api("hierarchie/hinweise"), api("kataloge"), api("kostenstellen")]);
  const neu = () => zeigeBenutzer(wurzel, [ansicht]);
  const dialog = (b) => benutzerDialog(b, liste, kataloge, kostenstellen).then((r) => r && (melden(t("allgemein.gespeichert")), neu()));

  const warnungen = hinweise.length ? h("div.warnung", h("strong", t("benutzer.hinweise_titel")),
    h("ul", hinweise.map((x) => h("li", t(`benutzer.hinweis.${x.code}`, { name: x.name, grenze: geld(x.grenze) }))))) : null;

  const reiter = h("div.reiter",
    h("a", { href: "#/benutzer", class: ansicht === "liste" ? "aktiv" : "" }, t("benutzer.liste")),
    h("a", { href: "#/benutzer/hierarchie", class: ansicht === "hierarchie" ? "aktiv" : "" }, t("benutzer.hierarchie")));

  const grenzeText = (g) => (g === null ? t("benutzer.unbegrenzt") : geld(g));
  let inhalt;
  if (ansicht === "hierarchie") {
    const kinder = new Map();
    for (const b of liste) {
      const k = b.vorgesetzter_id ?? 0;
      if (!kinder.has(k)) kinder.set(k, []);
      kinder.get(k).push(b);
    }
    const ast = (id) => {
      const unter = kinder.get(id) || [];
      if (!unter.length) return null;
      return h("ul.baum", unter.map((b) => h("li",
        h("span.person", h("a", { href: "#", onclick: (e) => { e.preventDefault(); dialog(b); } }, b.anzeigename),
          h("small.gedimmt", `${t("benutzer.grenze_kurz")}: ${grenzeText(b.grenze)}`),
          b.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv"))),
        ast(b.id))));
    };
    inhalt = h("div.box", h("p.hinweis", t("benutzer.hierarchie_hilfe")), ast(0) || h("p.leer", t("benutzer.leer")));
  } else {
    inhalt = h("div.box", h("div.tabelle-rahmen", h("table.tabelle",
      h("thead", h("tr", h("th", t("feld.name")), h("th", t("benutzer.vorgesetzter")), h("th.betrag", t("benutzer.grenze_kurz")),
        h("th.weg-schmal", t("feld.kostenstelle")), h("th.weg-schmal", t("benutzer.kataloge")), h("th.weg-schmal", t("benutzer.rechte")), h("th"))),
      h("tbody", liste.map((b) => h(`tr${b.aktiv ? "" : ".inaktiv"}`,
        h("td", h("strong", b.anzeigename), h("br"), h("small.gedimmt", `${b.benutzername}${b.email ? ` · ${b.email}` : ""}`),
          b.quelle === "ldap" ? h("span.marke-klein", "AD") : null, b.aktiv ? null : h("span.marke-klein.grau", t("allgemein.inaktiv"))),
        h("td", b.vorgesetzter || h("span.gedimmt", "–")),
        h("td.betrag", grenzeText(b.grenze)),
        h("td.weg-schmal", b.kostenstelle || "–"),
        h("td.weg-schmal", (b.kataloge.nutzer || []).map((k) => k.name).join(", ") || h("span.gedimmt", "–"),
          (b.kataloge.ausfuehrender || []).map((k) => h("span.marke-klein", t("benutzer.fuehrt_aus", { name: k.name }))),
          (b.kataloge.pfleger || []).map((k) => h("span.marke-klein.grau", t("benutzer.pflegt", { name: k.name })))),
        h("td.weg-schmal", b.rechte.map((r) => t(`recht.${r}`)).join(", ") || "–"),
        h("td.aktionen",
          h("button.knopf-flach", { onclick: () => dialog(b) }, t("allgemein.bearbeiten")),
          b.id !== zustand.benutzer.id ? h("button.knopf-flach.gefahr", {
            onclick: async () => {
              if (!(await bestaetigen(t("benutzer.loeschen_frage", { name: b.anzeigename })))) return;
              try {
                await api(`benutzer/${b.id}`, { methode: "DELETE" });
                neu();
              } catch (e) {
                fehlerMelden(e);
              }
            },
          }, t("allgemein.loeschen")) : null)))))));
  }

  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("benutzer.titel")), h("button.knopf", { onclick: () => dialog(null) }, t("benutzer.neu"))),
    warnungen,
    reiter,
    inhalt
  );
}

function benutzerDialog(b, liste, kataloge, kostenstellen) {
  const unbegrenzt = b ? b.grenze === null : false;
  const grenzeFeld = h("input", { type: "number", min: 0, step: "0.01", value: unbegrenzt ? "" : (b?.grenze ?? 0), disabled: unbegrenzt });
  const unbegrenztFeld = h("input", { type: "checkbox", checked: unbegrenzt, onchange: (e) => (grenzeFeld.disabled = e.target.checked) });
  const grenze = h("div.zeile", grenzeFeld, h("label.haken", unbegrenztFeld, h("span", t("benutzer.unbegrenzt"))));
  // als Vorgesetzte nicht wählbar: die Person selbst
  const vorgesetzte = liste.filter((x) => !b || x.id !== b.id);
  return formularDialog({
    titel: b ? t("benutzer.bearbeiten") : t("benutzer.neu"),
    gross: true,
    felder: [
      { typ: "ueberschrift", label: t("benutzer.abschnitt_person") },
      { name: "anzeigename", label: t("benutzer.anzeigename"), wert: b?.anzeigename, pflicht: true },
      { name: "benutzername", label: t("anmeldung.benutzername"), wert: b?.benutzername, pflicht: true },
      { name: "email", label: t("benutzer.email"), typ: "email", wert: b?.email, hilfe: t("benutzer.email_hilfe") },
      { name: "quelle", label: t("benutzer.quelle"), typ: "auswahl", wert: b?.quelle || "lokal",
        optionen: [["lokal", t("benutzer.quelle_lokal")], ["ldap", t("benutzer.quelle_ldap")]] },
      { name: "passwort", label: b ? t("benutzer.passwort_neu") : t("anmeldung.passwort"), typ: "password", hilfe: t("benutzer.passwort_hilfe"), attr: { autocomplete: "new-password" } },
      { typ: "ueberschrift", label: t("benutzer.abschnitt_freigabe") },
      { name: "vorgesetzter_id", label: t("benutzer.vorgesetzter"), typ: "auswahl", wert: b?.vorgesetzter_id ?? "",
        optionen: [["", t("benutzer.kein_vorgesetzter")], ...vorgesetzte.map((x) => [x.id, x.anzeigename])], hilfe: t("benutzer.vorgesetzter_hilfe") },
      { name: "grenze", label: t("benutzer.grenze"), typ: "element", element: grenze, hilfe: t("benutzer.grenze_hilfe"),
        lesen: () => (unbegrenztFeld.checked ? null : Number(grenzeFeld.value || 0)) },
      { name: "kostenstelle_id", label: t("benutzer.kostenstelle"), typ: "auswahl", wert: b?.kostenstelle_id ?? "",
        optionen: [["", "–"], ...kostenstellen.map((k) => [k.id, `${k.nummer} ${k.bezeichnung}`])], hilfe: t("benutzer.kostenstelle_hilfe") },
      { typ: "ueberschrift", label: t("benutzer.abschnitt_zugriff") },
      { name: "kataloge", label: t("benutzer.kataloge"), typ: "mehrfach", wert: (b?.kataloge.nutzer || []).map((k) => k.id),
        optionen: kataloge.map((k) => [k.id, k.name]), hilfe: t("benutzer.kataloge_hilfe") },
      { name: "rechte", label: t("benutzer.rechte"), typ: "mehrfach", wert: b?.rechte || [],
        optionen: [["verwalten", t("recht.verwalten")], ["statistik", t("recht.statistik")]], hilfe: t("benutzer.rechte_hilfe") },
      { name: "aktiv", label: t("benutzer.aktiv"), typ: "haken", wert: b ? !!b.aktiv : true },
    ],
    speichern: (w) => {
      const daten = {
        ...w,
        vorgesetzter_id: w.vorgesetzter_id ? Number(w.vorgesetzter_id) : null,
        kostenstelle_id: w.kostenstelle_id ? Number(w.kostenstelle_id) : null,
        passwort: w.passwort || null,
      };
      return b ? api(`benutzer/${b.id}`, { methode: "PUT", daten }) : api("benutzer", { methode: "POST", daten });
    },
  });
}
