import React,{useState} from 'react';
import './phase4.css';
const data={
 dashboard:['Vue générale','Comprendre les volumes de données historiques et accéder rapidement au registre des lots.','Consultez les indicateurs, puis ouvrez « Registre des lots » pour explorer une culture ou un lot.'],
 lots:['Registre des lots','Retrouver un lot historique avec ses données de production franc, de greffage et de livraison.','Choisissez la campagne, puis l’espèce, puis l’article/variété. Les lots restent visibles sans filtre. Cliquez sur une carte.'],
 production:['Production active','Enregistrer les opérations sur des lots vivants et consulter leur stock et leur historique auditable.','Réceptionnez des semences, créez un semis, sélectionnez un lot et enregistrez chaque opération réelle.'],
 quality:['Contrôle qualité','Décider quels plants peuvent être commercialisés après inspection.','Ouvrez un lot, renseignez l’état sanitaire, l’homogénéité et la quantité approuvée, puis validez.'],
 delivery:['Préparation & livraison','Réserver des quantités approuvées, confirmer une livraison ou traiter un retour.','Préparez une commande, ouvrez son lot, sélectionnez la préparation avant de déclarer la livraison.'],
 sources:['Données sources','Identifier les trois fichiers Excel historiques utilisés sans les modifier.','Vérifiez la provenance des informations et les distinctions entre données historiques et opérations nouvelles.'],
 architecture:['Traçabilité des lots','Consulter les opérations enregistrées, les QR codes et les dossiers des lots.','Choisissez un lot opérationnel pour afficher sa chronologie et télécharger sa fiche. Le contrôle des empreintes est local.'],
 employees:['Collaborateurs','Accorder uniquement les droits nécessaires à chaque employé.','Créez un compte avec un rôle et des sites. Transmettez le mot de passe provisoire de manière sécurisée.'],
 assistant:['Assistant NLP','Transformer une description agricole en proposition structurée sans modifier les stocks.','Saisissez une opération en français, vérifiez le lot et les valeurs, puis ouvrez son formulaire. Une confirmation humaine est obligatoire.'],
 profile:['Mon compte','Maintenir des identifiants personnels et éviter le partage de comptes.','Changez votre mot de passe; vous devrez vous reconnecter ensuite.'],
};
export default function PageGuide({page}){const [open,setOpen]=useState(true);const v=data[page];if(!v)return null;return <section className="p4-guide"><button type="button" className="p4-guide-toggle" onClick={()=>setOpen(!open)} aria-expanded={open}><span>ⓘ &nbsp; Guide d'utilisation · {v[0]}</span><span>{open?'Masquer −':'Afficher +'}</span></button>{open&&<div className="p4-guide-body"><div><b>Pourquoi cette page ?</b><p>{v[1]}</p></div><div><b>Comment l’utiliser ?</b><p>{v[2]}</p></div></div>}</section>}
