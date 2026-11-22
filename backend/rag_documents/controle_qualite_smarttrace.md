# Contrôle qualité avant préparation et livraison — fonctionnement du logiciel SmartTrace

**Statut : guide applicatif de démonstration, NON VALIDÉ comme procédure qualité agricole officielle de Royal Plants.** Il décrit uniquement les étapes et validations déjà implémentées par FastAPI. Il ne remplace pas l'inspection physique, les règles internes ou l'approbation du responsable qualité.

## Étape 1 — Identifier le lot

Dans « Production active », ouvrir un lot opérationnel autorisé appartenant à un site accessible. Vérifier que la production ou la germination a été enregistrée et que le stock disponible est cohérent. Les lots des fichiers Excel ne deviennent pas automatiquement du stock opérationnel.

## Étape 2 — Réaliser l'inspection et saisir les observations

Le collaborateur habilité au rôle **qualité** remplit le formulaire de contrôle : date de contrôle, quantité inspectée, quantité commercialisable approuvée, état sanitaire (`SAIN`, `A_SURVEILLER`, `NON_CONFORME`), homogénéité (`HOMOGENE`, `HETEROGENE`, `A_VERIFIER`) et observations. La quantité inspectée ne doit pas dépasser le stock disponible, et la quantité approuvée ne peut pas dépasser la quantité inspectée.

## Étape 3 — Décision humaine de conformité

Dans SmartTrace, une décision positive exige un état sanitaire **SAIN** et une homogénéité **HOMOGENE**, avec une quantité commercialisable positive. Sans approbation, la quantité approuvée doit être zéro et le lot est marqué **BLOQUE**. La date du contrôle ne peut pas être dans le futur ou avant le semis. Les préparations en cours peuvent empêcher de modifier ce contrôle. L'assistant IA n'approuve jamais un lot automatiquement.

## Étape 4 — Préparation commerciale

La préparation d'une commande est accessible au rôle **logistique** seulement si `qualityStatus` vaut `CONFORME`. Les quantités sont limitées par le stock dans l'emplacement choisi et par le solde commercialisable approuvé. Le préparateur renseigne le client, la référence de commande, l'emplacement, la quantité et éventuellement plateaux et palettes.

## Étape 5 — Livraison et confirmation

La livraison exige une préparation existante, un lot toujours conforme et des quantités effectivement réservées et disponibles. Le collaborateur renseigne le bon de livraison, le transporteur, le véhicule, le réceptionnaire, la date de livraison et confirme explicitement la réception client. Les événements restent non certifiés Fabric tant que la preuve n'a pas été vérifiée sur un réseau opérationnel.

**Important :** cette séquence couvre les contrôles du logiciel, pas un protocole phytosanitaire ou un référentiel de certification officiel.
