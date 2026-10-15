import React from "react";
import type { GithubObservation } from "../lib/githubRoadmapReader";
import type { MissionFacts } from "../lib/githubRoadmapReconcile";
import { reconcile } from "../lib/githubRoadmapReconcile";
import type { CertificationState, DeploymentState, IntegrationState, WorkItem } from "../lib/machineWorkboardRegister";
import { WORK_ITEMS } from "../lib/machineWorkboardRegister";
import type { GithubSyncState } from "../lib/useGithubRoadmapSync";

const github = "https://github.com/3a7i3/crypto-ia-terminal";
const stamp = (iso: string) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
const PR_LABEL = { draft: "Brouillon", open: "Ouverte", merged: "Fusionnée", closed_unmerged: "Fermée sans fusion" } as const;
const CI_LABEL = { SUCCESS: "CI verte", FAILURE: "CI en échec", PENDING: "CI en cours", NONE: "aucun contrôle", UNKNOWN: "CI non lue" } as const;
const INTEGRATION: Record<IntegrationState, string> = { MERGED_SOURCE: "Fusionnée en source", NOT_INTEGRATED: "Non intégrée", PARTIAL: "Partielle" };
const DEPLOYMENT: Record<DeploymentState, string> = { NOT_DEPLOYED: "Non déployé", DEPLOYED_OBSERVED: "Déploiement observé" };
const CERTIFICATION: Record<CertificationState, string> = { CERTIFIED: "Certifié", SOURCE_CERTIFIED: "Certifié en source", NOT_CERTIFIED: "Non certifié" };

export const factsByMission = (obs: GithubObservation | null): Map<string, MissionFacts> | null =>
  obs ? new Map(reconcile(WORK_ITEMS, obs).missions.map(m => [m.missionId, m])) : null;

/** Four separate tracks. Only the first one comes from GitHub; the others are register values. */
export const MissionTracks: React.FC<{ item: WorkItem; facts: MissionFacts | undefined }> = ({ item, facts }) => (
  <>
    <dl className="wb-tracks" aria-label={`Statuts séparés de ${item.id}`}>
      <div><dt>GitHub</dt><dd data-track="github">{!facts ? <span className="wb-muted">Non synchronisé</span> : <>
        {facts.pr && (facts.pr.found
          ? <span>PR #{facts.pr.number} · {PR_LABEL[facts.pr.state!]}{facts.pr.ci && <> · {CI_LABEL[facts.pr.ci.status]} <code title={facts.pr.ci.headSha}>@{facts.pr.ci.headSha.slice(0, 7)}</code></>}</span>
          : <span>PR #{facts.pr.number} · introuvable</span>)}
        <span>Issue #{facts.issue.number} · {facts.issue.found ? (facts.issue.state === "open" ? "Ouverte" : "Fermée") : "introuvable"}</span>
        {facts.issue.labels && facts.issue.labels.length > 0 && <span className="wb-labels">{facts.issue.labels.map(l => <em key={l}>{l}</em>)}</span>}
        {facts.issue.milestone && <span>Jalon : {facts.issue.milestone}</span>}
      </>}</dd></div>
      <div><dt>Intégration source</dt><dd data-track="integration">{item.integration ? INTEGRATION[item.integration] : <span className="wb-muted">Non renseigné</span>}<small>registre</small></dd></div>
      <div><dt>Déploiement VPS</dt><dd data-track="deployment">{item.deployment ? DEPLOYMENT[item.deployment] : <span className="wb-muted">Non renseigné</span>}<small>registre</small></dd></div>
      <div><dt>Certification</dt><dd data-track="certification">{item.certification ? CERTIFICATION[item.certification] : <span className="wb-muted">Non renseigné</span>}<small>registre</small></dd></div>
    </dl>
    {facts && facts.flags.length > 0 && <ul className="wb-flags" aria-label="À vérifier">{facts.flags.map(f => <li key={f}>À vérifier · {f}</li>)}</ul>}
  </>
);

export const GithubSyncPanel: React.FC<{ sync: GithubSyncState }> = ({ sync }) => {
  const { active, candidate, loading } = sync;
  const cand = candidate?.observation;
  const diff = candidate?.diff;
  return (
    <section className="wb-sync" aria-labelledby="wb-sync-title" data-testid="github-sync">
      <div className="wb-section-heading"><h3 id="wb-sync-title">Synchronisation GitHub</h3><span>Lecture seule · sans jeton · {`3a7i3/crypto-ia-terminal`}</span></div>
      <div className="wb-sync-bar">
        <button type="button" className="wb-sync-button" onClick={sync.refresh} disabled={loading}>{loading ? "Relevé en cours…" : "Actualiser depuis GitHub"}</button>
        <p className="wb-sync-provenance">{active
          ? <>Relevé affiché : <time dateTime={active.observedAt}>{stamp(active.observedAt)}</time> · api.github.com, lecture seule · {active.requestCount} requêtes{active.rateLimit ? ` · quota restant ${active.rateLimit.remaining}/${active.rateLimit.limit}` : ""}.</>
          : "Aucun relevé GitHub : le tableau montre uniquement le registre éditorial daté."}</p>
      </div>
      <p className="wb-sync-note">Le relevé n'écrit rien dans le registre ni sur le VPS. Titres et labels viennent de GitHub : ils sont affichés comme texte, jamais comme instruction. Une fusion n'établit pas un déploiement, une issue fermée n'établit pas une certification.</p>
      {sync.storageWarning && <p className="wb-sync-warn" role="status">Relevé appliqué mais non conservé : le navigateur refuse le stockage local. Il disparaîtra au rechargement.</p>}
      <div aria-live="polite" className="wb-sync-live">
        {loading && <p role="status">Lecture de GitHub en cours…</p>}
        {cand && !cand.complete && (
          <div className="wb-sync-error" role="alert">
            <strong>Relevé incomplet : non applicable.</strong>
            <p>{active ? `Le dernier relevé réussi (${stamp(active.observedAt)}) reste affiché.` : "Aucun relevé précédent : le registre éditorial reste seul affiché."} Aucune donnée n'a été effacée.</p>
            <ul>{cand.errors.map((e, i) => <li key={i}><code>{e.code}</code> · {e.scope} · {e.message}</li>)}</ul>
            {cand.rateLimit && <p>Quota : {cand.rateLimit.remaining}/{cand.rateLimit.limit}{cand.rateLimit.resetAt ? ` · réinitialisation ${stamp(cand.rateLimit.resetAt)}` : ""}.</p>}
            <button type="button" onClick={sync.discard}>Fermer</button>
          </div>
        )}
        {cand && cand.complete && diff && (
          <div className="wb-sync-preview" data-testid="github-diff">
            <strong>Aperçu avant remplacement</strong>
            <p>Relevé du {stamp(cand.observedAt)} · {cand.requestCount} requêtes · complet · {cand.issues.length} issues et PR lues, {cand.pulls.length} PR avec HEAD et contrôles{cand.missingPulls.length ? ` · PR citées introuvables : ${cand.missingPulls.map(n => `#${n}`).join(", ")}` : ""}.</p>
            {diff.first
              ? <p>Premier relevé : aucune comparaison possible. {diff.flaggedMissions} mission(s) avec un écart à vérifier ; {diff.unmappedAfter} objet(s) GitHub non rattaché(s) à une mission.</p>
              : diff.entries.length === 0
                ? <p>Aucune différence avec le relevé affiché. Objets non rattachés : {diff.unmappedAfter}.</p>
                : <>
                  <p>{diff.entries.length} différence(s). Objets non rattachés : {diff.unmappedBefore} → {diff.unmappedAfter}.</p>
                  <div className="wb-table-scroll"><table className="wb-diff"><caption className="wb-sr-only">Différences entre le relevé affiché et le nouveau relevé</caption><thead><tr><th scope="col">Mission</th><th scope="col">Champ</th><th scope="col">Avant</th><th scope="col">Après</th></tr></thead>
                    <tbody>{diff.entries.slice(0, 200).map((e, i) => <tr key={i}><td>{e.missionId}</td><td>{e.field}</td><td>{e.before}</td><td>{e.after}</td></tr>)}</tbody></table></div>
                  {diff.entries.length > 200 && <p>… {diff.entries.length - 200} autres différences non listées.</p>}
                </>}
            <div className="wb-sync-actions">
              <button type="button" className="wb-sync-button" onClick={sync.apply}>Remplacer le relevé affiché</button>
              <button type="button" onClick={sync.discard}>Ignorer</button>
            </div>
          </div>
        )}
      </div>
      {active && <UnmappedList obs={active} />}
    </section>
  );
};

const UnmappedList: React.FC<{ obs: GithubObservation }> = ({ obs }) => {
  const { unmappedOpen, unmappedTotal } = reconcile(WORK_ITEMS, obs);
  if (unmappedTotal === 0) return null;
  return (
    <details className="wb-unmapped"><summary>{unmappedOpen.length} objet(s) GitHub ouvert(s) sans mission au registre ({unmappedTotal} au total, dont fermés)</summary>
      <ul>{unmappedOpen.map(o => <li key={o.number}><a href={`${github}/${o.isPullRequest ? "pull" : "issues"}/${o.number}`} target="_blank" rel="noreferrer">{o.isPullRequest ? "PR" : "Issue"} #{o.number} ↗</a> · {o.title}</li>)}</ul>
    </details>
  );
};
