/* Governance Tower — interface à panel unique (GT-M5).
 *
 * Règles de ce fichier :
 * - rendu exclusivement par createElement / textContent / setAttribute ;
 *   aucune chaîne n'est jamais interprétée comme du balisage ou du code ;
 * - aucun jeton, aucune clé, aucun stockage navigateur : l'historique vit en
 *   mémoire le temps de la session ;
 * - l'interface présente la réponse de Sentinel sans la recalculer ; une
 *   section illisible est signalée comme telle, jamais affichée comme vide ;
 * - aucune action opérationnelle : Sentinel observe et propose.
 */
"use strict";

(function () {
  const DELAI_MS = 20000;
  const MAX_QUESTION = 2000;
  const URL_STATUT = "/api/status";
  const URL_QUESTION = "/api/sentinel/ask";
  const URL_APERCU = "/sample_run.json";

  // ── Vocabulaires (libellés lisibles, valeurs brutes conservées) ───────────

  const DISPONIBILITE = {
    AVAILABLE: { libelle: "Disponible", ton: "ok" },
    STALE: { libelle: "Périmé", ton: "stale" },
    NOT_AVAILABLE: { libelle: "Indisponible", ton: "ko" },
    DENIED: { libelle: "Refusé", ton: "ko" },
    RATE_LIMITED: { libelle: "Quota atteint", ton: "ko" },
    ERROR: { libelle: "Erreur", ton: "ko" },
    UNKNOWN: { libelle: "Inconnu", ton: "unknown" },
  };

  const STATUT_CONSTAT = {
    OBSERVED: { ton: "ok", aide: "Observé : appuyé par au moins une preuve citée dans ce run" },
    INFERRED: { ton: "accent", aide: "Déduit : interprétation de preuves, pas une observation directe" },
    PROPOSED: { ton: "accent", aide: "Proposé : suggestion, sans valeur de constat" },
    NOT_PROVEN: { ton: "unknown", aide: "Non prouvé : les preuves ne suffisent pas à l'affirmer" },
  };

  const CLASSIFICATION = {
    ALIGNED: { libelle: "Aligné — GitHub et VPS concordent", ton: "ok" },
    EXPECTED_PINNED_RUNTIME: { libelle: "Runtime volontairement épinglé, attendu", ton: "ok" },
    POSSIBLE_DRIFT: { libelle: "Dérive possible — à vérifier par l'opérateur", ton: "stale" },
    STALE: { libelle: "Donnée périmée — comparaison non concluante", ton: "stale" },
    INSUFFICIENT_EVIDENCE: { libelle: "Preuves insuffisantes — aucune conclusion", ton: "unknown" },
    VIOLATION_PROVEN: { libelle: "Violation prouvée", ton: "ko" },
  };

  const SEVERITE = {
    INFO: { libelle: "Information", ton: "unknown" },
    NOTICE: { libelle: "À noter", ton: "accent" },
    WARNING: { libelle: "Avertissement", ton: "stale" },
    CRITICAL: { libelle: "Critique", ton: "ko" },
  };

  const NOM_SOURCE = { GITHUB: "GitHub", HOST: "VPS", DECLARED_REFERENCE: "Référence déclarée" };

  const ERREURS_HTTP = {
    400: "Requête invalide : la question n'a pas été comprise par le serveur.",
    403: "Requête refusée par le serveur (origine ou en-tête non admis).",
    413: "Question trop longue pour le serveur.",
    415: "Format de requête non accepté par le serveur.",
    429: "Trop de requêtes : patientez quelques instants avant de réessayer.",
    500: "Erreur interne du serveur : aucune réponse exploitable.",
  };

  // ── Utilitaires DOM sûrs ──────────────────────────────────────────────────

  let compteurIds = 0;
  function nouvelId(prefixe) {
    compteurIds += 1;
    return prefixe + "-" + compteurIds;
  }

  /** Crée un élément ; `texte` passe toujours par textContent. */
  function el(tag, options, enfants) {
    const noeud = document.createElement(tag);
    const opts = options || {};
    if (opts.classe) noeud.className = opts.classe;
    if (opts.texte !== undefined && opts.texte !== null) noeud.textContent = String(opts.texte);
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach(function (nom) {
        const valeur = opts.attrs[nom];
        if (valeur !== undefined && valeur !== null) noeud.setAttribute(nom, String(valeur));
      });
    }
    (enfants || []).forEach(function (enfant) {
      if (enfant === null || enfant === undefined) return;
      noeud.appendChild(typeof enfant === "string" ? document.createTextNode(enfant) : enfant);
    });
    return noeud;
  }

  function vider(noeud) {
    while (noeud.firstChild) noeud.removeChild(noeud.firstChild);
  }

  function estObjet(v) {
    return v !== null && typeof v === "object" && !Array.isArray(v);
  }

  function texteOuInconnu(v, inconnu) {
    return typeof v === "string" && v.length > 0 ? v : inconnu;
  }

  /** Horodatage exact conservé : valeur brute affichée, sans conversion locale. */
  function horodatage(valeur, absent) {
    if (typeof valeur !== "string" || !valeur) return el("span", { classe: "vide", texte: absent });
    return el("time", { texte: valeur.replace("T", " ").replace(/\.\d+Z$/, "Z"), attrs: { datetime: valeur, title: valeur } });
  }

  function badge(texte, ton, aide, extra) {
    const attrs = Object.assign({}, extra || {});
    if (aide) attrs.title = aide;
    return el("span", { classe: "badge ton-" + ton + (attrs["data-claim"] ? " badge-claim" : ""), texte: texte, attrs: attrs });
  }

  function badgeConstat(statut) {
    const info = STATUT_CONSTAT[statut] || { ton: "unknown", aide: "Statut hors vocabulaire" };
    return badge(texteOuInconnu(statut, "STATUT INCONNU"), info.ton, info.aide, { "data-claim": statut });
  }

  /** Lien uniquement vers https://github.com/ ; tout autre locator reste du texte. */
  function locator(valeur) {
    if (typeof valeur !== "string" || !valeur) return el("span", { classe: "vide", texte: "non fourni" });
    if (valeur.indexOf("https://github.com/") === 0) {
      let sur = false;
      try {
        sur = new URL(valeur).origin === "https://github.com";
      } catch (e) {
        sur = false;
      }
      if (sur) {
        return el("a", { texte: valeur, attrs: { href: valeur, rel: "noopener noreferrer", target: "_blank" } });
      }
    }
    return el("code", { texte: valeur });
  }

  function definitions(paires) {
    const dl = el("dl", { classe: "dl" });
    paires.forEach(function (p) {
      if (!p) return;
      dl.appendChild(el("dt", { texte: p[0] }));
      const dd = el("dd");
      if (p[1] instanceof Node) dd.appendChild(p[1]);
      else dd.textContent = p[1] === null || p[1] === undefined ? "—" : String(p[1]);
      dl.appendChild(dd);
    });
    return dl;
  }

  function codeOuAbsent(v, absent) {
    return typeof v === "string" && v ? el("code", { texte: v }) : el("span", { classe: "vide", texte: absent });
  }

  // ── Références DOM ────────────────────────────────────────────────────────

  const $ = function (id) {
    return document.getElementById(id);
  };
  let fil, formulaire, champ, compteur, boutonEnvoyer, boutonAnnuler, messageFormulaire, banniere, ligneMode;

  // ── État de session (mémoire uniquement) ──────────────────────────────────

  const historique = [];
  let enCours = null;
  let donneesSynthetiquesVues = false;
  let sourcesDepuisRun = false;

  function majBanniere(demo) {
    if (demo) donneesSynthetiquesVues = true;
    banniere.hidden = !donneesSynthetiquesVues;
  }

  // ── Indicateurs de sources ────────────────────────────────────────────────

  function majSource(idNoeud, entree) {
    const noeud = $(idNoeud);
    if (!noeud) return;
    const etat = noeud.querySelector(".source-etat");
    const meta = noeud.querySelector(".source-meta");
    if (!estObjet(entree)) {
      noeud.setAttribute("data-ton", "unknown");
      etat.textContent = "Inconnu";
      meta.textContent = "Non communiqué par le serveur";
      noeud.removeAttribute("title");
      return;
    }
    const dispo = DISPONIBILITE[entree.availability] || { libelle: "Hors vocabulaire", ton: "unknown" };
    noeud.setAttribute("data-ton", dispo.ton);
    etat.textContent = dispo.libelle;
    vider(meta);
    meta.appendChild(document.createTextNode(texteOuInconnu(entree.provenance, "provenance inconnue") + " · "));
    meta.appendChild(horodatage(entree.collected_at_utc, "jamais collecté"));
    if (typeof entree.detail === "string" && entree.detail) {
      meta.appendChild(document.createTextNode(" · " + entree.detail));
    }
    noeud.setAttribute("title", "Disponibilité brute : " + String(entree.availability));
  }

  function majSources(sources) {
    if (!Array.isArray(sources)) {
      majSource("source-github", null);
      majSource("source-host", null);
      return false;
    }
    const trouve = function (nom) {
      return sources.find(function (s) {
        return estObjet(s) && s.source === nom;
      });
    };
    majSource("source-github", trouve("GITHUB"));
    majSource("source-host", trouve("HOST"));
    return sources.some(function (s) {
      return estObjet(s) && s.provenance === "SYNTHETIC";
    });
  }

  async function chargerStatut() {
    try {
      const r = await fetch(URL_STATUT, { cache: "no-store", credentials: "same-origin", redirect: "error" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const s = await r.json();
      if (!estObjet(s)) throw new Error("statut illisible");
      const synth = majSources(s.sources);
      const demo = s.mode === "DEMO";
      majBanniere(demo || synth);
      const morceaux = ["Mode : " + (demo ? "DÉMO" : s.mode === "LIVE_READ" ? "lecture réelle (LIVE_READ)" : "inconnu")];
      if (typeof s.scenario === "string" && s.scenario) morceaux.push("scénario " + s.scenario);
      morceaux.push("capacité " + texteOuInconnu(s.capability, "inconnue"));
      morceaux.push("autorité opérationnelle " + texteOuInconnu(s.operational_authority, "inconnue"));
      ligneMode.textContent = morceaux.join(" · ");
    } catch (e) {
      // Un échec du statut n'efface pas les sources déjà décrites par un run.
      if (!sourcesDepuisRun) majSources(null);
      ligneMode.textContent = "Mode : inconnu — statut du serveur illisible (ce n'est pas un état vide).";
    }
  }

  // ── Rendu de la réponse ───────────────────────────────────────────────────

  function bloc(titre, contenu) {
    const idTitre = nouvelId("bloc");
    return el("section", { classe: "bloc", attrs: { "aria-labelledby": idTitre } }, [
      el("h3", { texte: titre, attrs: { id: idTitre } }),
      contenu,
    ]);
  }

  function illisible(nom) {
    return el("p", { classe: "alerte ton-unknown", texte: "Champ « " + nom + " » absent ou illisible — ce n'est pas une section vide." });
  }

  /** Retourne le tableau, ou null si le champ est absent / mal formé. */
  function tableau(obj, cle) {
    return estObjet(obj) && Array.isArray(obj[cle]) ? obj[cle] : null;
  }

  function detailPreuve(ev) {
    if (!estObjet(ev)) return el("p", { classe: "vide", texte: "Preuve citée mais absente du run." });
    return definitions([
      ["Identifiant", codeOuAbsent(ev.evidence_id, "inconnu")],
      ["Source", NOM_SOURCE[ev.source] || texteOuInconnu(ev.source, "inconnue")],
      ["Provenance", badge(texteOuInconnu(ev.provenance, "INCONNUE"), ev.provenance === "SYNTHETIC" ? "stale" : "accent")],
      ["Emplacement", locator(ev.locator)],
      ["Collectée", horodatage(ev.collected_at_utc, "inconnu")],
      ["Observée", horodatage(ev.observed_at_utc, "non fourni")],
      ["SHA source", codeOuAbsent(ev.source_sha, "non fourni")],
      ["SHA-256 contenu", codeOuAbsent(ev.content_sha256, "non fourni")],
      ev.note ? ["Note", ev.note] : null,
    ]);
  }

  /** Puces de preuve cliquables ; chacune déplie le détail de la preuve. */
  function pucesPreuve(ids, index) {
    const conteneur = el("div");
    if (!ids.length) return conteneur;
    const ligne = el("div", { classe: "puces-preuve", attrs: { role: "group", "aria-label": "Preuves citées" } });
    const zone = el("div");
    ids.forEach(function (id) {
      const idPanneau = nouvelId("preuve");
      const panneau = el("div", { classe: "detail-preuve", attrs: { id: idPanneau } }, [detailPreuve(index.get(id))]);
      panneau.hidden = true;
      const puce = el("button", {
        classe: "puce",
        texte: "preuve " + String(id),
        attrs: { type: "button", "aria-expanded": "false", "aria-controls": idPanneau },
      });
      puce.addEventListener("click", function () {
        const ouvert = puce.getAttribute("aria-expanded") === "true";
        puce.setAttribute("aria-expanded", ouvert ? "false" : "true");
        panneau.hidden = ouvert;
      });
      ligne.appendChild(puce);
      zone.appendChild(panneau);
    });
    conteneur.appendChild(ligne);
    conteneur.appendChild(zone);
    return conteneur;
  }

  function idsDe(evidences) {
    return (Array.isArray(evidences) ? evidences : [])
      .map(function (e) {
        return estObjet(e) ? e.evidence_id : null;
      })
      .filter(function (x) {
        return typeof x === "string";
      });
  }

  function rendreConstats(liste, index) {
    if (!liste) return illisible("statements");
    if (!liste.length) return el("p", { classe: "vide", texte: "Aucun constat formulé." });
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (s) {
      if (!estObjet(s)) return;
      const ids = Array.isArray(s.evidence_ids) ? s.evidence_ids : [];
      ul.appendChild(
        el("li", { classe: "carte" }, [
          el("div", { classe: "ligne-badges" }, [badgeConstat(s.claim_status)]),
          el("p", { texte: s.text }),
          pucesPreuve(ids, index),
        ])
      );
    });
    return ul;
  }

  function rendrePreuves(liste) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (ev) {
      ul.appendChild(el("li", { classe: "carte" }, [detailPreuve(ev)]));
    });
    return ul;
  }

  function rendreIncertitudes(liste) {
    if (!liste) return illisible("uncertainties");
    if (!liste.length) return el("p", { classe: "vide", texte: "Aucune incertitude déclarée par Sentinel." });
    return el(
      "ul",
      { classe: "liste-puces" },
      liste.map(function (u) {
        return el("li", { texte: u });
      })
    );
  }

  function valeurComparee(titre, v) {
    return el("div", {}, [
      el("span", { classe: "etiquette", texte: titre }),
      typeof v === "string" && v ? el("code", { texte: v }) : el("span", { classe: "vide", texte: "inconnu (non fourni)" }),
    ]);
  }

  function rendreEcarts(liste, index) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (d) {
      if (!estObjet(d)) return;
      const cls = CLASSIFICATION[d.classification] || { libelle: "Classification hors vocabulaire", ton: "unknown" };
      ul.appendChild(
        el("li", { classe: "carte" }, [
          el("p", { classe: "carte-titre", texte: d.subject }),
          el("div", { classe: "ligne-badges" }, [badge(cls.libelle, cls.ton, "Classification brute : " + String(d.classification))]),
          el("div", { classe: "comparaison" }, [valeurComparee("GitHub", d.github_value), valeurComparee("VPS", d.host_value)]),
          el("h4", { texte: "Attendu" }),
          el("p", { texte: d.expectation }),
          el("h4", { texte: "Explication" }),
          el("p", { texte: d.explanation }),
          pucesPreuve(idsDe(d.evidence), index),
        ])
      );
    });
    return ul;
  }

  function rendreCandidats(liste, index) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (f) {
      if (!estObjet(f)) return;
      const sev = SEVERITE[f.severity] || { libelle: "Sévérité inconnue", ton: "unknown" };
      const enfants = [
        el("p", { classe: "carte-titre", texte: f.title }),
        el("div", { classe: "ligne-badges" }, [
          badge(sev.libelle, sev.ton, "Sévérité brute : " + String(f.severity)),
          badgeConstat(f.claim_status),
          badge("Candidat — aucune autorité", "unknown", "Statut brut : " + String(f.status)),
        ]),
        el("h4", { texte: "Raison de la sévérité" }),
        el("p", { texte: f.severity_reason }),
        el("h4", { texte: "Impact" }),
        el("p", { texte: f.impact }),
      ];
      if (f.hypothesis) enfants.push(el("h4", { texte: "Hypothèse" }), el("p", { texte: f.hypothesis }));
      if (f.suggestion) enfants.push(el("h4", { texte: "Suggestion" }), el("p", { texte: f.suggestion }));
      enfants.push(pucesPreuve(idsDe(f.evidence), index));
      ul.appendChild(el("li", { classe: "carte" }, enfants));
    });
    return ul;
  }

  function listeTextes(titre, valeurs) {
    const items = Array.isArray(valeurs) ? valeurs : [];
    return [
      el("h4", { texte: titre }),
      items.length
        ? el(
            "ul",
            { classe: "liste-puces" },
            items.map(function (t) {
              return el("li", { texte: t });
            })
          )
        : el("p", { classe: "vide", texte: "Non précisé." }),
    ];
  }

  function rendrePropositions(liste) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (p) {
      if (!estObjet(p)) return;
      const enfants = [
        el("p", { classe: "carte-titre", texte: p.title }),
        el("p", {}, [el("span", { classe: "non-execute", texte: "Non exécutée — aucune autorité" })]),
        el("p", { texte: p.description }),
        definitions([
          ["Problème lié", codeOuAbsent(p.problem_ref, "non fourni")],
          ["Autorité", texteOuInconnu(p.authority, "inconnue")],
          ["Exécution", texteOuInconnu(p.execution, "inconnue")],
          ["Validation", texteOuInconnu(p.approval_path, "non précisée")],
        ]),
      ]
        .concat(listeTextes("Périmètre admis", p.allowed_scope))
        .concat(listeTextes("Preuves requises", p.required_evidence))
        .concat(listeTextes("Tests", p.tests))
        .concat(listeTextes("Périmètre interdit", p.forbidden_scope));
      ul.appendChild(el("li", { classe: "carte" }, enfants));
    });
    return ul;
  }

  function rendreRefus(liste) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (r) {
      if (!estObjet(r)) return;
      const enfants = [
        el("div", { classe: "ligne-badges" }, [badge(texteOuInconnu(r.code, "REFUS"), "ko")]),
        el("p", { texte: r.reason }),
      ];
      if (typeof r.quoted_request === "string") {
        enfants.push(citation(r.quoted_request, "Demande citée comme donnée, jamais exécutée"));
      }
      ul.appendChild(el("li", { classe: "carte" }, enfants));
    });
    return ul;
  }

  function citation(texte, legende) {
    return el("figure", { classe: "citation" }, [el("figcaption", { texte: legende }), el("blockquote", { texte: texte })]);
  }

  function rendreCitations(liste) {
    const ul = el("ul", { classe: "liste" });
    liste.forEach(function (q) {
      ul.appendChild(el("li", {}, [citation(String(q), "Contenu externe non fiable — cité comme donnée, jamais exécuté")]));
    });
    return ul;
  }

  function rendreTechnique(run) {
    const outils = Array.isArray(run.tool_calls) ? run.tool_calls : null;
    let blocOutils;
    if (!outils) blocOutils = el("span", { classe: "vide", texte: "non communiqué" });
    else if (!outils.length) blocOutils = el("span", { classe: "vide", texte: "aucun outil consulté" });
    else
      blocOutils = el(
        "ul",
        { classe: "liste-puces" },
        outils.map(function (t) {
          if (!estObjet(t)) return el("li", { texte: "entrée illisible" });
          const dispo = DISPONIBILITE[t.availability] || { libelle: String(t.availability), ton: "unknown" };
          return el("li", {}, [
            el("code", { texte: t.tool }),
            " — ",
            badge(dispo.libelle, dispo.ton),
            " ",
            horodatage(t.started_at_utc, "?"),
            " → ",
            horodatage(t.finished_at_utc, "?"),
            t.detail ? " · " + t.detail : "",
          ]);
        })
      );
    const shas = [];
    (Array.isArray(run.evidence) ? run.evidence : []).forEach(function (ev) {
      if (estObjet(ev) && ev.source_sha) shas.push(ev.evidence_id + " : " + ev.source_sha);
    });
    return el("details", { classe: "technique" }, [
      el("summary", { texte: "Détail technique du run" }),
      definitions([
        ["run_id", codeOuAbsent(run.run_id, "inconnu")],
        ["Intention", texteOuInconnu(run.intent, "inconnue")],
        ["Début", horodatage(run.started_at_utc, "inconnu")],
        ["Fin", horodatage(run.finished_at_utc, "inconnu")],
        ["Mode", texteOuInconnu(run.mode, "inconnu")],
        ["Reasoner", texteOuInconnu(run.reasoner, "inconnu")],
        ["Agent", texteOuInconnu(run.agent_id, "inconnu")],
        ["Capacité", texteOuInconnu(run.capability, "inconnue")],
        ["Autorité opérationnelle", texteOuInconnu(run.operational_authority, "inconnue")],
        ["Coût", run.cost === null || run.cost === undefined ? "non mesuré" : String(run.cost)],
        ["Schéma", texteOuInconnu(run.schema_version, "inconnu")],
        [
          "SHA cités",
          shas.length
            ? el(
                "ul",
                { classe: "liste-puces" },
                shas.map(function (s) {
                  return el("li", {}, [el("code", { texte: s })]);
                })
              )
            : el("span", { classe: "vide", texte: "aucun SHA source cité" }),
        ],
        ["Outils consultés", blocOutils],
      ]),
    ]);
  }

  /** Vérifie l'identité déclarée : une réponse qui revendique une autorité est rejetée. */
  function integrite(run) {
    if (!estObjet(run) || !estObjet(run.answer)) return "Réponse sans structure de run reconnaissable.";
    if (run.agent_id !== "SENTINEL-01" || run.capability !== "OBSERVE_ONLY" || run.operational_authority !== "DENIED") {
      return "Identité ou capacité inattendue : la réponse n'est pas affichée.";
    }
    return null;
  }

  function rendreRun(run) {
    const a = run.answer;
    const evidences = Array.isArray(run.evidence) ? run.evidence : null;
    const index = new Map();
    (evidences || []).forEach(function (ev) {
      if (estObjet(ev) && typeof ev.evidence_id === "string") index.set(ev.evidence_id, ev);
    });
    let synth =
      run.mode === "DEMO" ||
      (evidences || []).some(function (ev) {
        return estObjet(ev) && ev.provenance === "SYNTHETIC";
      });
    const racine = el("div");
    const entete = el("div", { classe: "ligne-badges" }, [
      badge(run.mode === "DEMO" ? "DÉMO" : texteOuInconnu(run.mode, "MODE INCONNU"), run.mode === "DEMO" ? "stale" : "accent"),
      badge("Intention " + texteOuInconnu(run.intent, "inconnue"), "unknown"),
    ]);
    racine.appendChild(el("span", { classe: "etiquette", texte: "Sentinel" }));
    racine.appendChild(entete);
    racine.appendChild(el("p", { classe: "resume", texte: texteOuInconnu(a.summary, "Résumé absent.") }));

    racine.appendChild(bloc("Constats", rendreConstats(tableau(a, "statements"), index)));
    racine.appendChild(
      bloc(
        "Preuves",
        evidences === null
          ? illisible("evidence")
          : evidences.length
            ? rendrePreuves(evidences)
            : el("p", { classe: "vide", texte: "Aucune preuve citée dans ce run." })
      )
    );
    racine.appendChild(bloc("Incertitudes", rendreIncertitudes(tableau(a, "uncertainties"))));

    const sections = [
      ["discrepancies", "Écarts GitHub / VPS", rendreEcarts],
      ["findings", "Constats candidats", rendreCandidats],
      ["proposals", "Propositions non exécutées", rendrePropositions],
      ["refusals", "Refus", rendreRefus],
      ["untrusted_quotes", "Contenu externe non fiable", rendreCitations],
    ];
    sections.forEach(function (s) {
      const liste = tableau(a, s[0]);
      // Le contrat sérialise toujours ces champs : leur absence est une anomalie visible.
      if (liste === null) {
        racine.appendChild(bloc(s[1], illisible(s[0])));
        return;
      }
      if (liste.length) racine.appendChild(bloc(s[1], s[2](liste, index)));
    });
    racine.appendChild(rendreTechnique(run));

    if (Array.isArray(run.sources)) {
      sourcesDepuisRun = true;
      if (majSources(run.sources)) synth = true;
    }
    majBanniere(synth);
    return racine;
  }

  // ── Échanges ──────────────────────────────────────────────────────────────

  function etatChargement() {
    return el("p", { classe: "etat etat-chargement", texte: "Sentinel consulte les sources en lecture seule…" });
  }

  function etatErreur(titre, detail, ton, reessayer) {
    const enfants = [el("span", { classe: "alerte-titre", texte: titre }), el("span", { texte: detail })];
    const boite = el("div", { classe: "alerte" + (ton ? " ton-" + ton : ""), attrs: { role: "alert" } }, enfants);
    if (reessayer) {
      const b = el("button", { classe: "btn-reessayer", texte: "Réessayer", attrs: { type: "button" } });
      b.addEventListener("click", reessayer);
      boite.appendChild(el("p", { classe: "etat" }, [b]));
    }
    return boite;
  }

  function creerEchange(question, etiquette) {
    const vide = $("fil-vide");
    if (vide) vide.remove();
    const reponse = el("div", { classe: "reponse" });
    const article = el("article", { classe: "echange", attrs: { "aria-label": "Échange " + (historique.length + 1) } }, [
      el("div", { classe: "question-bulle" }, [el("span", { classe: "etiquette", texte: etiquette }), el("span", { texte: question })]),
      reponse,
    ]);
    fil.appendChild(article);
    return { article: article, reponse: reponse };
  }

  function verrouiller(actif) {
    boutonEnvoyer.disabled = actif;
    boutonAnnuler.hidden = !actif;
    document.querySelectorAll(".raccourci").forEach(function (b) {
      b.disabled = actif;
    });
  }

  function afficherDans(echange, contenu) {
    vider(echange.reponse);
    echange.reponse.appendChild(contenu);
    echange.article.removeAttribute("aria-busy");
  }

  async function lireJson(r) {
    const brut = await r.text();
    try {
      return JSON.parse(brut);
    } catch (e) {
      return undefined;
    }
  }

  async function interroger(entree, echange) {
    if (enCours) return;
    const controleur = new AbortController();
    const requete = { controleur: controleur, delaiDepasse: false, minuterie: 0 };
    requete.minuterie = window.setTimeout(function () {
      requete.delaiDepasse = true;
      controleur.abort();
    }, DELAI_MS);
    enCours = requete;
    verrouiller(true);
    vider(echange.reponse);
    echange.reponse.appendChild(etatChargement());
    echange.article.setAttribute("aria-busy", "true");

    const relancer = function () {
      interroger(entree, echange);
    };

    try {
      const r = await fetch(URL_QUESTION, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-GT-Request": "1" },
        body: JSON.stringify({ question: entree.question, shortcut: entree.shortcut }),
        signal: controleur.signal,
        cache: "no-store",
        credentials: "same-origin",
        redirect: "error",
      });
      const donnees = await lireJson(r);
      if (!r.ok) {
        const code = estObjet(donnees) && typeof donnees.error === "string" ? donnees.error : "CODE_INCONNU";
        const msg = ERREURS_HTTP[r.status] || "Réponse inattendue du serveur.";
        const relancable = r.status === 429 || r.status >= 500;
        afficherDans(
          echange,
          etatErreur("Erreur " + r.status + " — " + code, msg, r.status === 429 ? "stale" : null, relancable ? relancer : null)
        );
        entree.resultat = { erreur: code, statut: r.status };
        return;
      }
      if (donnees === undefined) {
        afficherDans(echange, etatErreur("Réponse illisible", "Le serveur a répondu sans JSON exploitable.", null, relancer));
        entree.resultat = { erreur: "REPONSE_ILLISIBLE" };
        return;
      }
      const probleme = integrite(donnees);
      if (probleme) {
        afficherDans(echange, etatErreur("Réponse rejetée", probleme, null, null));
        entree.resultat = { erreur: "INTEGRITE" };
        return;
      }
      afficherDans(echange, rendreRun(donnees));
      entree.resultat = { run_id: donnees.run_id };
    } catch (e) {
      if (requete.delaiDepasse) {
        afficherDans(
          echange,
          etatErreur("Délai dépassé", "Aucune réponse en " + DELAI_MS / 1000 + " s. La requête a été abandonnée côté navigateur.", "stale", relancer)
        );
        entree.resultat = { erreur: "DELAI_DEPASSE" };
      } else if (controleur.signal.aborted) {
        afficherDans(echange, etatErreur("Requête annulée", "Vous avez annulé cette question.", "unknown", relancer));
        entree.resultat = { erreur: "ANNULEE" };
      } else {
        afficherDans(
          echange,
          etatErreur("Erreur réseau", "Le serveur est injoignable. Aucune donnée n'a été reçue (ce n'est pas une réponse vide).", null, relancer)
        );
        entree.resultat = { erreur: "RESEAU" };
      }
    } finally {
      window.clearTimeout(requete.minuterie);
      enCours = null;
      verrouiller(false);
    }
  }

  function poser(question, shortcut) {
    if (enCours) return;
    const entree = { question: question, shortcut: shortcut, resultat: null };
    const echange = creerEchange(question, shortcut ? "Raccourci" : "Vous");
    historique.push(entree);
    interroger(entree, echange);
  }

  async function chargerApercu() {
    const echange = creerEchange("Exemple SYNTHETIC local (sample_run.json) — pas une réponse de Sentinel.", "Aperçu");
    try {
      const r = await fetch(URL_APERCU, { cache: "no-store", credentials: "same-origin", redirect: "error" });
      const donnees = r.ok ? await lireJson(r) : undefined;
      const probleme = donnees === undefined ? "Exemple indisponible." : integrite(donnees);
      if (probleme) afficherDans(echange, etatErreur("Aperçu indisponible", probleme, "unknown", null));
      else afficherDans(echange, rendreRun(donnees));
    } catch (e) {
      afficherDans(echange, etatErreur("Aperçu indisponible", "Lecture de l'exemple impossible.", "unknown", null));
    }
  }

  // ── Formulaire ────────────────────────────────────────────────────────────

  function majCompteur() {
    const n = champ.value.length;
    compteur.textContent = n + " / " + MAX_QUESTION;
    compteur.setAttribute("data-limite", n >= MAX_QUESTION ? "true" : "false");
  }

  function soumettre() {
    messageFormulaire.textContent = "";
    if (enCours) {
      messageFormulaire.textContent = "Une question est déjà en cours : attendez la réponse ou annulez-la.";
      return;
    }
    const question = champ.value;
    if (!question.trim()) {
      messageFormulaire.textContent = "Saisissez une question ou choisissez un raccourci.";
      champ.focus();
      return;
    }
    if (question.length > MAX_QUESTION) {
      messageFormulaire.textContent = "Question trop longue (" + question.length + " / " + MAX_QUESTION + " caractères).";
      return;
    }
    champ.value = "";
    majCompteur();
    poser(question, null);
  }

  function initialiser() {
    fil = $("fil");
    formulaire = $("formulaire");
    champ = $("question");
    compteur = $("compteur");
    boutonEnvoyer = $("envoyer");
    boutonAnnuler = $("annuler");
    messageFormulaire = $("message-formulaire");
    banniere = $("banniere-demo");
    ligneMode = $("mode");

    formulaire.addEventListener("submit", function (e) {
      e.preventDefault();
      soumettre();
    });
    champ.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        soumettre();
      }
    });
    champ.addEventListener("input", majCompteur);
    boutonAnnuler.addEventListener("click", function () {
      if (enCours) enCours.controleur.abort();
    });
    document.querySelectorAll(".raccourci").forEach(function (b) {
      b.addEventListener("click", function () {
        messageFormulaire.textContent = "";
        poser(b.textContent.trim(), b.getAttribute("data-shortcut"));
      });
    });
    majCompteur();
    chargerStatut();
    if (window.location.hash === "#apercu") chargerApercu();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialiser);
  else initialiser();
})();
