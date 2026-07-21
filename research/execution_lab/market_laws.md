# Market Laws — registre versionné (labo passif, ADR-0007)

Registre des **propriétés statistiques observées** du marché. Une « loi » n'est
PAS une stratégie et n'influence JAMAIS le moteur live. Chaque entrée porte un
**niveau de preuve** explicite et un **état de cycle de vie**. Toute promotion
vers le moteur passe par ADR + nouvelle époque expérimentale (jamais un tweak).

> Discipline : chaque loi est **pré-enregistrée** (définition + test fixés AVANT
> de regarder les résultats). Le registre conserve aussi les **candidates
> rejetées** — le dénominateur (tout ce qui a été testé) est nécessaire pour
> corriger les comparaisons multiples. Une observation sur une seule fenêtre
> n'est jamais une vérité générale.

## Niveaux de preuve

| Niveau | Signification |
|--------|---------------|
| E0 | Observation brute, non reproduite |
| E1 | Régularité observée, méthode reproductible, **une seule fenêtre** |
| E2 | Reproduite sur ≥2 fenêtres temporelles disjointes |
| E3 | Tenue à travers les régimes (haussier / baissier / range) |
| E4 | Tenue à travers marchés/exchanges (spot ↔ swap, MEXC ↔ autre) |
| E5 | Validée hors-échantillon (holdout) + walk-forward |
| E6 | Cohérente avec le comportement du moteur en paper (gates existants) |
| E7 | Validée en réel, capital limité (progression A→B→C) |
| E8 | Éligible à une promotion via ADR + nouvelle époque |

## Cycle de vie (bidirectionnel — une loi peut DÉCROÎTRE)

```
Candidate → Observed(E1) → Reproduced(E2) → Cross-Regime(E3)
          → Cross-Exchange(E4) → Validated(E5) → Operational(E8)
```

**Une loi n'est jamais acquise** : demi-vie/stabilité surveillées en continu ;
une loi dont la régularité s'éteint (alpha decay, changement de structure de
marché) **redescend** de niveau. Pas de cliquet à sens unique.

---

## LAW-001 — Pump Reversion (réversion des impulsions haussières)

- **Niveau : E1** (observée, une seule fenêtre — PAS encore cross-régime/exchange)
- **État : Observed**
- **Univers** : MEXC spot, liquidité qv 24h ≥ 1 M$ (50 symboles)
- **Fenêtre** : 2026-07-16 → 2026-07-21 (6 jours, régime **principalement haussier**)
- **Définition (pré-enregistrée)** : impulsion 15 min ≥ θ % (θ ∈ {0.5, 1, 2}) ;
  survie = rendement forward dir-ajusté à +15m/+1h/+4h vs baseline (|r| < 0.25 %).
- **Observation** : après une impulsion haussière, le rendement forward est
  **inférieur à la baseline** à tous les horizons ; continuation à +4h = 41 %
  contre 61 % pour la baseline (θ=1 %). Réversion **croissante** avec θ et
  l'horizon (θ=2 % : −3.33 % à +4h). Stable aux 3 seuils.
- **Menaces à la validité (déclarées)** : une seule fenêtre de régime (haussier),
  fenêtres chevauchantes (autocorrélation), **spot alors que le moteur trade swap**,
  physique de PRIX (pas les signaux réels du moteur), pas d'ATR (impulsion en %).
- **Prochains gates avant E2+** : rejouer sur une fenêtre disjointe (E2),
  puis en régime baissier/range (E3), puis sur swap / autre exchange (E4).
- **Sonde** : `scratchpad/signal_survival_probe.py` (lecture seule).
- **NB** : ne dit PAS « mean_reversion est la meilleure stratégie » — aucune
  comparaison momentum/hybrid/regime-switching sur les mêmes événements.

## LAW-002 (candidate) — Dump Persistence (persistance des impulsions baissières)

- **Niveau : E0/E1** (observation compagnon de LAW-001, même fenêtre)
- **Observation** : après une impulsion baissière, P(continue de baisser) à +4h
  = 52 % contre baseline P(baisse) = 39 %. Les baisses brutales **persistent**
  davantage que la baseline. Asymétrie avec LAW-001 (« fade les pumps, suis les
  dumps »). Mêmes menaces à la validité.

---

*Registre créé 2026-07-21. Prochaines lois candidates envisagées (NON testées) :
Weekend Effect, Volatility Compression, Spread Expansion. Chacune devra être
pré-enregistrée avant tout calcul.*
