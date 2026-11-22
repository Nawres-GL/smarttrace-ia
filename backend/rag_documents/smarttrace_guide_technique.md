# Guide technique SmartTrace — démonstration, non validé comme procédure Royal Plants

Ce document sert uniquement à tester la recherche documentaire. Il décrit le fonctionnement du prototype logiciel et ne constitue **pas** une procédure agricole ou commerciale officielle.

## Consultation de l’historique

Les données Excel historiques sont lues sans modifier les fichiers originaux. Le rapprochement entre production, production greffée et livraison utilise un code commun à cinq chiffres. Ce rapprochement n'établit pas à lui seul la généalogie ou l'origine physique d'un lot. Dans le pilote, les historiques Excel sont réservés au rôle administrateur car les sites d'origine ne sont pas établis.

## Enregistrement d'une opération

Le module CamemBERT interprète une phrase en français et propose un brouillon modifiable. Un collaborateur habilité corrige ou complète les champs. L'opération est ensuite vérifiée par les endpoints FastAPI selon le rôle, le site, la disponibilité du stock et les règles métier. Le chatbot RAG n'enregistre aucune opération.

## Certificat Blockchain

Les nouveaux événements d'audit enregistrés dans MongoDB sont mis en file d'attente pour Hyperledger Fabric. Tant que le réseau et le worker n'ont pas confirmé une preuve relue sur la blockchain, le statut ne doit pas être décrit comme certifié. Les informations des Excel historiques ne sont pas des transactions Fabric.
