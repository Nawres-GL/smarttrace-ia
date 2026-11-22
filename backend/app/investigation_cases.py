"""Saved investigation cases for operational lots (no Fabric dependency).

Case records do not modify stock, production history or historical Excel archives.
A closed case means an internal review was recorded, NOT a digital signature.
"""
from datetime import date, datetime, timezone
from io import BytesIO
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pymongo import DESCENDING

from .auth import authenticated_user, database, require_site
from .operations import ensure_lot
from .investigations import prepare_report, _pdf_bytes, _docx_bytes

router = APIRouter(prefix='/api/investigations/cases', tags=['Enquêtes et réclamations'])
STATUS = ('BROUILLON','EN_COURS','A_REVOIR','CLOTURE')

class CreateCase(BaseModel):
    lot_id: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=5, max_length=240)
    customer: str = Field(default='', max_length=160)
    region: str = Field(default='', max_length=160)
    claim_date: date

class UpdateCase(BaseModel):
    revision: int = Field(ge=0)
    subject: str = Field(min_length=5, max_length=240)
    customer: str = Field(default='', max_length=160)
    region: str = Field(default='', max_length=160)
    claim_date: date
    planting_date: date | None = None
    affected_quantity: int | None = Field(default=None, ge=0)
    prior_complaint: bool | None = None
    agronomic_notes: str = Field(default='', max_length=4000)
    irrigation_notes: str = Field(default='', max_length=2500)
    soil_notes: str = Field(default='', max_length=2500)
    climate_notes: str = Field(default='', max_length=2500)
    treatments_notes: str = Field(default='', max_length=2500)
    investigation_notes: str = Field(default='', max_length=4000)
    engineer_opinion: str = Field(default='', max_length=4000)
    administrative_opinion: str = Field(default='', max_length=4000)
    status: Literal['BROUILLON','EN_COURS','A_REVOIR','CLOTURE'] = 'BROUILLON'

FIELDS = ('subject','customer','region','planting_date','affected_quantity','prior_complaint',
          'agronomic_notes','irrigation_notes','soil_notes','climate_notes','treatments_notes',
          'investigation_notes','engineer_opinion','administrative_opinion','status')

def stamp():
    return datetime.now(timezone.utc)

def public(c):
    return {k: (v.isoformat() if isinstance(v,(datetime,date)) else v)
            for k,v in c.items() if k != '_id'}

def get_case(db, identifier, user):
    case = db.investigation_cases.find_one({'_id':identifier})
    if not case:
        raise HTTPException(404,'Enquête introuvable.')
    require_site(user, case['siteCode'])
    return case

@router.get('')
def list_cases(request: Request, lot_id: str | None = Query(default=None),
               user=Depends(authenticated_user)):
    query = {} if user.get('role')=='admin' else {'siteCode': {'$in':user.get('siteCodes',[])}}
    if lot_id:
        ensure_lot(database(request),lot_id,user)
        query['lotId'] = lot_id
    return [public(x) for x in database(request).investigation_cases.find(query)
            .sort('updatedAt',DESCENDING).limit(250)]

@router.post('',status_code=201)
def create_case(data: CreateCase, request: Request, user=Depends(authenticated_user)):
    if user.get('role') not in ('admin','production','qualite'):
        raise HTTPException(403,'Votre rôle ne peut pas ouvrir une enquête.')
    db=database(request)
    lot=ensure_lot(db,data.lot_id,user)
    if data.claim_date > date.today():
        raise HTTPException(422,'La date de réclamation ne peut pas être future.')
    moment=stamp()
    record={'_id':str(uuid4()),'id':None,'lotId':lot['_id'],'lotCode':lot['code'],
            'siteCode':lot['siteCode'],'subject':data.subject.strip(),
            'customer':data.customer.strip(),'region':data.region.strip(),
            'claim_date':data.claim_date.isoformat(),'status':'BROUILLON',
            'createdAt':moment,'updatedAt':moment,'createdBy':user['_id'],
            'updatedBy':user['_id'],'revision':0,'history':[]}
    record['id']=record['_id']
    db.investigation_cases.insert_one(record)
    return public(record)

@router.get('/{case_id}')
def detail_case(case_id: str, request:Request,user=Depends(authenticated_user)):
    return public(get_case(database(request),case_id,user))

@router.patch('/{case_id}')
def update_case(case_id:str, payload:UpdateCase, request:Request,
                user=Depends(authenticated_user)):
    if user.get('role') not in ('admin','production','qualite'):
        raise HTTPException(403,'Lecture seule pour votre rôle.')
    db=database(request)
    original=get_case(db,case_id,user)
    if original.get('status')=='CLOTURE':
        raise HTTPException(409,'Enquête clôturée : création d’un avenant requise pour toute modification.')
    if payload.claim_date > date.today() or (payload.planting_date and payload.planting_date>date.today()):
        raise HTTPException(422,'Les dates constatées ne peuvent pas être futures.')
    if payload.planting_date and payload.planting_date > payload.claim_date:
        raise HTTPException(422,'La date de plantation ne peut pas suivre la date de réclamation.')
    if payload.status == 'CLOTURE':
        if user.get('role') not in ('admin','qualite'):
            raise HTTPException(403,'Clôture réservée au contrôle qualité ou à l’administration.')
        if not payload.engineer_opinion.strip() or not payload.administrative_opinion.strip():
            raise HTTPException(422,'Avis ingénieur et administratif requis pour clôturer.')
    if payload.status=='A_REVOIR' and not payload.investigation_notes.strip():
        raise HTTPException(422,'Ajoutez une synthèse avant de demander une revue.')
    values=payload.model_dump()
    revision=values.pop('revision')
    values['claim_date']=payload.claim_date.isoformat()
    values['planting_date']=payload.planting_date.isoformat() if payload.planting_date else None
    values.update(updatedAt=stamp(),updatedBy=user['_id'])
    if payload.status=='CLOTURE':
        values.update(closedAt=stamp(),closedBy=user['_id'])
    res=db.investigation_cases.update_one({'_id':case_id,'revision':revision,'status':{'$ne':'CLOTURE'}},
        {'$set':values,'$inc':{'revision':1},'$push':{'history':{'at':stamp(),
          'by':user['_id'],'from':original.get('status'),'to':payload.status}}})
    if res.matched_count!=1:
        raise HTTPException(409,'Enquête modifiée par une autre personne : actualisez avant de réessayer.')
    return public(get_case(db,case_id,user))

@router.get('/{case_id}/export')
def export_case(case_id:str, request:Request,
                format:Literal['pdf','docx']=Query('pdf'),user=Depends(authenticated_user)):
    db=database(request)
    case=get_case(db,case_id,user)
    info=prepare_report(db,case['lotId'],user)
    info['case']=public(case)
    info['source_note']='Données de production enregistrées dans SmartTrace ; observations issues du dossier d’enquête saisi par un utilisateur autorisé.'
    data = _pdf_bytes(info) if format=='pdf' else _docx_bytes(info)
    mime='application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return StreamingResponse(BytesIO(data),media_type=mime,headers={
        'Content-Disposition':f'attachment; filename="enquete-{case_id}.{format}"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
