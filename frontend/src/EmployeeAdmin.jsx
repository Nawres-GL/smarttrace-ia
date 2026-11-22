import React, {useEffect, useState} from 'react';
import './phase4.css';
const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
export const roleNames = {
  admin:'Administrateur', production:'Production', qualite:'Contrôle qualité',
  logistique:'Logistique & livraisons', lecture:'Consultation seulement'
};
const roleDescriptions = {
  admin:'Gestion des utilisateurs, des sites, des historiques, des opérations et des corrections.',
  production:'Réception, semis, germination, transferts, interventions, pertes et greffage.',
  qualite:'Lecture des lots affectés et validation ou blocage des quantités commercialisables.',
  logistique:'Lecture des lots affectés, préparation, livraison et retours clients.',
  lecture:'Lecture seule des lots opérationnels des sites attribués, sans création ni modification.'
};

export default function EmployeeAdmin({token}) {
  const [users,setUsers]=useState([]),[sites,setSites]=useState([]);
  const [form,setForm]=useState({name:'',email:'',role:'lecture',site_codes:['S01']});
  const [password,setPassword]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const [siteForm,setSiteForm]=useState({code:'',name:''});
  async function api(path, method='GET', body) {
    const response=await fetch(`${API}${path}`, {method,headers:{Authorization:`Bearer ${token}`, ...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
    const json=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof json.detail==='string'?json.detail:(json.errors||[]).map(x=>x.message).join(' · ')||`Erreur HTTP ${response.status}`);
    return json;
  }
  async function reload(){const [u,s]=await Promise.all([api('/api/auth/users'),api('/api/sites')]);setUsers(u);setSites(s);}
  useEffect(()=>{reload().catch(e=>setError(e.message));},[token]);
  async function create(e){e.preventDefault();setBusy(true);setError('');setPassword(null);try{const result=await api('/api/auth/users','POST',form);setPassword({name:result.name,value:result.temporary_password});setNotice(`Compte créé : ${result.name}. L'employé devra changer son mot de passe lors de la première connexion.`);setForm({name:'',email:'',role:'lecture',site_codes:['S01']});await reload();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function createSite(e){e.preventDefault();setBusy(true);setError('');try{const row=await api('/api/sites','POST',siteForm);setNotice(`Site ${row.code} créé. Vous pouvez maintenant y affecter des employés.`);setSiteForm({code:'',name:''});await reload();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function toggle(user){if(!window.confirm(`${user.disabled?'Réactiver':'Désactiver'} ${user.name} ?`))return;setBusy(true);setError('');setPassword(null);try{await api(`/api/auth/users/${user.id}`,'PATCH',{disabled:!user.disabled});setNotice('Compte mis à jour.');await reload();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function changeRole(user,role){setBusy(true);setError('');try{await api(`/api/auth/users/${user.id}`,'PATCH',{role});await reload();setNotice('Rôle actualisé.');}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function changeSites(user,values){setBusy(true);setError('');try{await api(`/api/auth/users/${user.id}`,'PATCH',{site_codes:values});await reload();setNotice('Sites actualisés.');}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="p4-admin">
    <div className="p4-heading"><div><span className="p4-eyebrow">ADMINISTRATION · ACCÈS SÉCURISÉS</span><h1>Collaborateurs & permissions</h1><p>Créez un compte pour chaque employé, attribuez son rôle et les sites qu'il peut consulter.</p></div><span className="p4-count">{users.length} comptes</span></div>
    {error&&<div className="p4-alert" role="alert">{error}</div>}{notice&&<div className="p4-positive" role="status">{notice}</div>}
    {password&&<div className="p4-credential" role="status"><b>Mot de passe provisoire — {password.name}</b><p>Copiez-le une seule fois et transmettez-le de manière sécurisée à l'employé. Il ne sera plus affiché après fermeture.</p><div><code>{password.value}</code><button type="button" onClick={()=>navigator.clipboard?.writeText(password.value)}>Copier</button><button type="button" onClick={()=>setPassword(null)}>Masquer</button></div></div>}
    <div className="p4-admin-layout"><section className="p4-panel"><h2>Créer un compte employé</h2><p className="p4-note">Pas d'inscription publique : seul un administrateur peut créer un compte. Le système génère un mot de passe temporaire et demande de le remplacer au premier accès.</p><form className="p4-admin-form" onSubmit={create}><label>Nom complet<input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} required minLength="2" placeholder="Prénom Nom" /></label><label>Adresse e-mail<input value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))} required type="email" placeholder="prenom@entreprise.tn" /></label><label>Rôle<select value={form.role} onChange={e=>setForm(f=>({...f,role:e.target.value}))}>{Object.entries(roleNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><div className="p4-role-hint">{roleDescriptions[form.role]}</div><fieldset><legend>Sites autorisés</legend>{sites.map(site=><label className="p4-checkbox" key={site.code}><input type="checkbox" checked={form.site_codes.includes(site.code)} onChange={e=>setForm(f=>({...f,site_codes:e.target.checked?[...f.site_codes,site.code]:f.site_codes.filter(x=>x!==site.code)}))}/>{site.name} ({site.code})</label>)}</fieldset><button type="submit" className="p4-main-button" disabled={busy||!form.site_codes.length}>Créer le collaborateur</button></form></section>
    <section className="p4-panel"><h2>Comptes existants</h2><p className="p4-note">Vous pouvez changer les rôles, les sites et désactiver des comptes sans supprimer leur historique d'activité.</p><div className="p4-users">{users.map(u=><article className="p4-user" key={u.id}><div className="p4-user-head"><div><b>{u.name}</b><small>{u.email}</small></div><span className={u.disabled?'p4-tag off':'p4-tag'}>{u.disabled?'Désactivé':'Actif'}</span></div><div className="p4-user-tools"><label>Rôle<select disabled={busy} value={u.role} onChange={e=>changeRole(u,e.target.value)}>{Object.entries(roleNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label>Accès aux sites<select multiple disabled={busy} value={u.site_codes} onChange={e=>changeSites(u,[...e.target.selectedOptions].map(x=>x.value))} aria-label={`Sites de ${u.name}`}>{sites.map(s=><option key={s.code} value={s.code}>{s.name}</option>)}</select></label><button type="button" className="p4-outline-button" disabled={busy} onClick={()=>toggle(u)}>{u.disabled?'Réactiver':'Désactiver'}</button></div>{u.must_change_password&&<small className="p4-pending">Mot de passe personnel à définir</small>}</article>)}</div></section></div>
    <section className="p4-panel"><h2>Sites de production</h2><p className="p4-note">Royal Plants peut disposer de plusieurs sites. Créez-les ici avant d'affecter leurs collaborateurs.</p><div className="p4-site-list">{sites.map(s=><span key={s.code}>{s.code} · {s.name}</span>)}</div><form onSubmit={createSite} className="p4-admin-form p4-site-form"><label>Code site<input value={siteForm.code} onChange={e=>setSiteForm(f=>({...f,code:e.target.value.toUpperCase()}))} minLength="2" maxLength="20" pattern="[A-Za-z0-9_-]+" placeholder="S02" required /></label><label>Nom site<input value={siteForm.name} onChange={e=>setSiteForm(f=>({...f,name:e.target.value}))} minLength="2" placeholder="Royal Plants — Serres Sud" required/></label><button type="submit" className="p4-main-button" disabled={busy}>Créer le site</button></form></section>
    <section className="p4-panel p4-permissions"><h2>Guide des rôles</h2>{Object.entries(roleDescriptions).map(([k,v])=><div key={k}><b>{roleNames[k]}</b><p>{v}</p></div>)}<p className="p4-note">Les historiques Excel avec les noms de clients restent réservés à l'administrateur tant que leur correspondance exacte aux sites n'est pas établie.</p></section>
  </div>;
}
