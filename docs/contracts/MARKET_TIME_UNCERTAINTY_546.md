# Modèle de référence d’incertitude temporelle — #546

**DESIGN_ONLY / OFFLINE_REFERENCE / NON_ADMIS.** Ce modèle prolonge la
[proposition #543](MARKET_PUBLIC_US_ADMISSION_543.md).
Il n’est importé par aucun pilote, publisher, reader ou frontend.
Il ne modifie ni une stratégie, ni un seuil actif, ni une calibration.

[Attestations documentaires](../research/market_time_attestation_546/ATTESTATIONS.json) ·
[Dossier et décision](../research/market_time_attestation_546/README.md) ·
[Référence exécutable](../research/market_time_attestation_546/interval_reference.py).

## 1. Domaine et hypothèses

Tout nombre temporel du modèle est un entier en nanosecondes.
Span[lo,hi] est un intervalle fermé ; bool, float, NaN et intervalles inversés
sont refusés. Les bornes de calcul sont arrondies vers l’extérieur.
Une borne manquante reste None/UNRESOLVED ; elle n’est pas remplacée par zéro.

Window conserve un identifiant explicite d’échelle commune. Deux fenêtres
d’échelles différentes ne sont pas combinées. Déclarer le même identifiant ne
prouve pas la relation des horloges ; celle-ci doit être étayée séparément,
avec source, sens de l’offset, validité et incertitude. Un libellé UTC seul
ne certifie pas l’alignement physique.

Les fonctions font de l’algèbre sur des hypothèses fournies ; elles n’attestent
ni la véracité de ces hypothèses, ni une permission d’exécution.
WITHIN_ASSUMPTIONS n’est pas une admission scientifique ou opérationnelle.
L’identité des instruments, la cohérence des bodies et le format de publication
gardent leurs contrôles distincts.

## 2. Du champ natif à l’intervalle d’événement

Convention : o = horloge_source - échelle_commune.
Le champ natif sérialise t ; son erreur de quantification additive q est bornée.
L est le délai non négatif entre l’événement recherché et l’événement daté
par le champ. Son sens et ses composantes doivent être documentés.

Avec o dans [o0,o1], q dans [q0,q1] et L dans [L0,L1] :

`E = [t + q0 - o1 - L1, t + q1 - o0 - L0]`.

L’inclusion est conservatrice sans supposer d’indépendance statistique.
Si des composantes sont corrélées, l’intervalle peut être plus large que
nécessaire ; aucune réduction de corrélation n’est appliquée ici.
Si la signification du champ ou une borne est inconnue, E reste inconnu.
Une référence de document ou un booléen fourni par un caller ne remplace
pas une preuve de cette signification.

Une résolution connue ne fournit pas automatiquement le mode d’arrondi.
Par exemple, une troncature explicitement attestée au microseconde peut
justifier q=[0,999] ns ; ce n’est pas un défaut appliqué aux plateformes.
La référence conserve les neuf décimales possibles en arithmétique entière.

L ne doit inclure qu’un délai non déjà couvert. Si t date l’état du carnet,
un séjour ultérieur en cache ne décale pas cet événement : l’âge mesuré
depuis l’événement tient déjà compte du temps écoulé. Ne pas ajouter ce séjour
une seconde fois. Une date de message nécessiterait, elle, une relation bornée
vers l’état du carnet ; Date HTTP ne l’apporte pas automatiquement.
Un cache long ou Age absent ne prouvent pas à eux seuls un carnet périmé ;
l’usage du champ natif exige toujours sa propre qualification.

## 3. Borne ponctuelle locale et propagation conditionnelle

L’attestation CHRONY42_TRACKING donne une formule conditionnelle.
La référence `chrony_point_bound_ns` additionne la valeur absolue de
System time, root dispersion et la moitié de root delay, arrondie vers le haut.
Elle ne lit pas Chrony et ne règle aucune horloge.

Sur les nombres conservés de #542 : 1928 + 800163 + 130041/2 =
867111.5 ns, soit **867112 ns** avec arrondi conservateur.
Ce résultat est un diagnostic conditionnel au point observé, sans preuve
de continuité ni validation de l’horloge de l’exchange.

Une propagation peut seulement utiliser une borne de variation r explicitement
justifiée et valide sur une durée d : `B(d)=B0+ceil(d*r/10^9)`, r en ppb.
Si r ou sa validité manque, aucune borne future n’est calculée. Skew/RMS,
fréquence estimée et réglages par défaut ne sont pas promus en garanties.
Le modèle suppose le domaine de validité établi par le caller ; il ne le certifie pas.

## 4. Âge et séparation

Pour une fenêtre de lecture N=[n0,n1] et d’événement E=[e0,e1] sur la même échelle :

`âge = [n0-e1, n1-e0]`.

Les valeurs négatives sont conservées. La classification refuse la certitude
si un futur ou un dépassement d’âge reste possible. Un budget d’âge est
obligatoire et explicite ; aucun seuil de trading n’est fourni par défaut.

Pour A=[a0,a1], B=[b0,b1] :

`séparation_min = max(0, a0-b1, b0-a1)` ;
`séparation_max = max(abs(a0-b1), abs(a1-b0))`.

Un chevauchement donne une possibilité de coïncidence, pas une garantie.
A=B=[-1000,1000] permet des événements séparés de 2000 ns.
Le critère conservateur exige que toute la plage admissible respecte un budget
explicite. Les classifications de référence restent conditionnelles.

Le plan US #542 ne reçoit aucun max_skew implicite du profil Bybit/OKX.
Aucun seuil numérique nouveau n’est adopté ou ajusté sur les trois cycles réels.
Il n’est calculé ici ni prix, ni spread, ni score, ni profit.

## 5. Application et non-application

Pour #542 : sémantiques natives et bornes d’horloge exchange non attestées,
propagation locale continue non justifiée. Les fenêtres d’événement et d’âge
qualifiées restent donc nulles. Les âges apparents historiques déjà publiés
sont conservés, sans être remplacés par des âges certifiés ou corrigés.
Les métadonnées temporelles GitHub/VM de #545 ne sont pas réalignées arbitrairement.

Une implémentation future devra lier ses attestations à la version de flux,
au roster, aux horloges et à leur domaine temporel, et tester leur expiration.
Aucune fonction de ce fichier ne fait cette admission, ne valide le contrat
MarketVenueComparison, ne choisit un chemin actif ou ne déclenche une capture.
