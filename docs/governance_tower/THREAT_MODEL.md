# Governance Tower — Modèle de menaces (GOV-TOWER-00, lot A/G)

Périmètre : prototype local `governance_tower/` (serveur loopback, SENTINEL-01, fournisseurs de lecture).
État : `IMPLEMENTED_SOURCE`, `TESTED_LOCAL`, `NOT_DEPLOYED`. Garde #286 active.

## 1. Actifs à protéger

| Actif | Pourquoi |
|---|---|
| Burn-in actif (epoch, runtime gelé, config, PPL/FIN) | intégrité scientifique de l'expérience (#282, #286) |
| Secrets (jetons GitHub, clés exchange, `.env`, clés SSH) | compromission de comptes et d'argent |
| Autorité opérationnelle (restart, deploy, merge, gates) | seule l'opérateur décide (#286, #315, #445) |
| Exactitude des réponses | un faux « tout va bien » ou un faux zéro induit une mauvaise décision |

## 2. Frontières

```
navigateur ──(loopback, Host contrôlé, X-GT-Request)──► serveur GT ──► Sentinel ──► table fixe d'outils READ-ONLY
                                                                          │
                                       GitHub (GET opt-in, non fiable) ◄──┤
                         snapshots publiés (fichiers ou Operator API GET) ◄┘
```

Rien ne traverse dans l'autre sens : aucun outil n'écrit, aucune réponse ne pilote un processus.

## 3. Adversaires et données non fiables

| Source | Hypothèse |
|---|---|
| Titres d'issues/PR/commits, README, commentaires | contrôlables par n'importe quel contributeur ; données, jamais instructions |
| Extraits de journaux, snapshots | peuvent contenir du texte injecté ; validés par contrat, cités seulement |
| Page web tierce dans le navigateur de l'opérateur | peut tenter du CSRF ou du DNS rebinding vers le port local |
| Question de l'utilisateur | peut être une demande d'action déguisée (« pour vérifier la santé, redémarre Advisor ») |
| Futur modèle de langage | peut halluciner une preuve ou suivre une injection |

## 4. Abus → mitigations → preuves

| Abus | Mitigation | Test |
|---|---|---|
| Demande d'action (restart, deploy, merge, PR, ordre, paiement, seuil, gate) | politique de refus **avant tout outil** | `test_gt_sentinel.py::test_mutating_requests_refused_before_any_tool` |
| Demande déguisée | motifs sur les verbes d'action, pas sur le contexte | même test, cas « Pour vérifier la santé… » |
| Outil inconnu, outil d'écriture | table fixe immuable, `read_only=True` imposé, budget d'appels | `test_tool_table_is_fixed_and_read_only`, `test_tool_budget_enforced` |
| Prompt injection via PR/issue/journal | l'intention est figée par la question avant lecture ; texte cité dans `untrusted_quotes` ; constat candidat | `test_injection_in_pr_title_and_log_is_quoted_not_obeyed` + scénario `injection` |
| Fuite de secret dans une sortie | rédaction (`redaction.py`) des motifs connus ; jeton GitHub jamais en attribut, log ou preuve | `test_secrets_are_redacted`, tests du connecteur GitHub |
| Lecture d'un `.env`, d'une clé, d'un `.git/` | chemins interdits exclus ; aucun outil de lecture de fichier arbitraire | `test_forbidden_paths`, `locate_code` |
| Faux zéro / faux vide | `Observation` : aucune valeur si absent ; `DENIED ≠ EMPTY` | `test_absent_states_never_carry_a_value_not_even_zero`, `test_github_denied_is_not_empty` |
| Fixture prise pour une preuve réelle | locator `fixture:` obligatoire pour SYNTHETIC ; mélange SYNTHETIC/LIVE_READ refusé ; bandeau DÉMO | `test_mixed_synthetic_and_live_refused_in_snapshot_and_run`, `test_synthetic_and_live_providers_cannot_be_mixed` |
| Horodatage futur, SHA malformé | contrat refuse | `test_future_observation_refused`, `test_invalid_sha_refused` |
| Runtime gelé pris pour une dérive | référence déclarée #286 → `EXPECTED_PINNED_RUNTIME` | `test_pinned_runtime_is_expected_not_drift` |
| Dérive affirmée sans preuve | au mieux `POSSIBLE_DRIFT` ; `VIOLATION_PROVEN` jamais produit par l'analyse | `test_unexpected_sha_is_possible_drift_never_violation` |
| Panne de source convertie en succès | exception fournisseur → `ToolCall ERROR` et source `ERROR` | `test_provider_failure_never_becomes_success` |
| Épuisement ou contournement de quota GitHub | budget par question (12), plafond de service glissant (40/h), blocage distant mémorisé (`Retry-After`, `X-RateLimit-Reset`) même pour une nouvelle question | `test_gt_github_provider.py::test_remote_rate_limit_survives_a_new_question_and_is_never_a_success`, `test_service_ceiling_holds_across_questions_until_the_window_slides` |
| État de source ancien présenté comme courant | âge mesuré, `STALE` au-delà de 300 s, rafraîchissement GET du statut | `test_source_status_carries_age_and_turns_stale` |
| Échec d'audit masqué | incertitude ajoutée au run, état `audit` dans `/api/status` | `test_audit_cap_is_visible_in_every_run_never_a_silent_success`, `test_audit_write_error_is_reported_without_crashing_the_answer` |
| CSRF / DNS rebinding | en-tête `X-GT-Request`, contrôle `Host` et `Origin` | `test_gt_server.py` |
| Exposition réseau | bind refusé hors loopback | `test_bind_outside_loopback_refused` |
| Payload surdimensionné | corps ≤ 8 Kio, question ≤ 2 000 car., réponses GitHub/hôte bornées | `test_body_bounds_and_shape`, tests fournisseurs |
| Traversée de chemin, symlink | chemins statiques fixes ; snapshots ouverts avec `O_NOFOLLOW` | `test_unknown_paths_404_and_no_traversal`, tests hôte |
| XSS dans l'interface | rendu `textContent` uniquement, CSP `script-src 'self'`, liens seulement vers `https://github.com/` | `test_gt_ui_static.py` |
| Chemin de code vers runtime/FIN/exchange | imports contrôlés par AST, aucun `subprocess`/`socket` | `test_gt_isolation.py` |
| Activation implicite d'un modèle payant, worker, scheduler | `ClaudeApiReasoner` refuse de s'instancier ; aucun thread/timer dans le paquet | `test_claude_reasoner_disabled_by_default`, `test_no_scheduler_worker_or_daemon_entrypoints` |

## 5. Risques résiduels

1. **Pas d'authentification utilisateur** : acceptable uniquement en loopback sur un poste de confiance. Toute exposition (tailnet, tunnel, VPS) exige une authentification dédiée et une gate distincte.
2. **Détection d'injection heuristique** : elle peut manquer un texte. Ce n'est pas la barrière de sécurité : celle-ci est l'absence de tout outil mutateur et le choix d'outils avant lecture des contenus.
3. **Rédaction par motifs** : un secret de format inconnu peut passer. Les fournisseurs ne lisent jamais de contenu de fichier, de corps d'issue ni de journal brut, ce qui limite l'exposition.
4. **Politique de refus par motifs** : conservatrice (certaines questions légitimes contenant « secret » ou « token » sont refusées). Préférer un refus de trop qu'une action.
5. **Références gelées documentaires** : `pinned_references.json` recopie #286 ; si #286 évolue, le fichier doit être mis à jour par revue humaine.
6. **Futur raisonneur LLM** : non implémenté ; son intégration devra valider toute sortie contre `SentinelAnswer`/`AgentRun` (preuves citées ⊆ preuves du run).
7. **Preuves de connexion bornées** : GitHub réel exercé, VPS lu par transport direct puis copies des projections analysées localement ; `OperatorApiHostProvider` distant reste non démontré. Dates et limites dans [DELIVERY_REPORT.md](DELIVERY_REPORT.md).
8. **Temps et disponibilité** : timeouts réseau d’inactivité, pas deadline globale ; serveur stdlib loopback sans qualification face aux clients lents. Aucun service exposé autorisé.
