"""Historical data-quality and human-reconciliation API.

Admin-only until source site ownership is mapped. No guessed physical links,
no automated Excel overwrite, no fabricated agronomic events.
"""
from __future__ import annotations
from collections import defaultdict, Counter
import os
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Literal
from pymongo import ReturnDocument
from app.auth import require_role
from app.history import load_historical
from app.insights import _campaign, _num
from app.correction_review import EDITABLE
from etl.pipeline import normalize

router=APIRouter(prefix='/api/data-quality',tags=['Qualité et décisions'])
COLLECTIONS={
 'production':'historical_production_records',
 'livraison':'historical_delivery_lines',
 'greffage':'historical_grafting_records',
}

def _db(request):
    db=request.app.state.db
    if db is None: raise HTTPException(503,'Atlas requis pour la revue des données.')
    return db

def _now():return datetime.now(timezone.utc)

def _public(item):
    if not item:return None
    return {k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in item.items() if k!='_id'} | {'id':str(item['_id'])}

def compare_campaigns(p,d,g):
    result=defaultdict(lambda:{'production_rows':0,'delivery_rows':0,'grafting_rows':0,
                                'seeds_sown':0,'plants_net':0,'grafting_rate_sum':0,
                                'grafting_rate_count':0,'delivery_notes':set(),
                                'production_lots':set()})
    for kind,items in [('production',p),('delivery',d),('grafting',g)]:
        for row in items:
            key=_campaign(row)
            rec=result[key];rec[kind+'_rows']+=1
            if kind=='production':
                rec['seeds_sown']+=_num(row.get('seeds_sown'))
                rec['plants_net']+=_num(row.get('plants_net'))
                if row.get('lot_code'):rec['production_lots'].add(row['lot_code'])
            elif kind=='delivery':
                if row.get('delivery_note_number'):rec['delivery_notes'].add(str(row['delivery_note_number']))
            elif row.get('grafting_rate_pct') is not None:
                rec['grafting_rate_sum']+=_num(row['grafting_rate_pct'])
                rec['grafting_rate_count']+=1
    output=[]
    for year,row in sorted(result.items()):
        output.append({'campaign':year,'production_rows':row['production_rows'],
             'delivery_rows':row['delivery_rows'],'grafting_rows':row['grafting_rows'],
             'seeds_sown':round(row['seeds_sown'],2),'plants_net':round(row['plants_net'],2),
             'production_lots':len(row['production_lots']),
             'delivery_notes':len(row['delivery_notes']),
             'avg_grafting_rate':round(row['grafting_rate_sum']/row['grafting_rate_count'],2)
                 if row['grafting_rate_count'] else None})
    return output

def compute_alerts(p,d,g, loss_threshold=30, graft_threshold=65):
    alerts=[]
    for row in p:
        sow=_num(row.get('seeds_sown')); net=_num(row.get('plants_net'))
        if sow>0 and net>=0 and row.get('plants_net') is not None:
            # These fields are not necessarily directly comparable after staging;
            # use nonnegative percentage only as an indicative signal.
            loss=100*(sow-net)/sow
            if loss_threshold<loss<=100:
                alerts.append({'kind':'HIGH_PRODUCTION_LOSS','severity':'ATTENTION',
                    'source':'production','record_id':str(row['_id']), 'lot_code':row.get('lot_code'),
                    'value':round(loss,1),'unit':'%',
                    'message':'Écart semis/plants nets élevé ; vérifier le périmètre et les unités avant de conclure.'})
            if net>sow:
                alerts.append({'kind':'QUANTITY_INCONSISTENCY','severity':'REVUE',
                    'source':'production','record_id':str(row['_id']), 'lot_code':row.get('lot_code'),
                    'value':round(net-sow,1),'unit':'plants',
                    'message':'Plants nets supérieurs aux semences déclarées ; vérifier les définitions des champs.'})
    for row in g:
        rate=row.get('grafting_rate_pct')
        if rate is not None and _num(rate)<graft_threshold:
            alerts.append({'kind':'LOW_GRAFT_RATE','severity':'ATTENTION',
                'source':'greffage','record_id':str(row['_id']), 'lot_code':row.get('lot_code'),
                'value':round(_num(rate),1),'unit':'%',
                'message':'Taux de greffage inférieur au seuil indicatif configuré.'})
    prod={str(x['lot_code']) for x in p if x.get('lot_code')}
    for row in d:
        if row.get('lot_code') and str(row['lot_code']) not in prod:
            alerts.append({'kind':'UNMATCHED_DELIVERY','severity':'REVUE',
                'source':'livraison','record_id':str(row['_id']), 'lot_code':row.get('lot_code'),
                'value':None,'unit':'',
                'message':'Aucune production avec le même code LOT ; absence de lien confirmé.'})
    return alerts

def candidate_matches(production, deliveries):
    bycode=defaultdict(list)
    for p in production:
        if p.get('lot_code'):bycode[str(p['lot_code'])].append(p)
    items=[]
    for d in deliveries:
        candidates=bycode.get(str(d.get('lot_code')),[]) if d.get('lot_code') else []
        refs=sorted({str(x.get('lot_ref') or x['_id']) for x in candidates})
        article=d.get('article_key') or normalize(d.get('article'))
        mismatch=bool(article and candidates and all((x.get('article_key') or normalize(x.get('article')))!=article for x in candidates))
        kind='MISSING_CODE' if not d.get('lot_code') else 'UNMATCHED' if not candidates else 'AMBIGUOUS' if len(refs)>1 else 'ARTICLE_CONFLICT' if mismatch else 'CANDIDATE'
        if kind!='CANDIDATE':
            items.append({'delivery_id':str(d['_id']), 'lot_code':d.get('lot_code'),
                'client':d.get('client'),'article':d.get('article'),
                'status':kind,'candidates':[{'id':str(x['_id']), 'ref':x.get('lot_ref'),
                   'article':x.get('article'), 'campaign':_campaign(x)} for x in candidates[:12]],
                'total_candidates':len(candidates)})
    return items

@router.get('/overview')
def overview(request:Request, campaign:str=Query('',max_length=100),
             loss_threshold:int=Query(30,ge=1,le=100),graft_threshold:int=Query(65,ge=0,le=100),
             user=Depends(require_role('admin'))):
    if os.getenv('HISTORY_MODE','excel').lower()!='atlas':
        raise HTTPException(409,'Activez HISTORY_MODE=atlas après migration pour analyser et revoir les archives centralisées.')
    p,d,g=load_historical()
    series=compare_campaigns(p,d,g)
    if campaign:
        p=[r for r in p if _campaign(r)==campaign]
        d=[r for r in d if _campaign(r)==campaign]
        g=[r for r in g if _campaign(r)==campaign]
    alerts=compute_alerts(p,d,g,loss_threshold,graft_threshold)
    matches=candidate_matches(p,d)
    counts=Counter(x['kind'] for x in alerts)
    return {'campaigns':series,'alerts_total':len(alerts),'alerts_by_kind':dict(counts),
            'alerts':alerts[:100], 'alerts_truncated':len(alerts)>100,
            'match_issues_total':len(matches),'match_issues':matches[:100],
            'thresholds':{'loss':loss_threshold,'graft':graft_threshold},
            'notes':['Seuils indicatifs ; aucun diagnostic automatique.',
                     'Écart semis/plants nets : contrôler les unités et les étapes du processus.',
                     'Les rapprochements Excel restent des hypothèses tant qu’ils ne sont pas revus.']}

class MatchDecision(BaseModel):
    action:Literal['CONFIRM_LINK','REJECT_LINK']
    production_record_id:str|None=None
    reason:str=Field(min_length=10,max_length=1000)

@router.post('/matches/{delivery_id}/decision')
def decide_match(delivery_id:str,body:MatchDecision,request:Request,
                 user=Depends(require_role('admin'))):
    db=_db(request)
    row=db.historical_delivery_lines.find_one({'_id':delivery_id})
    if not row:raise HTTPException(404,'Ligne de livraison introuvable.')
    target=None
    if body.action=='CONFIRM_LINK':
        if not body.production_record_id:raise HTTPException(422,'Choisissez une référence de production.')
        target=db.historical_production_records.find_one({'_id':body.production_record_id})
        if not target or not row.get('lot_code') or row.get('lot_code')!=target.get('lot_code'):
            raise HTTPException(422,'Le lot de production ne correspond pas au code déclaré.')
    original=db.historical_match_decisions.find_one({'_id':delivery_id})
    new_target=str(target['_id']) if target else None
    if original and original.get('decision')==body.action and original.get('productionRecordId')==new_target:
        return _public(original)
    moment=_now()
    record={'deliveryRecordId':delivery_id,'decision':body.action,
            'productionRecordId':new_target,
            'reason':body.reason,'reviewedBy':str(user['_id']),'reviewedAt':moment,
            'lotCode':row.get('lot_code')}
    entry={'at':moment,'by':str(user['_id']), 'from':original.get('decision') if original else None,
           'fromProductionId':original.get('productionRecordId') if original else None,
           'to':body.action,'toProductionId':new_target,'reason':body.reason}
    db.historical_match_decisions.update_one({'_id':delivery_id},
        {'$set':record,'$push':{'history':entry}},upsert=True)
    return _public(db.historical_match_decisions.find_one({'_id':delivery_id}))

@router.get('/matches/decisions')
def list_match_decisions(request:Request,user=Depends(require_role('admin'))):
    return [_public(r) for r in _db(request).historical_match_decisions.find({}).limit(200)]

@router.get('/corrections')
def list_corrections(request:Request,status:Literal['PENDING','APPROVED','REJECTED','ACCEPTED_NEW']='PENDING',
                     limit:int=Query(100,ge=1,le=200),user=Depends(require_role('admin'))):
    return [_public(x) for x in _db(request).historical_correction_reviews.find({'status':status})
            .sort('createdAt',-1).limit(limit)]

class CorrectionResolution(BaseModel):
    action:Literal['APPROVE_CORRECTION','ACCEPT_NEW','REJECT']
    reason:str=Field(min_length=10,max_length=1000)

@router.post('/corrections/{review_id}/resolve')
def resolve_correction(review_id:str,body:CorrectionResolution,request:Request,
                       user=Depends(require_role('admin'))):
    db=_db(request)
    review=db.historical_correction_reviews.find_one({'_id':review_id})
    if not review:raise HTTPException(404,'Proposition introuvable.')
    if review['status']!='PENDING':raise HTTPException(409,'Cette proposition a déjà été traitée.')
    kind=review['kind'];collection=db[COLLECTIONS[kind]]
    original=collection.find_one({'_id':review['originalId']})
    if not original:raise HTTPException(409,'Enregistrement source manquant.')
    new=review['newRecord']
    if body.action=='APPROVE_CORRECTION':
        if review.get('ambiguous'):
            raise HTTPException(422,'Clé métier ambiguë : acceptez une nouvelle ligne ou écartez-la après contrôle.')
        changes={field:new.get(field) for field in EDITABLE[kind] if new.get(field)!=original.get(field)}
        # A correction may only update approved projection fields, never the original raw values.
        if not changes:raise HTTPException(409,'Aucun champ corrigeable différent.')
        for field,value in changes.items():
            if value is not None and (field.startswith(('seeds_','trays_','plants_','grafted_')) or field in ('item_quantity','tray_quantity')):
                if not isinstance(value,(float,int)) or isinstance(value,bool) or value<0:
                    raise HTTPException(422,f'{field}: quantité non numérique ou négative.')
            if field in ('grafting_rate_pct','grafting_loss_pct','total_loss_pct') and value is not None:
                if not isinstance(value,(float,int)) or not 0<=value<=100:
                    raise HTTPException(422,f'{field}: pourcentage attendu entre 0 et 100.')
        res=collection.update_one({'_id':original['_id'],'contentFingerprint':original.get('contentFingerprint')},
             {'$set':changes,'$addToSet':{'acceptedContentFingerprints':new['contentFingerprint']},
              '$push':{'correctionHistory':{'at':_now(),'by':str(user['_id']),
                 'reason':body.reason,'before':{k:original.get(k) for k in changes},
                 'after':changes,'importReviewId':review_id}}})
        if res.matched_count!=1:raise HTTPException(409,'La ligne a changé : relancez la revue.')
        state='APPROVED'
    elif body.action=='ACCEPT_NEW':
        from pymongo.errors import DuplicateKeyError
        try:collection.insert_one(new)
        except DuplicateKeyError:raise HTTPException(409,'Cette ligne a déjà été enregistrée.')
        state='ACCEPTED_NEW'
    else:state='REJECTED'
    db.historical_correction_reviews.update_one({'_id':review_id,'status':'PENDING'},
        {'$set':{'status':state,'resolvedBy':str(user['_id']),
                 'resolvedAt':_now(),'resolutionReason':body.reason}})
    if state in ('APPROVED','ACCEPTED_NEW'):
        from app.unified_registry import sync_historical_registry
        sync_historical_registry(db,{new.get('lot_code')})
    return {'id':review_id,'status':state}

class OpenIssue(BaseModel):
    kind:str=Field(min_length=2,max_length=80)
    source:Literal['production','livraison','greffage']
    record_id:str=Field(min_length=1,max_length=180)
    lot_code:str|None=Field(default=None,max_length=60)
    title:str=Field(min_length=5,max_length=240)
    notes:str=Field(default='',max_length=3000)

@router.post('/issues',status_code=201)
def open_issue(payload:OpenIssue,request:Request,user=Depends(require_role('admin'))):
    db=_db(request)
    row=db[COLLECTIONS[payload.source]].find_one({'_id':payload.record_id})
    if not row:raise HTTPException(404,'Ligne source introuvable.')
    if payload.lot_code and payload.lot_code!=row.get('lot_code'):
        raise HTTPException(422,'Code LOT incohérent avec la source.')
    existing=db.historical_quality_issues.find_one({'kind':payload.kind, 'recordId':payload.record_id,
                                                    'status':{'$ne':'RESOLU'}})
    if existing:return _public(existing)
    item={'_id':str(uuid4()),'revision':0,'kind':payload.kind,'source':payload.source,'recordId':payload.record_id,
          'lotCode':row.get('lot_code'),'title':payload.title,'notes':payload.notes,
          'status':'OUVERT','createdBy':str(user['_id']),'createdAt':_now(),
          'updatedAt':_now(),'history':[]}
    db.historical_quality_issues.insert_one(item)
    return _public(item)

@router.get('/issues')
def list_issues(request:Request,user=Depends(require_role('admin'))):
    return [_public(r) for r in _db(request).historical_quality_issues.find({}).sort('createdAt',-1).limit(200)]

class IssueUpdate(BaseModel):
    revision:int=Field(ge=0)
    status:Literal['OUVERT','EN_ANALYSE','RESOLU']
    notes:str=Field(max_length=3000)

@router.patch('/issues/{id}')
def update_issue(id:str,payload:IssueUpdate,request:Request,user=Depends(require_role('admin'))):
    db=_db(request)
    if payload.status=='RESOLU' and not payload.notes.strip():
        raise HTTPException(422,'Ajoutez une conclusion documentée avant résolution.')
    changed=db.historical_quality_issues.find_one_and_update({'_id':id,'revision':payload.revision},
        {'$inc':{'revision':1},'$set':{'status':payload.status,'notes':payload.notes,'updatedAt':_now()},
         '$push':{'history':{'by':str(user['_id']),'at':_now(),'status':payload.status}}},
         return_document=ReturnDocument.AFTER)
    if not changed:raise HTTPException(409,'Dossier modifié ou introuvable : actualisez puis réessayez.')
    return _public(changed)
