import React from "react";
import { useRuntimeService, type RuntimeServiceState } from "../lib/runtimeServiceClient";

export const RuntimeServiceCard: React.FC<{ state: RuntimeServiceState; testId?: string }> = ({ state, testId = "runtime-service-view" }) => {
  if (state.status !== "success") {
    const label = state.status === "loading" ? "CHARGEMENT" : state.status === "api_error" ? state.errorCode : "ERREUR TRANSPORT / CONTRAT";
    return <article className="direction-card direction-card-governed runtime-service-card" data-testid={testId}><h3>Service Advisor · host</h3><strong>{label}</strong><p>État du service · INCONNU</p><p>La preuve host est indépendante du snapshot Advisor.</p></article>;
  }
  const s = state.snapshot, service = s.service, d = s.deployment;
  const stale = s.freshness_classification === "STALE";
  return (
    <article className="direction-card direction-card-governed runtime-service-card" data-testid={testId}>
      <div className="direction-card-heading"><h3>Service Advisor · host</h3><span className="direction-card-badge">{s.freshness_classification}</span></div>
      <div className="runtime-service-state" data-testid="runtime-service-state"><strong>{stale || service.query_status !== "OK" ? "ÉTAT ACTUEL · INCONNU" : `ÉTAT OBSERVÉ · ${service.active_state}`}</strong><span>{service.query_status}</span></div>
      {stale && <p className="direction-warning">Preuve périmée : les valeurs ci-dessous décrivent la dernière observation, pas l’état actuel.</p>}
      <dl className="direction-fact-grid">
        <div><dt>Unité Advisor</dt><dd>{service.unit}</dd></div>
        <div><dt>Host</dt><dd>{s.host_id}</dd></div>
        <div><dt>LoadState</dt><dd>{service.load_state ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>ActiveState à la capture</dt><dd>{service.active_state ?? "UNKNOWN"}</dd></div>
        <div><dt>SubState à la capture</dt><dd>{service.sub_state ?? "UNKNOWN"}</dd></div>
        <div><dt>MainPID à la capture</dt><dd>{service.main_pid ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>NRestarts</dt><dd>{service.restart_count ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>Démarrage process · UTC</dt><dd>{service.exec_main_started_at_utc ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>Observé à</dt><dd>{s.observed_at_utc}</dd></div>
        <div><dt>Âge de la preuve host</dt><dd>{s.snapshot_age_s}s</dd></div>
        <div><dt>Source code · preuve fournie</dt><dd>{d.source_code_sha ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>Preuve de déploiement</dt><dd>{d.status}</dd></div>
      </dl>
      <p className="direction-boundary">Un service actif ne certifie ni la santé du cycle Advisor ni une permission de trade.</p>
      <details className="direction-provenance" data-testid="runtime-service-provenance">
        <summary>Voir provenance host</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/runtime-service</dd></div>
          <div><dt>Autorité</dt><dd>{s.authority}</dd></div>
          <div><dt>Invocation systemd</dt><dd>{service.invocation_id ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Généré à</dt><dd>{s.generated_at_utc}</dd></div>
          <div><dt>Référence déploiement</dt><dd>{d.evidence_ref ?? d.reason}</dd></div>
          <div><dt>Preuve déploiement observée</dt><dd>{d.observed_at_utc ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Digest artifact de preuve</dt><dd>{d.artifact_sha256 ?? "NOT_AVAILABLE"}</dd></div>
        </dl>
      </details>
    </article>
  );
};

export const RuntimeServiceView: React.FC = () => <RuntimeServiceCard state={useRuntimeService()} />;
