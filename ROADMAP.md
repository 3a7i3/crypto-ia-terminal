# ROADMAP

## Objectif

Donner une direction simple a un depot riche en modules, dashboards, scripts et documentation, sans perdre le focus sur les zones a plus forte valeur.

## Ordre de priorite des systemes

1. `quant-hedge-ai` - laboratoire quant autonome V9.1
2. `crypto_quant_v16` - stack dashboard et execution V16/V26/V30
3. `quant-ai-system` - stack containerisee
4. Dossiers legacy - reference seulement, sauf demande explicite

## Etat general du depot

- Le projet est fortement documente et couvre plusieurs systemes distincts
- La checklist d'action principale est presque entierement cochee
- Une partie importante du travail recent porte sur la fiabilisation des tests racine et la clarification de l'architecture
- Le pilotage quotidien gagne a etre centralise dans quelques fichiers courts et maintenus

## Horizon immediat

- Garder `README.md`, `ROADMAP.md`, `CURRENT_TASK.md`, `BUGS.md` et `IDEAS_PARKING.md` alignes
- Nettoyer les references de documentation cassées ou ambigues depuis la racine
- Conserver un point d'entree clair pour chaque systeme prioritaire
- Continuer la separation entre vrais tests `pytest` et validateurs manuels

## Horizon suivant

- Fiabiliser l'onboarding de bout en bout pour un nouveau poste
- Clarifier les scripts de lancement critiques sous Windows
- Rendre les health checks et diagnostics plus faciles a executer
- Reduire la duplication entre documents de demarrage et de synthese

## Phase 1 - Stabilisation

- Centraliser les points d'entree utiles par systeme
- Corriger les liens de documentation les plus visibles
- Identifier et suivre les bugs actifs dans un seul registre
- Verifier les scripts de lancement critiques
- Garder les fichiers de pilotage tres courts et actionnables

## Phase 2 - Fiabilisation

- Renforcer les verifications de sante et de diagnostic
- Ameliorer la coherence entre modules et dashboards
- Reduire les points de configuration ambigus
- Prioriser les corrections qui bloquent l'usage quotidien
- Poursuivre l'audit des tests racine encore ambigus

## Phase 3 - Industrialisation

- Mieux documenter les workflows importants
- Consolider les tests les plus utiles
- Simplifier l'onboarding et la reprise du projet
- Rendre le suivi des taches plus explicite
- Clarifier les frontieres entre logique de signal, risque, sizing et gouvernance

## Priorites actuelles

1. Garder une documentation de pilotage simple et a jour
2. Corriger les points de friction les plus visibles dans la doc racine
3. Finaliser la hygiene des tests racine et des validateurs manuels
4. Mieux separer les responsabilites d'architecture dans les moteurs de decision et de risque

## Indicateurs de progression

- Un nouveau lecteur comprend ou demarrer en moins de 5 minutes
- Les liens de la doc racine pointent vers des fichiers existants
- Les bugs connus sont traces avec un statut clair
- La tache courante est lisible en une minute
