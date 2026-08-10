# Checklist de validation manuelle – Dashboard 3D Evolution

## 1. Navigation générale
- [ ] Accès à la page d’accueil du dashboard 3D
- [ ] Navigation entre panels via les boutons (Supervision, BotDoctor, Multi-Monde, Quant V16, Terminal V12, Feedback)

## 2. Sidebar et utilitaires
- [ ] Bouton "🔄 Recharger les données CSV" fonctionne et recharge les données
- [ ] Bouton "📖 Afficher le tutoriel" affiche bien le tutoriel
- [ ] Message d’aide sur le format CSV visible

## 3. Sélection et filtres
- [ ] Sélection du monde à visualiser (selectbox)
- [ ] Slider de génération à afficher fonctionne
- [ ] Slider de fitness fonctionne et filtre les stratégies
- [ ] Multiselect des espèces fonctionne
- [ ] Presets d’analyse rapide (Top 10 fitness, sharpe, drawdown) affichent les bons résultats

## 4. Navigation avancée
- [ ] Boutons "⬅️ Monde précédent" et "Monde suivant ➡️" fonctionnent
- [ ] Animation générationnelle (lecture auto, slider de vitesse) fonctionne

## 5. Visualisations et exports
- [ ] Visualisation 3D s’affiche sans erreur
- [ ] Export PNG/SVG/CSV/QR code fonctionne
- [ ] Clustering 3D (KMeans, DBSCAN, Agglomerative) fonctionne et affiche les clusters
- [ ] Heatmap 2D TP/SL fonctionne
- [ ] Analyse temporelle de la diversité fonctionne
- [ ] Comparatif multi-monde fonctionne

## 6. Aide et gestion des erreurs
- [ ] Expander "ℹ️ Aide & Astuces" visible et utile
- [ ] Message d’erreur si données manquantes dans results/
- [ ] Message d’erreur si colonnes critiques absentes
- [ ] Message d’alerte si peu ou aucune stratégie après filtrage
- [ ] Message d’aide avec lien vers CSV_POPULATION_FORMAT.md en cas d’erreur

## 7. Tutoriel et documentation
- [ ] Accès facile à la documentation et au tutoriel depuis la sidebar
- [ ] Lien vers CSV_POPULATION_FORMAT.md fonctionnel

---
Cochez chaque point lors de vos tests pour garantir une expérience utilisateur robuste et sans bug.
