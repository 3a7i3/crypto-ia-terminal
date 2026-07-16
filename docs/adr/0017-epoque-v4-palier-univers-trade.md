# ADR-0017 — Époque dataset V4 et paliers d'élargissement de l'univers tradé

- **Statut** : Accepté sur le principe (décision opérateur Mathieu,
  2026-07-16 — « il faut acter une nouvelle époque de dataset (V4) au moment
  du palier 1 : compteur remis à zéro, mais avec un débit 5-10× plus élevé,
  N=500 arrive plus vite au total qu'en attendant sur 28 paires »).
  **Activation conditionnée aux déclencheurs § Déclencheurs** — la pose de
  la borne V4 et la liste du palier 1 seront ajoutées ici au moment T.
- **Date** : 2026-07-16
- **Contexte** : ADR-0015 (univers épinglé 28 paires) a relancé le burn-in
  (~5-6 trades/jour) mais N=500 resterait à ~2-3 mois. La couche
  d'observation (ADR-0016, phases R1/R2) mesure désormais un univers de
  200 paires liquides — le levier de débit est l'univers, pas les seuils
  (sonde de débit du 2026-07-15).

## Décision

1. **Palier 1** : étendre l'univers TRADÉ (paper) de 28 à **100-200 paires**
   issues de la shortlist radar R1. La liste est arrêtée par l'opérateur au
   moment de l'activation et reste **épinglée** (mécanisme ADR-0015,
   `UNIVERSE_PINNED_SYMBOLS`) — l'élargissement ne réintroduit PAS la
   rotation d'univers. Paliers suivants : ~500 puis ~1000, chacun par
   révision du présent ADR, jamais implicitement.
2. **Époque V4** : au restart d'activation du palier 1, une nouvelle borne
   `CLEAN_DATA_SINCE_V4` est posée dans `scripts/data_quality.py` (source
   unique, précédent V1→V2→V3) = timestamp du restart. Le N canonique, le
   CRI et tous les seuils de la règle du statisticien se comptent depuis V4.
   Les données V3 restent archivées et documentées (époque 28 paires) —
   comparables entre elles, jamais mélangées avec V4.
3. **Les seuils de décision ne changent PAS** : mêmes seuils par régime,
   mêmes gates, même moteur. On élargit ce que la machine REGARDE pour
   trader, pas sa permissivité. Toute modification de seuil reste interdite
   avant N(V4)>=500 / CRI>=90.
4. **Anti-spam Telegram (exigence opérateur)** : avant activation, les
   panneaux qui listent chaque symbole (section SIGNAUX des rapports,
   résumé @QuantCrpto) doivent passer en agrégats au-delà de ~30 paires
   (compteurs par régime + top 10), sur le modèle du digest radar.

## Déclencheurs d'activation (tous requis)

| # | Condition | Mesure |
|---|---|---|
| T1 | >= 5 jours de données R2 sur la shortlist | `horizon_eval_*.json` |
| T2 | Churn quotidien de la shortlist < 15 % (stabilité) | entrées/sorties R1 |
| T3 | Débit projeté du palier >= 5× le débit actuel | R2 opportunités/jour + throughput_probe |
| T4 | Dry-run de charge : cycle complet < 200 s sur la taille du palier | mesure sur VPS |
| T5 | Panneaux Telegram agrégés livrés | commit |
| T6 | Go opérateur écrit + liste du palier figée dans cet ADR | révision ADR |

## Procédure d'activation (au moment T)

1. Commit : borne `CLEAN_DATA_SINCE_V4` + liste palier 1 dans cet ADR.
2. `.env` VPS : `UNIVERSE_PINNED_SYMBOLS="<liste palier 1>"`.
3. `deploy_vps.sh --confirm --yes --restart core` (ADR-0013).
4. Vérifier au boot : « ÉPINGLÉ : N symboles », borne V4 active,
   premier cycle < 200 s, panneaux agrégés.
5. Mettre à jour CLAUDE.md (borne canonique V4) et la mémoire de session.

## Conséquences

- **Assumé** : remise à zéro du compteur N (42 trades V3 archivés, non
  perdus — ils documentent l'époque 28 paires). Gain attendu : débit ×5-10
  → N=500 en 2-4 semaines au lieu de 2-3 mois.
- **Risques contrôlés** : charge du cycle (T4), qualité de la longue
  traîne (filtres durs R1 : volume, spread, présence), sur-information
  Telegram (T5), stationnarité (liste épinglée, époque documentée).
- **Réversibilité** : revenir à la liste 28 paires ADR-0015 + re-borner —
  documenté par révision d'ADR.

## Liens

- ADR-0011/0012 (précédents de bornes d'époque V1→V3)
- ADR-0015 (mécanisme d'épinglage — réutilisé tel quel)
- ADR-0016 (couche d'observation R1/R2 — source des mesures T1-T3)
- docs/design/scanner-500-paires.md (palier 2+, refonte scanner)
