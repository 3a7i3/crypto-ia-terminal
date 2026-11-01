# Qualification documentaire et intervalles temporels — #546

1er novembre 2026, America/Mexico_City.
Base source vérifiée : `9af84de7d570604f03192c74cd27ae6e61a6cf33`.
Mission [#546](https://github.com/3a7i3/crypto-ia-terminal/issues/546), suite de #543/#545.

**Préparation documentaire/source uniquement.** La release isolée #545 reste
inactive ; l’app active conserve sa release1da737. Aucune nouvelle capture,
probe d’heure exchange, installation, action de service ou publication.

## Résultat préparé

- [ATTESTATIONS.json](ATTESTATIONS.json) : huit notices officielles, localisateurs,
  versions disponibles et empreintes des seuls extraits courts ;
- [Modèle et hypothèses](../../contracts/MARKET_TIME_UNCERTAINTY_546.md) :
  intervalles d’événement, âge et séparation, inconnus conservés ;
- [interval_reference.py](interval_reference.py) : algèbre pure offline ;
- [DECISION.json](DECISION.json) : statut documentaire distinct de l’admission ;
- tests synthétiques dans tests/market_venues/test_temporal_interval_reference.py.

Les hashes d’extrait portent sur les seuls fragments UTF-8 conservés.
Les avis OpenAPI ajoutent les empreintes du texte reçu ou de l’objet de
spécification extrait, conservés privés ; ce ne sont ni des empreintes des
octets HTTP wire ni une signature de l’origine. Les API v2/v3 ne donnent pas la
révision de leur documentation glissante. Une révision amont non identifiée
reste null ; le commit de cette PR versionne notre observation, sans inventer
une version amont. Les lectures documentaires ultérieures ne certifient pas
rétroactivement le comportement lors de #542.

## Lecture des sources et points fermés

CB_PUBLIC_CACHE annonce un cache d’une seconde ; #542 a conservé
max-age14400 sur huit réponses Coinbase. Cet écart documentaire/observé
reste ouvert : il ne prouve ni quatre heures d’âge, ni une erreur fournisseur,
ni une revalidation d’origine. L’option documentaire no-cache n’a été ni
ajoutée au client ni essayée. Les méthodes privées et WebSocket citées par
le fournisseur ne sont pas activées.

RFC9111_CACHE distingue le défaut arithmétique HTTP d’Age=0 lorsqu’il manque
d’une preuve d’origine ou d’âge du carnet. Dans #543, « Age absent=UNKNOWN »
désigne cette preuve manquante, pas une réécriture du calcul normatif HTTP.
max-age règle la durée de fraîcheur HTTP ; no-cache demande une validation.
La référence d’intervalles ne réimplémente pas un cache HTTP.
RFC9110_DATE porte sur le message ; une date de message ne qualifie pas
l’événement bid/ask recherché.

CHRONY42_TRACKING apporte un calcul conditionnel, pas une certification.
Les chiffres conservés de #542 donnent 867112 ns au point observé avec
arrondi extérieur ; faute de borne de variation/validité, la référence ne
propage pas cette valeur jusqu’aux carnets et ne l’utilise pas pour corriger
leurs dates. chronyc -v a seulement confirmé la version actuelle4.2, sans
contact de mesure temporelle ; la version binaire de la capture reste non attestée.

## Inconnus qui restent réels

| Sujet | État après cette étape |
| --- | --- |
| Coinbase pricebook.time | Chaîne time annotée RFC3339 Timestamp, non requise dans PriceBook ; événement/horloge/délai non attestés |
| Bitstamp microtimestamp | Unités Unix/microsecondes documentées ; événement non défini, champs non requis dans OrderBookResponse |
| Cache Coinbase | Écart entre notice et en-têtes conservés non résolu |
| Horloge source liée au carnet | Relation et incertitude non attestées |
| Continuité de borne locale | Validité et taux maximal non établis dans les pièces conservées |
| Lecture Coinbase /time | Documentée, non appelée ; lien avec l’horloge du carnet non prouvé |
| Format et app | Sortie standalone toujours non admise par le lecteur actif |

Les premières ouvertures web Bitstamp ont expiré. Une lecture documentaire
via RDC a ensuite fourni le bloc OpenAPI3.0.3 / info.versionv2 de la page.
La branche OrderBookResponse donne les unités Unix/microsecondes, sans
événement défini ni champs temporels requis. Seul le bloc documentaire
__redoc_state.spec.data a été conservé ; le contexte de page, dont des
tickers préchargés accessoires, a été écarté et ne forme aucune observation
de marché. Aucun JavaScript, widget ou WebSocket n’a été exécuté.
Ce ciblage de schémas ne vaut pas revue exhaustive de toute la page. La première lecture web de l’OpenAPI Coinbase ne prenait pas en charge YAML.
Une lecture documentaire textuelle via RDC a ensuite permis de conserver le
texte privé et de suivre la chaîne du GET public vers PriceBook.time.
OpenAPI3.1.0 / info.version0.1 est une version déclarée du document, sans
révision amont immuable attestée. L’annotation de format et le caractère
optionnel du champ sont établis dans cette chaîne ; sa signification
événementielle reste absente. Ce n’est pas une revue sémantique exhaustive du spec.
La lecture ciblée a utilisé le parseur YAML système déjà présent, sans
installation ; le venv de tests n’avait pas ce parseur. Le corps documentaire
complet reste privé, seuls empreinte et extrait court sont publiés.
Aucun client tiers n’a été utilisé comme autorité de sémantique.
Ne pas substituer les définitions de X-Auth-Timestamp, d’un trade, de FIX ou
d’un autre flux au timestamp du carnet REST considéré.

## Portée scientifique

La référence renvoie des bornes sous hypothèses, pas AVAILABLE ou CERTIFIED.
Sans composante justifiée, elle conserve null/UNRESOLVED. Des intervalles qui
se chevauchent peuvent encore permettre un grand écart ; le modèle vérifie
la borne maximale, pas seulement la possibilité d’une coïncidence.
Ses identifiants d’échelle sont des déclarations, pas des preuves d’alignement.

Aucun invariant actif n’est desserré. La signification physique des champs reste
à documenter avant toute admission de comparaison ; un nouveau GET seul ne la
prouverait pas. Une étude future d’un header de cache ou d’une sonde devra
définir ce qu’elle peut établir et restera une décision distincte.
La présentation éventuelle d’observations historiques sans métriques aurait
aussi son scope et son artifact admis propres.

## Reproduction

La référence n’importe que dataclasses ; elle n’ouvre aucun fichier, socket ou
horloge. Les tests n’appellent aucune plateforme et bloquent les connexions et
résolutions réseau usuelles. Les exemples sont synthétiques, sauf l’illustration
arithmétique explicitement conditionnelle des diagnostics Chrony conservés.

```bash
python -m pytest -q tests/market_venues/test_temporal_interval_reference.py
python -m ruff check docs/research/market_time_attestation_546/interval_reference.py \
  tests/market_venues/test_temporal_interval_reference.py
python scripts/ci/ruff_baseline_gate.py check
```

Aucun besoin de simulation réseau, de nouvelle donnée ou de démarrage de service.
#286 demeure ACTIVE autrement ; #538, la capture #542 et l’installation #545
sont consommées. Cette préparation ne les rejoue pas et n’accorde pas un merge,
une nouvelle installation, une capture ou une publication.

Validation locale finale : **43 tests PASS**, 1 warning de configuration pytest
asyncio_mode déjà présent ; Ruff et gate baseline PASS, baseline inchangée.
Les refus socket/DNS sont actifs dans les tests ; aucun test de flux réel.
