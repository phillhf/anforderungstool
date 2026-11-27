// Einstellungen (nur Admins): Einrichtung, Adresse, E-Mail (SMTP) mit Erinnerungen, Active Directory, Sicherungen, Update

import { api, bestaetigen, fehlerMelden, formularDialog, h, leeren, melden, t, zeitText, zustand } from "./basis.js";

const REITER = ["allgemein", "email", "ad", "sicherung", "update"];

export async function zeigeEinstellungen(wurzel, [reiter = "allgemein"]) {
  if (!REITER.includes(reiter)) reiter = "allgemein";
  const e = await api("einstellungen");
  const neu = () => zeigeEinstellungen(wurzel, [reiter]);
  const inhalt = { allgemein, email, ad, sicherung, update }[reiter];
  leeren(
    wurzel,
    h("div.seitenkopf", h("h1", t("einstellungen.titel"))),
    h("div.reiter", REITER.map((r) => h("a", { href: `#/einstellungen/${r}`, class: r === reiter ? "aktiv" : "" }, t(`einstellungen.reiter.${r}`)))),
    await inhalt(e, neu)
  );
}

const feld = (label, el, hilfe) => h("label.feld", h("span", label), el, hilfe ? h("small", hilfe) : null);

async function speichernUnd(pfad, daten, neu, methode = "PUT") {
  try {
    await api(pfad, { methode, daten });
    melden(t("allgemein.gespeichert"));
    neu();
  } catch (err) {
    fehlerMelden(err);
  }
}

// ---------------------------------------------------------------- Allgemein mit Einrichtungs-Prüfung
async function allgemein(e, neu) {
  const [kostenstellen, kataloge, benutzer, hinweise] = await Promise.all([api("kostenstellen"), api("kataloge"), api("benutzer"), api("hierarchie/hinweise")]);
  const schritte = [
    ["email", !!(e.smtp.server && e.smtp.absender), "#/einstellungen/email"],
    ["adresse", !!e.adresse, null],
    ["kostenstellen", kostenstellen.length > 0, "#/kostenstellen"],
    ["kataloge", kataloge.some((k) => k.produkte > 0), "#/kataloge"],
    ["benutzer", benutzer.some((b) => b.vorgesetzter_id), "#/benutzer"],
    ["zuordnung", kataloge.some((k) => k.nutzer > 0), "#/kataloge"],
    ["hierarchie", hinweise.length === 0, "#/benutzer/hierarchie"],
  ];
  const offen = schritte.filter((s) => !s[1]).length;
  const einrichtung = h("div.box",
    h("h2", t("einrichtung.titel")),
    h("p.hinweis", offen ? t("einrichtung.offen", { anzahl: offen }) : t("einrichtung.fertig")),
    h("ul.zeitleiste", schritte.map(([name, ok, link]) => h(`li.${ok ? "gruen" : "jetzt"}`,
      h("strong", t(`einrichtung.${name}`)),
      h("small", ok ? t("einrichtung.erledigt") : t(`einrichtung.hilfe.${name}`)),
      !ok && link ? h("div", h("a", { href: link }, t("einrichtung.hin"))) : null))));

  const adresse = h("input", { value: e.adresse, placeholder: "https://anforderung.klinik.local:8480" });
  const inaktiv = h("input", { type: "number", min: 0.25, step: 0.25, value: e.sitzung_inaktiv_stunden });
  const adStunden = h("input", { type: "number", min: 1, step: 1, value: e.sitzung_ad_stunden });
  const sicherungen = h("input", { type: "number", min: 1, max: 365, value: e.sicherung_anzahl });
  return [einrichtung, h("div.box",
    h("h2", t("einstellungen.allgemein")),
    feld(t("einstellungen.adresse"), adresse, t("einstellungen.adresse_hilfe")),
    h("div.raster",
      feld(t("einstellungen.sitzung_inaktiv"), inaktiv, t("einstellungen.sitzung_inaktiv_hilfe")),
      feld(t("einstellungen.sitzung_ad"), adStunden, t("einstellungen.sitzung_ad_hilfe")),
      feld(t("einstellungen.sicherung_anzahl"), sicherungen, t("einstellungen.sicherung_anzahl_hilfe"))),
    h("button.knopf", {
      onclick: () => speichernUnd("einstellungen", {
        adresse: adresse.value, sitzung_inaktiv_stunden: Number(inaktiv.value), sitzung_ad_stunden: Number(adStunden.value),
        sicherung_anzahl: Number(sicherungen.value),
      }, neu),
    }, t("allgemein.speichern")))];
}

// ---------------------------------------------------------------- E-Mail
async function email(e, neu) {
  const s = e.smtp;
  const f = {
    server: h("input", { value: s.server, placeholder: "smtp.klinik.local" }),
    port: h("input", { type: "number", min: 1, max: 65535, value: s.port }),
    verschluesselung: h("select", ["starttls", "ssl", "keine"].map((v) => h("option", { value: v, selected: v === s.verschluesselung }, t(`email.verschluesselung_${v}`)))),
    benutzer: h("input", { value: s.benutzer, autocomplete: "off" }),
    passwort: h("input", { type: "password", placeholder: s.passwort_gesetzt ? t("email.passwort_gesetzt") : "", autocomplete: "new-password" }),
    absender: h("input", { type: "email", value: s.absender, placeholder: "anforderungen@klinik.local" }),
  };
  const ereignisse = Object.keys(e.mail_ereignisse).map((k) => [k, h("input", { type: "checkbox", checked: e.mail_ereignisse[k] })]);
  const erinnerungTage = h("input", { type: "number", min: 0, max: 30, step: 1, value: e.erinnerung_tage });
  const erinnerungOben = h("input", { type: "checkbox", checked: e.erinnerung_vorgesetzter });
  const mails = await api("mails");

  return [
    h("div.box",
      h("h2", t("email.server")),
      h("p.hinweis", t("email.hilfe")),
      h("div.raster",
        feld(t("email.server_name"), f.server), feld(t("email.port"), f.port), feld(t("email.verschluesselung"), f.verschluesselung),
        feld(t("email.benutzer"), f.benutzer, t("email.benutzer_hilfe")), feld(t("email.passwort"), f.passwort), feld(t("email.absender"), f.absender)),
      h("div.knopfreihe",
        h("button.knopf", {
          onclick: () => speichernUnd("einstellungen/smtp", {
            server: f.server.value.trim(), port: Number(f.port.value) || 587, verschluesselung: f.verschluesselung.value,
            benutzer: f.benutzer.value.trim(), passwort: f.passwort.value ? f.passwort.value : null, absender: f.absender.value.trim(),
          }, neu),
        }, t("allgemein.speichern")),
        h("button.knopf.rand", {
          onclick: () => formularDialog({
            titel: t("email.test"),
            felder: [{ name: "an", label: t("email.test_an"), typ: "email", pflicht: true }],
            speichernText: t("email.test_senden"),
            speichern: (w) => api("einstellungen/smtp/test", { methode: "POST", daten: w }),
          }).then((r) => r && melden(t("email.test_ok"))),
        }, t("email.test")))),
    h("div.box",
      h("h2", t("email.ereignisse")),
      ereignisse.map(([k, el]) => h("label.feld.haken", el, h("span", t(`email.ereignis.${k}`)))),
      h("button.knopf", { onclick: () => speichernUnd("einstellungen", { mail_ereignisse: Object.fromEntries(ereignisse.map(([k, el]) => [k, el.checked])) }, neu) },
        t("allgemein.speichern"))),
    h("div.box",
      h("h2", t("erinnerung.titel")),
      h("p.hinweis", t("erinnerung.hilfe")),
      feld(t("erinnerung.tage"), erinnerungTage, t("erinnerung.tage_hilfe")),
      h("label.feld.haken", erinnerungOben, h("span", t("erinnerung.vorgesetzter"))),
      h("button.knopf", {
        onclick: () => speichernUnd("einstellungen", { erinnerung_tage: Math.max(0, Math.round(Number(erinnerungTage.value) || 0)),
          erinnerung_vorgesetzter: erinnerungOben.checked }, neu),
      }, t("allgemein.speichern"))),
    h("div.box",
      h("h2", t("email.verlauf")),
      !mails.length ? h("p.leer", t("email.verlauf_leer")) : h("div.tabelle-rahmen", h("table.tabelle",
        h("thead", h("tr", h("th", t("email.zeit")), h("th", t("email.an")), h("th", t("email.betreff")), h("th", t("feld.status")), h("th"))),
        h("tbody", mails.map((m) => h("tr",
          h("td", zeitText(m.gesendet || m.erstellt)), h("td", m.an), h("td", m.betreff),
          h("td", h(`span.status.${m.status === "gesendet" ? "genehmigt" : m.status === "fehler" ? "abgelehnt" : "genehmigung"}`, t(`email.status.${m.status}`)),
            m.fehler ? h("small.gedimmt", { title: m.fehler }, ` ${m.fehler.slice(0, 80)}`) : null),
          h("td.aktionen", m.status === "fehler" ? h("button.knopf-flach", { onclick: () => speichernUnd(`mails/${m.id}/wiederholen`, undefined, neu, "POST") }, t("email.wiederholen")) : null))))))),
  ];
}

// ---------------------------------------------------------------- Active Directory
function ad(e, neu) {
  const l = e.ldap;
  const f = {
    aktiv: h("input", { type: "checkbox", checked: l.aktiv }),
    server: h("input", { value: l.server, placeholder: "ldaps://dc01.klinik.local" }),
    domaene: h("input", { value: l.domaene, placeholder: "klinik.local" }),
    basis_dn: h("input", { value: l.basis_dn, placeholder: "DC=klinik,DC=local" }),
    zugang_gruppe: h("input", { value: l.zugang_gruppe }),
  };
  const gruppen = l.gruppen.map((g) => ({ ...g }));
  const gruppenBox = h("div");
  const gruppenZeigen = () => leeren(gruppenBox,
    gruppen.map((g, i) => h("div.zeile", { style: { marginBottom: "6px" } },
      h("input", { type: "text", value: g.gruppe, placeholder: t("ad.gruppe"), oninput: (ev) => (g.gruppe = ev.target.value) }),
      h("select", { onchange: (ev) => (g.recht = ev.target.value) }, e.rechte.map((r) => h("option", { value: r, selected: r === g.recht }, t(`recht.${r}`)))),
      h("button.knopf-flach.gefahr", { onclick: () => { gruppen.splice(i, 1); gruppenZeigen(); } }, "✕"))),
    h("button.knopf-flach", { onclick: () => { gruppen.push({ gruppe: "", recht: e.rechte[0] }); gruppenZeigen(); } }, `+ ${t("ad.gruppe_neu")}`));
  gruppenZeigen();
  return h("div.box",
    h("h2", t("ad.titel")),
    h("p.hinweis", t("ad.hilfe")),
    h("label.feld.haken", f.aktiv, h("span", t("ad.aktiv"))),
    h("div.raster", feld(t("ad.server"), f.server, t("ad.server_hilfe")), feld(t("ad.domaene"), f.domaene), feld(t("ad.basis_dn"), f.basis_dn)),
    feld(t("ad.zugang_gruppe"), f.zugang_gruppe, t("ad.zugang_gruppe_hilfe")),
    h("h3", t("ad.gruppen")),
    h("p.hinweis", t("ad.gruppen_hilfe")),
    gruppenBox,
    h("div.knopfreihe", { style: { marginTop: "14px" } },
      h("button.knopf", {
        onclick: () => speichernUnd("einstellungen/ldap", {
          aktiv: f.aktiv.checked, server: f.server.value.trim(), domaene: f.domaene.value.trim(), basis_dn: f.basis_dn.value.trim(),
          zugang_gruppe: f.zugang_gruppe.value.trim(), gruppen: gruppen.filter((g) => g.gruppe.trim()),
        }, neu),
      }, t("allgemein.speichern")),
      h("button.knopf.rand", {
        onclick: () => formularDialog({
          titel: t("ad.test"),
          felder: [
            { name: "benutzername", label: t("anmeldung.benutzername"), pflicht: true },
            { name: "passwort", label: t("anmeldung.passwort"), typ: "password", pflicht: true },
          ],
          speichernText: t("ad.test"),
          speichern: (w) => api("einstellungen/ldap/test", { methode: "POST", daten: w }),
        }).then((r) => r && r.anzeigename && formularDialog({
          titel: t("ad.test_ok"),
          felder: [{ typ: "element", name: "_", lesen: () => null, element: h("div",
            h("p", `${r.anzeigename} · ${r.email || "–"}`),
            h("p", r.zugang ? t("ad.test_zugang") : t("ad.test_kein_zugang")),
            h("p", `${t("benutzer.rechte")}: ${r.rechte.map((x) => t(`recht.${x}`)).join(", ") || "–"}`),
            h("small.gedimmt", r.gruppen.join("; ")))}],
          speichernText: "OK",
          speichern: () => true,
        })),
      }, t("ad.test"))));
}

// ---------------------------------------------------------------- Sicherungen
async function sicherung(e, neu) {
  const liste = await api("sicherungen");
  return h("div.box",
    h("div.box-kopf", h("h2", t("sicherung.titel")),
      h("button.knopf", { onclick: () => speichernUnd("sicherungen", undefined, neu, "POST") }, t("sicherung.jetzt"))),
    h("p.hinweis", t("sicherung.hilfe")),
    !liste.length ? h("p.leer", t("sicherung.leer")) : h("table.tabelle",
      h("thead", h("tr", h("th", t("sicherung.datei")), h("th", t("sicherung.zeit")), h("th.betrag", t("sicherung.groesse")))),
      h("tbody", liste.map((s) => h("tr", h("td", s.name), h("td", new Date(s.zeit).toLocaleString("de-DE")), h("td.betrag", `${Math.ceil(s.groesse / 1024)} KB`))))));
}

// ---------------------------------------------------------------- Update
async function update() {
  const inhalt = h("div");
  const box = h("div.box",
    h("div.box-kopf", h("h2", t("update.titel")), h("button.knopf-flach", { onclick: () => pruefen(true) }, t("update.pruefen"))),
    inhalt);

  async function pruefen(neu) {
    leeren(inhalt, h("p.gedimmt", t("update.wird_geprueft")));
    let u;
    try {
      u = await api(`update${neu ? "?neu=true" : ""}`);
    } catch (err) {
      fehlerMelden(err);
      return;
    }
    if (u.fehler) return leeren(inhalt, h("p", t("update.version", { version: u.aktuell })), h("p.warnung", t("update.keine_verbindung")));
    leeren(inhalt,
      h("p", t("update.version", { version: u.aktuell })),
      u.verfuegbar ? [
        h("p.gut", h("strong", t("update.verfuegbar", { version: u.neueste }))),
        u.notizen ? h("pre.notizen", u.notizen) : null,
        u.installierbar
          ? h("div.knopfreihe", h("button.knopf", { onclick: () => installieren(u) }, t("update.installieren")),
            h("small.gedimmt", t("update.hinweis")))
          : h("p.hinweis", t("update.manuell"), " ", h("a", { href: u.url, target: "_blank", rel: "noopener" }, u.url)),
      ] : h("p.gut", t("update.aktuell")));
  }

  async function installieren(u) {
    if (!(await bestaetigen(t("update.wirklich", { version: u.neueste }), t("update.installieren")))) return;
    leeren(inhalt, h("p", t("update.laeuft")), h("progress"));
    try {
      await api("update", { methode: "POST" });
    } catch (err) {
      fehlerMelden(err);
      return pruefen(true);
    }
    // Warten, bis der Dienst mit der neuen Version antwortet; dann lädt die Seite neu (siehe app.js)
    const ende = Date.now() + 10 * 60 * 1000;
    while (Date.now() < ende) {
      await new Promise((r) => setTimeout(r, 5000));
      try {
        const r = await fetch("api/status", { cache: "no-store" });
        const { version } = await r.json();
        if (version && version !== zustand.version) return location.reload();
      } catch {}
    }
    leeren(inhalt, h("p.warnung", t("update.zeitueberschreitung")));
  }

  pruefen(false);
  return box;
}
