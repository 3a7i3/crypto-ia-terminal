# Capture publique #542 — dossier isolé, app inchangée

[Mission #542](https://github.com/3a7i3/crypto-ia-terminal/issues/542).
[Contrat et gates](../../contracts/MARKET_PUBLIC_US_CAPTURE_542.md).
[Plan déterministe](PLAN.json).

La première variante étudie Coinbase Advanced et Bitstamp Public API pour
BTC/USD et ETH/USD Spot. Aucun alias avec USDT/USDC ou les anciennes sources.
Le plan fermé Bybit/OKX n’est ni activé ni transformé automatiquement.
Le pilote standalone ne produit pas un artifact admis par l’Operator API.

## Fichiers

| Fichier | Fonction |
| --- | --- |
| observability/market_venues/public_us.py | URLs, plan, transport fermé désactivé par défaut, métadonnées, capture/âge natif et vérification offline |
| observability/market_venues/public_us_sandbox.py | Réduction des droits du child et limites/surveillance extérieures ; aucune opération de service |
| tests/market_venues/test_public_us.py | Réponses inventées, refus, limites, provenance, horloges et intégrité |
| tests/market_venues/test_public_us_sandbox.py | Tests du noyau cible et du superviseur sans accès exchange |

## Exécution hors réseau

Depuis un checkout isolé :

```bash
python -m observability.market_venues.public_us --plan
python -m observability.market_venues.public_us --simulate --out /chemin/prive/market-venue-pilot-runs
python -m observability.market_venues.public_us --verify-run /chemin/prive/market-venue-pilot-runs/IDENTIFIANT
```

Le parent doit exister, être absolu, appartenir à l’utilisateur et être 0700,
sans symlink. Chaque run crée son sous-dossier exclusif ; aucun ancien run
n’est réécrit ou repris. La simulation utilise un temps/prix inventés, un
source_sha zéro explicitement synthétique et aucune socket.

La CLI n’a aucun mode réseau réel. Une activation admise doit passer par
un caller séparé : décision, source/plan/hashes épinglés, NTP/host/UID, parent
neuf, reçu de tentative O_EXCL avant worker, confinement sans fallback,
deadline/ressources/disque et résultat terminal. Un éventuel refus consomme
cette tentative, sans nouveau GET pour le contourner.

## Résultat privé

Les intentions, réponses capturées et reçus sont conservés avant les fichiers
cycle-0001.json à cycle-0003.json. Le reçu run-result.json distingue COMPLETED,
STOPPED et INCOMPLETE. Les sources non tentées ou invalides restent visibles.
Aucun latest.json, fichier de présentation, source API ou service n’est modifié.

Les prix natifs et dates sont observables. L’âge selon ces dates est contrôlé
à la fin de chaque cycle, sans correction ni rajeunissement par réception.
L’état des horloges/sémantiques exchange reste NOT_PROVEN/UNRESOLVED :
aucune mesure économique inter-plateformes ni permission de trading.

Les observations réelles, si l’admission du run réussit, restent privées ;
seuls résultat, compteurs, limites et hashes sont documentés sur GitHub.
Le résultat source/CI et l’éventuel résultat runtime ont des preuves distinctes.
