# Fichiers modifiés — Phase 5

| Fichier | Statut | Fonction |
|---|---|---|
| `backend/app/historical_imports.py` | Modifié | Prévisualisation enrichie, échantillons de nouveaux LOT, confirmation liée à l'admin, contrôle de fraîcheur |
| `backend/app/insights.py` | Modifié | Filtres et nouvelles statistiques, contrôle des unités de livraison |
| `frontend/src/SourceImports.jsx` | Modifié | Parcours analyser → consulter les différences → confirmer avec une case explicite, historique des imports |
| `frontend/src/InsightsDashboard.jsx` | Modifié | Filtres réactifs, indicateurs de qualité, graphique par variété et par serre, vue livraison par unité |
| `frontend/src/data-intelligence.css` | Modifié | Styles responsive et accessibles pour imports, filtres et indicateurs |
| `backend/tests/test_phase5_analytics.py` | Ajouté | Tests de filtres et d'unités |
| `docs/PHASE5_IMPORTS_INSIGHTS.md` | Ajouté | Guide administrateur et limites |
| `docs/PHASE5_CHANGED_FILES.md` | Ajouté | Liste des changements |

Les routes principales, le registre unifié, les QR historiques, l'authentification et les opérations existantes sont conservés.
