# Proposition de PR — revue seulement, non publiée

Titre : **Simplifier Machine et le Laboratoire quantitatif en français, avec tableaux mobiles et preuves repliables**

Base : `main` à `69f16dc9ebcc665848f3fb38d5fba3bf586abf45`.
Branche : `ux/machine-laboratoire-fr`.

L'ouverture de l'application exigeait de parcourir de nombreux petits panneaux pour comprendre la situation. La page d'entrée devient une synthèse Machine regroupée autour de l'état, des finances et du marché ; les preuves techniques restent accessibles à la demande. CryptoRadar et les stratégies utilisent un tableau unique adapté au mobile, avec filtres, défilement contenu et fiches détaillées. Les libellés de présentation sont français, sans changer les clés API ou l'autorité des snapshots.

Les historiques absents sont annoncés comme indisponibles. Une entrée de démonstration isolée propose des courbes et une répartition explicitement fictives, sans collecteur ni connexion runtime. Le contrat futur d'historique/répartition/filiation est documenté comme brouillon non implémenté.

Validation : 415 tests frontend, 96 tests cross-stack, 7 tests transport/PWA, TypeScript et les deux builds ; 128 contrôles navigateur aux largeurs 320/390/820/1440 ; preuves visuelles existantes pertinentes et E2E HTTP local passent. Galerie avant/après synthétique et résultats détaillés dans `APP_UX_FR_REVIEW_2026-10-07.md`.

Périmètre source/frontend seulement. Aucun VPS, changement financier/scientifique producteur, déploiement, certification runtime ou L4. U8 non autorisé ; #286 reste actif. Pas de push ou merge automatique.
