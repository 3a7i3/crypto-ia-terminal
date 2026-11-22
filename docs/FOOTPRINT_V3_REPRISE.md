# Reprise Footprint V3 et Finance V6

Cette branche part de `a213ad193a18241849659faadc70c022bb41027a` (Finance V6). Les deux commits du patch `a213ad19..dd761be1` ont été réappliqués, avec de nouveaux identifiants Git. Ils rétablissent notamment la vue BTC_USDT figée et les commandes compactes.

## Référence déployée

Le VPS sert `CAT-FOOTPRINT-V3-L1-ab941c2` via une surcharge systemd en lecture seule de `frontend/dist` sur la RC1. Le bundle JS servi correspond à celui de l'archive Footprint V3 (SHA-256 `fcf0949c44c0eaea0b3fc572278d2bfcff6b24a251b5d4172281d8f7795b6f88`). Le patch récupéré introduit « Capture figée ». La source de « Valeurs exactes », visible dans le bundle servi, reste à retrouver. Cette branche est un point de reprise, avec la parité V3 encore à établir.

- [RC1](https://github.com/3a7i3/crypto-ia-terminal/tree/release/cat-footprint-finance-v6-rc1)
- [Footprint-V3.zip](https://chatgpt.com/library?file_id=libfile_00423410d3748191a66eca176d65184b&account_id=personal)
- [Maquette validée](https://chatgpt.com/library?file_id=libfile_5f108e50436881918497097a2474f600&account_id=personal)

## Reprise par Claude Code

1. Rechercher les sources de `ab941c2`, ou comparer la branche au bundle V3 et restituer les comportements manquants. Comparer en particulier Valeurs exactes, le sélecteur de profil, le plein écran et la provenance.
2. Vérifier un build local avec `frontend/scripts/verify_rc_preservation.mjs`. Contrôler le solde PAPER 1/7/30 jours, les décisions, les ordres en attente et la réconciliation Finance.
3. Sur cette base validée, réaliser le graphique dans Marché → Microstructure. En paysage, afficher les bougies OHLC et cellules Bid × Ask au centre, le profil delta (Ask − Bid) et l’axe prix à droite, puis DeltaChg, Delta, DltaDay et Volume sous les bougies. Garder le clair par défaut et les imbalances encadrées côté dominant.
4. Comparer au rejeu MEXC M5 partiel (volumes 9 984 et 73 521, deltas +8 960 et −15 145, cumul final −6 185). Vérifier aussi une fixture synthétique de 20 bougies, le plein écran mobile et le passage PWA. Préparer une PR brouillon. La fusion et la mise en service requièrent une décision séparée.
