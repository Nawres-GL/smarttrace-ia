# Phase 5 — Import Excel dans SmartTrace et indicateurs enrichis

## Déjà disponible dans la Phase 4

L'import par l'interface existait déjà dans `Données sources`. Cette phase **améliore le flux existant**, sans créer de nouvelle collection parallèle ni demander une commande terminal pour les mises à jour futures.

## Pour un administrateur

1. Ouvrir **Données sources → Importer un fichier Excel**.
2. Choisir **Production**, **Livraisons** ou **Greffage**.
3. Sélectionner un fichier `.xlsx` avec **les mêmes colonnes, dans le même ordre** que le schéma validé.
4. Cliquer **Analyser les lignes — sans importer**.
5. Contrôler lignes reçues, doublons, nouvelles lignes, codes LOT et numéros de lignes proposés.
6. Si le résultat convient, cocher la confirmation et cliquer **Confirmer l'import**.
7. Vérifier les comptes Atlas et l'historique des imports, puis consulter **Registre des lots** / **Statistiques & insights**.

L'API exploite déjà :
- `POST /api/historique/imports/{kind}/preview` (body brut .xlsx)
- `POST /api/historique/imports/{kind}/confirm/{preview_id}`
- `GET /api/historique/imports/status`

Une prévisualisation est maintenant associée à l'administrateur et au type de fichier ; sa validité est limitée dans le temps. La confirmation recalcule les doublons : en cas de modification entre l'analyse et la validation, le processus demande une nouvelle prévisualisation. Les fichiers d'origine ne sont pas modifiés.

**Attention :** la comparaison par contenu exact sait ignorer une ligne déjà importée, même déplacée dans une nouvelle version Excel. Une ligne **corrigée** peut toutefois être considérée comme nouvelle : elle doit être revue par un humain ; il n'existe pas encore de workflow métier complet de mise à jour/version des enregistrements existants.

**Attention :** l'exactitude des dédoublonnages simultanés entre plusieurs administrateurs dépend aussi des contraintes d'unicité MongoDB ; le projet pilote doit être testé avec deux confirmations concurrentes avant une exposition publique.

## Mode Atlas

Après l'import initial des trois sources, définir `HISTORY_MODE=atlas` dans le `.env` **privé** du backend et redémarrer l'API. Sans cette étape, des données peuvent être importées dans Atlas mais l'application continuer à afficher les fichiers Excel locaux.

## Statistiques & insights

Les filtres **campagne/année, espèce, client, serre, unité livraison** sont disponibles.

- Production : quantités semées par espèce et variété, nombre de lots distincts, plantes nettes.
- Livraison : lignes par client, région et unité, documents distincts ; **quantités** par client/région/article et évolution mensuelle seulement si une unité de livraison est sélectionnée.
- Greffage : taux moyen et perte moyenne par serre, avec le nombre de lignes utilisées (moyenne simple, non pondérée).
- Qualité des données : lots sans numéro, livraisons non rapprochées de la production, codes LOT historiques ambigus.

Les rapprochements historiques par numéro à 5 chiffres demeurent **indicatifs**. Les statistiques sont descriptives et ne sont pas des prédictions IA. Les filtres client et serre ne s'appliquent qu'aux sources où ces champs existent : il ne faut pas interpréter la sélection filtrée comme une cohorte unique de production et livraison.

## Étapes de validation

Depuis `backend` dans un environnement Python avec les dépendances de `requirements-dev.txt` :

```powershell
python -m pytest -q tests/test_incremental_import.py tests/test_phase5_analytics.py
```

Depuis `frontend` :

```powershell
npm install
npm run build
npm run dev
```

Scénarios manuels recommandés :

1. Importer une version qui contient 100 anciennes lignes et 50 nouvelles : prévisualisation 100 doublons, 50 ajouts ; confirmer ; recommencer le même fichier : 0 ajout.
2. Importer 3 types de fichiers avec les colonnes exactes.
3. Importer un fichier invalide : message de colonnes manquantes, aucune écriture.
4. Vérifier que les nouveaux codes LOT figurent dans le registre et ouvrent leur dossier QR.
5. Filtrer les statistiques et contrôler les totaux sur un échantillon du fichier source.
6. Comparer l'interface sur smartphone, tablette et desktop.

## Prochaine phase proposée

**Phase 6 — Qualité des données et intelligence de décision** : revue des corrections Excel, rapprochement multi-sources plus fiable (campagne/variété en plus du code LOT), alertes agricoles configurables, comparaison entre campagnes, suivi d'anomalies et lien vers une fiche d'enquête.
