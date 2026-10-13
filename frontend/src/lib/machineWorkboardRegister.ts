/** Versioned editorial register. These are work states, never runtime telemetry. */
export type WorkStatus = "done" | "active" | "todo" | "blocked" | "paused";
export type WorkItem = {
  id: string;
  title: string;
  area: string;
  status: WorkStatus;
  scope: string;
  evidence: string;
  next: string;
  issue: number;
  pr?: number;
};
export const WORKBOARD_REVIEWED_AT = "2026-10-13T01:34:16Z";
export const WORKBOARD_SOURCE_SHA = "b58f14b447f36efeb6c4c3c356a6510419d1ab98";
export const STATUS_LABELS: Record<WorkStatus, string> = {
  done: "Terminé", active: "En cours", todo: "À faire", blocked: "Bloqué", paused: "En pause",
};
export const WORK_ITEMS: readonly WorkItem[] = [
  { id:"L3", title:"Socle scientifique L0 → L3", area:"Gouvernance", status:"done", scope:"Certification formelle L3", evidence:"Chaîne de certificats intégrée ; L3 acquis.", next:"Conserver les preuves ; préparer L4 sans refaire L3.", issue:362 },
  { id:"U7", title:"Cockpit unifié · certification source", area:"Cockpit", status:"done", scope:"U7 · périmètre historique", evidence:"Certification #382/#383. Les ajouts ultérieurs ne sont pas recertifiés automatiquement.", next:"Préparer la gate runtime U8 séparée.", issue:323, pr:383 },
  { id:"DOC", title:"Documentation et tâche courante", area:"Gouvernance", status:"done", scope:"Source documentaire", evidence:"CURRENT_TASK et README réconciliés avec L3.", next:"Maintenir le registre quand une mission change d’état.", issue:412, pr:413 },
  { id:"CONTRACT", title:"Contrat de collecte · future epoch", area:"Research", status:"done", scope:"Contrat source intégré", evidence:"Roster, reçus, custody, budgets et gates C0–C6 définis.", next:"Qualifier les instruments ; aucune activation acquise.", issue:414, pr:415 },
  { id:"CORE", title:"Cœur de capture isolé", area:"Research", status:"done", scope:"Implémentation source", evidence:"Noyau borné, sans acquisition ni I/O de production.", next:"Qualifier les adapters sous missions distinctes.", issue:416, pr:417 },
  { id:"CAPACITY", title:"Capacité du noyau", area:"Research", status:"done", scope:"Benchmark synthétique local", evidence:"Essais de quotas intégrés ; pas admission du budget total VPS.", next:"Mesurer writer, témoin et collector ensemble.", issue:418, pr:419 },
  { id:"ROSTER-LAB", title:"Acquisition du roster · laboratoire", area:"Research", status:"done", scope:"Mécanisme synthétique intégré", evidence:"Scheduler et workers distincts ; sorties manquantes conservées.", next:"Prouver la couverture du vrai producteur.", issue:420, pr:421 },
  { id:"FSYNC-LAB", title:"Témoin fsync · appel système", area:"Research", status:"done", scope:"Observation native en laboratoire", evidence:"Succès, faux claim sans appel et EBADF distingués.", next:"Conserver les traces ; pas preuve par packet réel.", issue:422, pr:423 },
  { id:"BINDING", title:"Décision → fichier → plage → fsync", area:"Research", status:"done", scope:"Scénario mono-writer de laboratoire", evidence:"#425 fusionnée ; deux records couverts, troisième sans reçu fsync.", next:"Étendre la qualification hors scénario contrôlé.", issue:424, pr:425 },
  { id:"FAULTS", title:"Refus des opérations hors contrat", area:"Research", status:"done", scope:"Laboratoire source intégré", evidence:"#427 fusionnée après CI finale ; six scénarios natifs et preuves conservés.", next:"Versionner les adapters ; rotation et retries restent non supportés.", issue:426, pr:427 },
  { id:"WORKBOARD", title:"Livre blanc et tableau des travaux", area:"Cockpit", status:"active", scope:"Interface source · cette mission", evidence:"Demande opérateur #428 ; aucune preuve de déploiement.", next:"Valider présentation, mobile et CI ; release séparée.", issue:428 },
  { id:"BURNIN", title:"Observation et clôture du burn-in", area:"Expérience", status:"active", scope:"#282 · non finalisé", evidence:"Checkpoints historiques acquis ; aucun compteur actuel déduit.", next:"Preuve fraîche, population finale, frontière quiescente, finance et replay.", issue:282 },
  { id:"FREEZE", title:"Protection de l’epoch active", area:"Gouvernance", status:"active", scope:"Garde constitutionnelle", evidence:"#286 ACTIVE : code/config/epoch protégés.", next:"Maintenir l’interdiction de feedback Research vers cette epoch.", issue:286 },
  { id:"D1-D", title:"Complétude du vrai roster producteur", area:"Research", status:"blocked", scope:"D1-D · NOT_PROVEN", evidence:"Un roster synthétique ne prouve pas toutes les invocations réelles.", next:"Acquérir un roster amont indépendant et des fences vérifiables.", issue:404 },
  { id:"D1-E", title:"Durabilité de chaque packet réel", area:"Research", status:"blocked", scope:"D1-E · NOT_PROVEN", evidence:"La liaison aux décisions et fichiers réels reste non prouvée.", next:"Joindre receipts, ranges, génération et témoin indépendant.", issue:404 },
  { id:"ADAPTERS", title:"Retries, rotation et group-fsync", area:"Research", status:"todo", scope:"Contrat / versionnement à préparer", evidence:"Le parser strict refuse ces opérations ; il ne les prend pas en charge.", next:"Définir les identités et cardinalités avant implémentation séparée.", issue:420 },
  { id:"TRUST", title:"Horloges et custody indépendante", area:"Research", status:"todo", scope:"C2 / C3 incomplets", evidence:"Hashes et processus distincts ne suffisent pas à établir l’indépendance.", next:"Qualifier clocks, gaps, custody et budgets cumulés.", issue:420 },
  { id:"U8", title:"Cockpit · certification runtime", area:"Cockpit", status:"todo", scope:"U8 · non certifié", evidence:"U7 source ne prouve ni release actuelle ni interface servie.", next:"Mission runtime distincte, release exacte et preuves navigateur.", issue:323 },
  { id:"L4", title:"Maturité L4", area:"Gouvernance", status:"todo", scope:"Frontière suivante · non certifiée", evidence:"L3 est acquis ; isolation et preuves opérationnelles L4 restent distinctes.", next:"Préparer la matrice des préconditions et la revue formelle.", issue:362 },
  { id:"GATE-O", title:"Décisions opérateur · autorité", area:"Gouvernance", status:"blocked", scope:"Gate O ouverte / non déployé", evidence:"Six décisions de confiance opérationnelle non résolues.", next:"Définir owners, signataires, clés, registries et anti-rollback.", issue:315 },
  { id:"FUTURE", title:"Admission d’une future collecte", area:"Expérience", status:"blocked", scope:"C4 / C5 · DENIED", evidence:"Aucune activation obtenue par les merges source.", next:"Passer les gates scientifiques puis la décision d’activation distincte.", issue:404 },
  { id:"STRESS", title:"Stress PAPER", area:"Expérience", status:"blocked", scope:"Runtime · DENIED", evidence:"Complétude et durabilité restent NOT_PROVEN.", next:"Rester interdit tant que l’admissibilité n’est pas démontrée.", issue:404 },
  { id:"CVMO", title:"Observatoire de marché multi-exchanges", area:"Futur", status:"todo", scope:"Roadmap R4 · non démarré", evidence:"Fondations existantes à réutiliser ; pas de nouveau wiring runtime attesté.", next:"Audit de réutilisation, contrat public et queues bornées.", issue:285 },
  { id:"FIN", title:"Allocation future et Treasury réel", area:"Futur", status:"paused", scope:"FIN-03 / FIN-04 différés", evidence:"FIN PAPER V1 acquis ; nouvelles allocations et REAL non autorisés.", next:"Attendre burn-in propre et gates explicites.", issue:150 },
  { id:"AGENTS", title:"Agents, bounties et économie AIC", area:"Futur", status:"paused", scope:"Architecture future · non déployée", evidence:"Aucun agent actif, marché ni solde AIC inventé.", next:"Après les dépendances, définir propriétaires et contrats gouvernés.", issue:284 },
];
