# D1_C_CAUSAL_COVERAGE_MATRIX

Version méthode `D1_C_V1`, contrat source au parent
`b99c2ed4f38ebeff481b5f470ed2d08e8e852257`. Dénominateur : tous les REJECTED
présents dans la capture dont le manifest, les composants et les index sont
revérifiés. Aucun dénominateur producteur/epoch implicite.

| Catégorie | Preuve minimale | Portée / limite |
|---|---|---|
| LINKED | observation_id unique, packet_id unique, trace_id exact, symbol/cycle exacts, identité avec payload digest valide, timestamp observation ≥ packet ; record satisfait les validations identifiables | record observé dans copie, pas reçu d'écriture ni garantie du producteur |
| PROVEN_NOT_ELIGIBLE / NATIVE_LSE_NON_ACTIONABLE | metadata.lse_actionable bool False | filtre producteur exclut selon contrat source ; pas de reconstruction de score |
| PROVEN_NOT_ELIGIBLE / NATIVE_SIGNAL_SIDE_EXCLUDED | metadata.signal_raw chaîne hors BUY/SELL/LONG/SHORT, corroborée par message live_signal_engine exact | HOLD/FLAT/autre exclus ; packet.side=FLAT seul ne prouve pas le signal original |
| ELIGIBLE_WITHOUT_OBSERVED_RECORD | lse_actionable True, signal_raw directionnel corroboré, transition pipeline_g8d→REJECTED portant exactement trade_allowed=False [motif], identité native joignable | filtres identifiables satisfaits ; prix result.prix, publication, livraison et persistance non prouvés ; anomalie candidate seulement |
| UNKNOWN_ELIGIBILITY | preuve minimale précédente absente/ambiguë | conserve population, jamais imputé à zéro ni certifié perdu |
| INTEGRITY_FAILURE | duplicate packet/trace/observation, observation orpheline, lien non REJECTED, conflit trace/symbol/cycle, identité manquante, manifest/hash/format/time invalides | arrêt sans classification ; compteurs non établis, pas de ligne exclue silencieusement |

Priorité déterministe : lien valide d'abord (contradiction native = arrêt),
puis non-actionable, puis exclusion side, puis candidat, puis UNKNOWN. Une
identité peut avoir un historique de plusieurs lignes à même trace seulement
si le digest/payload et le binding sont cohérents ; cette multiplicité est
comptée séparément, pas assimilée à deux décisions. Packet traces doivent
rester uniques ; aucun rapprochement temporel ou symbole seul.

Le rapport donne quatre matrices : catégorie sémantique packet ; premier
acteur de transition REJECTED ; premier blocker OBSERVÉ de RejectionStore ;
heure UTC (24 lignes, avec zéros de capture explicites). Chaque matrice a
exactement le même total REJECTED. Le premier blocker des packets non liés
reste UNKNOWN ; le premier acteur packet ne le remplace pas. Un zéro horaire
mesure seulement l'absence de ligne dans la capture, pas l'absence de décision
au producteur. Les vocabulaires de sortie sont fermés : aucun ID ni texte
libre des records n'est publié.

Équations :

- packets = REJECTED + non_REJECTED ; EXECUTION_PENDING est compté séparément,
  jamais FILLED.
- REJECTED = LINKED + PROVEN_NOT_ELIGIBLE + ELIGIBLE_WITHOUT_OBSERVED_RECORD +
  UNKNOWN_ELIGIBILITY.
- observations = LINKED après validation univoque.
- REJECTED sans record = les trois catégories non LINKED ; aucune perte certifiée.

La temporalité est contrôlée identity.ts ≤ packet.created_at ≤ observation.ts,
à l'intérieur de [2026-10-10T00:00:00Z,2026-10-11T00:00:00Z). Cela reste une
cohérence de temps déclarés ; l'horloge et le délai de dispatch/fsync ne sont
pas certifiés. created_at naïf est compté comme hypothèse UTC explicite.

L'API pure classify_records retourne UNATTESTED_RECORDS_CLASSIFIED : elle ne
certifie pas la garde des bytes. Seule l'entrée publique audit, sans override
de hash/count/custody, peut retourner D1_C_REAL_SUBSET_CLASSIFIED après reprise
de l'auditeur D1 intact et relecture bornée hashée. La CLI exige une racine
Research absolue explicitement fournie ; pas de recherche automatique des
sources, d'import Advisor, d'écriture, d'API ou de credentials.
