# Passation #542 — variante de capture publique, app inchangée

31 octobre 2026, America/Mexico_City.
[Mission #542](https://github.com/3a7i3/crypto-ia-terminal/issues/542).
Source de départ : PR540 e8c4fa0f53666bde836682ab2c930077fff489bc.
Main : 1da7376829f82eacfb52794ec267be97523fb244.
Le HEAD final et sa CI sont consignés dans la PR et la mission, sans
assimiler un résultat de source à une exécution réelle.

## Adaptation

Le refus #541 est conservé : Bybit/OKX n’est pas admis depuis la VM US.
La nouvelle variante choisit explicitement Coinbase Advanced public et
Bitstamp Public API, BTC/USD et ETH/USD Spot. Le groupe USD n’est pas
USDT/USDC ; aucune ancienne ligne n’est renommée ni remplacée en silence.

[Contrat](../contracts/MARKET_PUBLIC_US_CAPTURE_542.md) et
[plan/dossier](../research/market_public_us_542/README.md).
Le collecteur est standalone : aucun fichier frontend, Operator API,
service, configuration ou artifact de présentation modifié dans ce delta.
Pas de latest.json ni de publication dans l’app.

Trois métadonnées puis trois cycles de quatre carnets au plus : 15 GET,
30 s internes, 5 s de cadence, 512 000 octets par réponse, 16 Mio de contenu.
Le processus extérieur impose deadline35s/TERM/KILL, CPU10s/AS256Mio,
fichier512Kio/64FD/core0/NPROC0 et surveillance de stockage.
Landlock ABI4 réduit les droits du seul worker UID1001, sans sudo :
écritures de contenu dans le parent isolé, connectTCP443, aucun bindTCP.
Lectures/UDP et certaines métadonnées ne sont pas couvertes ; code fixé,
environnement minimal et limites documentés, aucun certificat d’isolation globale.

Les dates natives sont conservées. L’âge est calculé à la fin du cycle ;
horloges et sémantiques exchange restent NOT_PROVEN/UNRESOLVED.
economic_metrics=null : aucune comparaison économique ou admission de trading.
Les réponses réelles éventuelles restent privées, hors GitHub et app.

## Validation locale de la préparation

- 340 tests Python PASS (cross-stack, market_venues, comparateur), dont
  58 nouveaux tests de cette variante/superviseur ; zéro skip sur la VM cible.
- Ruff des quatre nouveaux fichiers Python et gate du dépôt PASS ;
  baseline inchangée. Un import de test inutilisé a été corrigé après le
  premier refus Ruff ; aucun test ou baseline retiré.
- Simulation complète sous le vrai confinement noyau et les limites du child :
  3 cycles, 15 intentions/reçus, zéro capture en attente, cohérence locale PASS.
  Temps et prix inventés, evidence_kind=SYNTHETIC, aucun accès exchange.
- Deny probes locaux : écriture hors parent, bind TCP et connect TCP port9
  refusés ; watchdog de temps, sorties volumineuses et dossiers étrangers testés.
- Les fichiers frontend/API sont identiques au parent source. Les preuves
  UI antérieures restent de même tree ; la CI de la PR est à réévaluer au
  nouveau HEAD. Aucun nouveau build ou audit navigateur local nécessaire.
- Deux avertissements Python du venv réutilisé sont conservés : option
  asyncio_mode sans plugin et dépréciation Starlette/httpx.

## Reprise sur la VM

Remote Desktop Commander, appareil bc07f523-ad34-4c2e-9af1-0105f66d5783.
ACCESS_HANDOFF.md lu en premier ; hostname/id réels :
crypto-restore-01, lecanada26 UID1001. Aucun AGENTS applicable trouvé.
Instructions et #286 inchangés et relus dans la mission précédente ;
aucune ancienne roadmap ni permission #538 réutilisée.

Worktree : /home/lecanada26/crypto-install/worktrees/market-public-us-542-20261031
Audit : /home/lecanada26/crypto-install/audit-browser/market-public-us-542-20261031
Venv de test réutilisé : /home/lecanada26/crypto-install/envs/market-catalogue-533

À ce stade : source préparée/testée ; aucun endpoint exchange appelé.
Le caller réel doit encore épingler HEAD/plan/decision/hashes, vérifier NTP,
identité et services, créer le reçu exclusif de la seule tentative, puis
exécuter le worker confiné sous supervision. Un refus arrête sans retry.

L’autorisation de première collecte ponctuelle donnée par l’opérateur est
conservée sous les gates de #542. Elle ne publie rien dans l’app et ne
permet aucune fusion implicite ou activation permanente. Source/CI,
tentative réelle et qualification scientifique restent distinctes.
Aucun restart/reload/enable/reboot, secret/abonnement, port public,
moteur/Advisor/Telegram, stratégie/seuil/calibration, epoch/PPL/FIN,
original/sauvegarde ou ancienne VM.
