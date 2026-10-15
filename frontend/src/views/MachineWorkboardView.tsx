import React, { useMemo, useState } from "react";
import { STATUS_LABELS, WORK_ITEMS, WORKBOARD_REVIEWED_AT, WORKBOARD_SOURCE_SHA, type WorkStatus } from "../lib/machineWorkboardRegister";
import "./machine-workboard.css";

const github = "https://github.com/3a7i3/crypto-ia-terminal";
const statuses = Object.keys(STATUS_LABELS) as WorkStatus[];
const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const reviewedDate = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short", timeZone: "UTC" }).format(new Date(WORKBOARD_REVIEWED_AT));
const Dot: React.FC<{ status: WorkStatus }> = ({ status }) => <span className={`wb-status wb-${status}`}><i aria-hidden="true" />{STATUS_LABELS[status]}</span>;

export const MachineWorkboardView: React.FC = () => {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<WorkStatus | "all">("all");
  const [area, setArea] = useState("all");
  const areas = [...new Set(WORK_ITEMS.map(item => item.area))];
  const rows = useMemo(() => WORK_ITEMS.filter(item =>
    (status === "all" || status === item.status) && (area === "all" || area === item.area) &&
    normalize(`${item.id} ${item.title} ${item.scope} ${item.evidence} ${item.next} ${item.issue} ${item.pr ?? ""}`).includes(normalize(query)),
  ), [query, status, area]);
  return <div className="workboard" data-testid="machine-workboard">
    <header className="wb-intro">
      <p className="wb-eyebrow">DIRECTION / PILOTAGE DES TRAVAUX</p>
      <h2>Le livre blanc de la machine</h2>
      <p className="wb-lead">Comprendre ce qui est acquis, ce qui avance et ce qui reste à prouver.</p>
      <div className="wb-meta"><span>Registre du <time dateTime={WORKBOARD_REVIEWED_AT}>{reviewedDate} UTC</time></span><a href={`${github}/issues/285`} target="_blank" rel="noreferrer">Roadmap II ↗</a></div>
      <p className="wb-snapshot">Registre daté, mis à jour avec les releases de l’interface. Les changements GitHub ultérieurs ne sont pas synchronisés automatiquement. Ce tableau ne mesure pas la santé actuelle du VPS.</p>
    </header>
    <aside className="wb-guard" aria-label="Protection de l’expérience"><span className="wb-shield" aria-hidden="true">◇</span><div><strong>Burn-in protégé</strong><p>Collecte non activée · stress PAPER interdit · aucune rétroaction sur l’epoch active.</p></div><a href={`${github}/issues/286`} target="_blank" rel="noreferrer">Garde #286 ↗</a></aside>
    <section className="wb-metrics" aria-label="Répartition des travaux">
      {statuses.map(key => <button key={key} type="button" className={`wb-metric wb-${key}`} aria-pressed={status === key} onClick={() => setStatus(status === key ? "all" : key)}><span>{STATUS_LABELS[key]}</span><strong>{WORK_ITEMS.filter(item => item.status === key).length}</strong><small>{key === "done" ? "dans le périmètre indiqué" : key === "paused" ? "volontairement différés" : "missions du registre"}</small></button>)}
    </section>
    <section className="wb-next" aria-labelledby="wb-next-title"><div className="wb-section-heading"><h3 id="wb-next-title">Le chemin devant nous</h3><span>Ordre de travail · sans date promise</span></div><ol>
      <li><b>01</b><div><strong>Qualifier l’observation</strong><p>Adapters, horloges, custody et budgets après les laboratoires intégrés.</p></div></li>
      <li><b>02</b><div><strong>Terminer l’expérience</strong><p>Faits frais, frontière finale, finance et replay du burn-in.</p></div></li>
      <li><b>03</b><div><strong>Certifier le cockpit</strong><p>Gates U8 et L4 distinctes, preuves runtime explicites.</p></div></li>
      <li><b>04</b><div><strong>Ouvrir le cycle suivant</strong><p>Future epoch admise ; observatoire et agents selon dépendances.</p></div></li>
    </ol></section>
    <section className="wb-table-section" aria-labelledby="wb-table-title">
      <div className="wb-section-heading"><h3 id="wb-table-title">Tableau des travaux</h3><span aria-live="polite">{rows.length} / {WORK_ITEMS.length} travaux affichés</span></div>
      <div className="wb-filters"><label className="wb-search">Rechercher<input aria-label="Rechercher" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Mission, preuve, numéro d’issue…" /></label><label>État<select aria-label="État" value={status} onChange={event => setStatus(event.target.value as WorkStatus | "all")}><option value="all">Tous les états</option>{statuses.map(key => <option key={key} value={key}>{STATUS_LABELS[key]}</option>)}</select></label><label>Domaine<select aria-label="Domaine" value={area} onChange={event => setArea(event.target.value)}><option value="all">Tous les domaines</option>{areas.map(value => <option key={value}>{value}</option>)}</select></label><button className="wb-reset" type="button" onClick={() => {setQuery("");setStatus("all");setArea("all");}}>Réinitialiser</button></div>
      <p className="wb-legend">Vert ● terminé dans son périmètre (source, laboratoire ou runtime, voir « Périmètre ») · jaune ◐ en cours · rouge ○ non commencé · rouge plein ■ bloqué · gris ❚❚ en pause. Aucun statut « échec » n’est enregistré : une issue ouverte n’est pas un échec.</p>
      <div className="wb-table-scroll" role="region" aria-label="Liste des missions et preuves" tabIndex={0}><table><caption className="wb-sr-only">Travaux de l’infrastructure de recherche, état au registre, preuve et prochaine étape</caption><thead><tr><th scope="col">Mission</th><th scope="col">État</th><th scope="col">Périmètre / preuve</th><th scope="col">Prochaine étape</th></tr></thead><tbody>{rows.map(item => <tr key={item.id}><td data-label="Mission"><span className="wb-row-id">{item.id} <span>· {item.area}</span></span><strong>{item.title}</strong><div className="wb-row-links"><a href={`${github}/issues/${item.issue}`} target="_blank" rel="noreferrer">Issue #{item.issue} ↗</a>{item.pr && <a href={`${github}/pull/${item.pr}`} target="_blank" rel="noreferrer">PR #{item.pr} ↗</a>}</div></td><td data-label="État"><Dot status={item.status} /></td><td data-label="Périmètre / preuve"><strong className="wb-scope">{item.scope}</strong><p>{item.evidence}</p></td><td data-label="Prochaine étape"><p>{item.next}</p></td></tr>)}</tbody></table></div>
      {rows.length === 0 && <p className="wb-empty" role="status">Aucun travail ne correspond à ces filtres. Réinitialise pour retrouver le registre complet.</p>}
    </section>
    <details className="wb-whitepaper"><summary>Livre blanc · vision, règles et critères de sortie</summary><div className="wb-paper-grid"><article><h3>Une infrastructure de recherche</h3><p>La machine produit des faits PAPER, les conserve et les exporte vers Research pour les rejouer, diagnostiquer et proposer des candidats. Chaque évolution doit rester explicable et reproductible.</p><p>Le socle F00, FIN PAPER V1 et Research est établi. L3 est certifié ; le burn-in demeure non finalisé.</p></article><article><h3>Deux vérités à distinguer</h3><p><strong>Source :</strong> code revu, tests et preuves intégrés dans GitHub.</p><p><strong>Runtime :</strong> version effectivement servie ou exécutée, avec une observation datée et vérifiée. Un merge ne vaut pas déploiement.</p></article><article><h3>La frontière scientifique actuelle</h3><p>La complétude du vrai producteur et la durabilité par packet restent <strong>non prouvées</strong>. Les laboratoires démontrent des mécanismes limités ; ils ne certifient pas la population réelle.</p><p>Une valeur inconnue reste inconnue. Aucun compteur courant n’est reconstruit à partir d’un ancien checkpoint.</p></article><article><h3>Ce qui ouvre le prochain cycle</h3><p>Clôture scientifique du burn-in, instruments qualifiés, contrats d’adaptation, ressources et custody admises, puis décisions d’expérience et d’activation distinctes.</p><p>L’économie d’agents et le Treasury réel restent différés.</p></article></div></details>
    <footer className="wb-footer"><p>Références : <a href={`${github}/issues/285`}>roadmap active #285</a> · <a href={`${github}/issues/282`}>burn-in #282</a> · <a href={`${github}/issues/404`}>admissibilité #404</a> · <a href={`${github}/issues/428`}>tableau #428</a></p><details><summary>Provenance du registre</summary><p>Registre éditorial consolidé : {WORKBOARD_REVIEWED_AT}. Source main : <code>{WORKBOARD_SOURCE_SHA}</code>. Les missions proposées et les preuves historiques sont distinguées dans chaque ligne. Aucun statut runtime global n’est inféré.</p></details></footer>
  </div>;
};
