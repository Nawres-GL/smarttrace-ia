"""Read-only draft investigation export from a site-authorized operational lot.

The Royal Plants external investigation template is used as a business reference;
this generated draft is NOT a signed or validated investigation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from .auth import authenticated_user, database, require_site, require_role
from .operations import serial_lot

router = APIRouter(prefix="/api/investigations", tags=["Enquetes et rapports"])

SECTIONS = (
    ("Identification et réclamation", (
        ("Commercial", "À compléter"), ("Agriculteur / client", "À compléter"),
        ("Superficie / nombre de plants concernés", "À compléter"),
        ("Date de réclamation", "À compléter"), ("Date de plantation", "À compléter"),
        ("Sujet de la réclamation", "À compléter"),
        ("Réclamation antérieure", "À vérifier"),
        ("Analyse de la situation et avis de l'ingénieur", "À compléter et valider par l'ingénieur"),
    )),
    ("I. Partie agronomique — inspection sur le terrain", (
        ("Période de plantation", "À compléter"), ("Stockage avant repiquage", "À compléter"),
        ("Orientation des lignes", "À compléter"), ("Nature du sol", "À compléter"),
        ("Culture abritée", "À compléter"), ("Culture intercalaire", "À compléter"),
        ("Situation hydraulique", "À compléter"), ("Nature et salinité de l'eau", "À compléter"),
        ("Fumure de fond et quantité", "À compléter"), ("Désherbage chimique", "À compléter"),
        ("Culture sur banquette", "À compléter"), ("Conditions climatiques", "À compléter"),
        ("Deux dernières fertigations", "À compléter"), ("Deux derniers traitements au champ", "À compléter"),
        ("Culture au voisinage", "À compléter"), ("Précédent cultural", "À compléter"),
        ("Remarques agronomiques", "À compléter"),
    )),
    ("Avis administratif et signatures", (
        ("Avis administratif", "À compléter et valider"),
        ("Signature ingénieur", "Non recueillie"),
        ("Signature agriculteur", "Non recueillie"),
        ("Validation administration", "Non recueillie"),
    )),
)


def prepare_report(db, lot_id: str, user: dict) -> dict:
    lot = db.production_lots.find_one({"_id": lot_id})
    if not lot:
        raise HTTPException(404, "Lot opérationnel introuvable.")
    require_site(user, lot["siteCode"])
    doc = serial_lot(lot)
    # Only retrieve related records in the same permitted site.
    matching = {"$or": [
        {"subjectType":"PRODUCTION_LOT","subjectId":lot_id},
        {"subjectType":"SEED_LOT","subjectId":lot.get("seedLotId")},
        {"details.parent_lot_ids":lot_id}, {"details.lot_fils_id":lot_id},
    ], "siteCode":lot["siteCode"]}
    events = list(db.trace_events.find(matching).sort("occurredAtDt", 1).limit(500))
    deliveries = list(db.deliveries.find({"lotId":lot_id, "siteCode":lot["siteCode"]}).limit(300))
    relevant = []
    for e in events:
        relevant.append({
            "type":str(e.get("eventType") or "Événement"),
            "date":str(e.get("occurredAt") or e.get("occurredAtDt") or "Non renseignée")[:25],
            "state":"Enregistré dans MongoDB",
        })
    return {
        "lot":doc, "events":relevant,
        "deliveries":[{
            "client":str(d.get("client") or "Non renseigné"),
            "quantity":str(d.get("quantity") or d.get("quantityDelivered") or "Non renseignée"),
            "date":str(d.get("deliveredOn") or d.get("createdAt") or "Non renseignée")[:25],
            "reference":str(d.get("deliveryNote") or d.get("deliveryNoteNumber") or "Non renseignée")
        } for d in deliveries],
        "generated_at":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def _header_values(data: dict):
    lot=data["lot"]
    return [
        ("Référence du lot de production",lot.get("code")),
        ("Culture / espèce",lot.get("species")),
        ("Variété",lot.get("variety")),
        ("Article",lot.get("article")),
        ("Campagne",lot.get("campaign")),
        ("Site de production",lot.get("site_code")),
        ("Quantité semée (si enregistrée)",lot.get("quantity_sown")),
        ("Stock actuel déclaré",lot.get("plants_in_stock") if not data.get("historical") else "Indéterminé — Excel historique"),
        ("Date de livraison", "Voir tableau des livraisons déclarées" if data.get("historical") else "À vérifier dans les pièces de livraison"),
    ]


def _docx_bytes(data:dict)->bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc=Document()
    sec=doc.sections[0]
    sec.top_margin=sec.bottom_margin=Cm(1.8)
    sec.left_margin=sec.right_margin=Cm(2)
    normal=doc.styles["Normal"]
    normal.font.name="Aptos";normal.font.size=Pt(9)
    t=doc.add_heading("ROYAL PLANTS — FICHE D’ENQUÊTE (EXTERNE)",0)
    t.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("BROUILLON AUTOMATIQUE — à compléter et valider avant diffusion")
    doc.add_paragraph("Date de génération : " + data["generated_at"])
    doc.add_heading("Dossier de traçabilité / Partie pépinière",1)
    tab=doc.add_table(rows=0,cols=2);tab.style="Light Shading Accent 1"
    for label,val in _header_values(data):
        row=tab.add_row().cells;row[0].text=label;row[1].text=str(val) if val is not None else "Non renseigné"
    if data.get('case'):
        c=data['case']
        doc.add_heading('Enquête enregistrée — '+str(c.get('status','BROUILLON')).replace('_',' '),1)
        for k,label in [('subject','Réclamation'),('customer','Client'),('region','Région'),
                        ('claim_date','Date réclamation'),('planting_date','Date plantation'),
                        ('affected_quantity','Quantité concernée'),('agronomic_notes','Agronomie'),
                        ('soil_notes','Sol'),('irrigation_notes','Irrigation'),('climate_notes','Climat'),
                        ('treatments_notes','Traitements'),('investigation_notes','Constat'),
                        ('engineer_opinion','Avis ingénieur'),('administrative_opinion','Avis administratif')]:
            p=doc.add_paragraph();p.add_run(label+ ' : ').bold=True
            p.add_run(str(c.get(k)) if c.get(k) not in (None,'') else '.........................................')
    for heading,items in SECTIONS:
        doc.add_heading(heading,1)
        for label,val in items:
            p=doc.add_paragraph();p.add_run(label+" : ").bold=True;p.add_run(val)
    doc.add_heading("II. Partie pépinière — chronologie enregistrée" if not data.get("historical") else "II. Partie pépinière — lignes de semis Excel (non certifiées)",1)
    if data["events"]:
        tab=doc.add_table(rows=1,cols=3);tab.style="Table Grid"
        for c,v in zip(tab.rows[0].cells,["Opération","Date","Référence Excel / non certifié" if data.get("historical") else "Statut de l’opération"]):c.text=v
        for e in data["events"]:
            row=tab.add_row().cells
            for c,v in zip(row,[e["type"],e["date"],e["state"]]):c.text=v
    else:doc.add_paragraph("Aucun événement opérationnel enregistré pour ce lot.")
    if data.get('historical'):
        doc.add_heading('Production et greffage déclarés dans Excel (non certifiés)',1)
        for label, rows, keys in (
            ('Production',data.get('production_excel',[]),('lot_ref','article','variety','sowing_date','seeds_sown','plants_net')),
            ('Greffage',data.get('grafting_excel',[]),('lot_ref','article','variety','greenhouse','grafting_rate_pct','plants_net'))):
            doc.add_heading(label,2)
            if rows:
                tb=doc.add_table(rows=1,cols=len(keys));tb.style='Table Grid'
                for cell,key in zip(tb.rows[0].cells,keys):cell.text=key.replace('_',' ')
                for item in rows:
                    for cell,key in zip(tb.add_row().cells,keys):cell.text=str(item.get(key) if item.get(key) is not None else '—')
            else:doc.add_paragraph('Aucune ligne correspondante.')
    doc.add_heading("Livraisons associées",1)
    if data["deliveries"]:
        tab=doc.add_table(rows=1,cols=4);tab.style="Table Grid"
        for c,v in zip(tab.rows[0].cells,["Client","Quantité source","Date","Bon de livraison"]):c.text=v
        for d in data["deliveries"]:
            row=tab.add_row().cells
            for c,v in zip(row,[d["client"],d["quantity"],d["date"],d["reference"]]):c.text=v
    else:doc.add_paragraph("Aucune livraison rattachée dans la base opérationnelle consultée.")
    doc.add_paragraph(data.get("source_note", "Source : journal opérationnel MongoDB. Rapport brouillon à compléter et valider."))
    out=BytesIO();doc.save(out);return out.getvalue()


def _pdf_bytes(data: dict) -> bytes:
    """Produce an attractive, honest, fillable-on-paper investigation draft.

    Fields absent from source remain blank dotted writing lines, not made-up data.
    Both historical and operational reports retain explicit provenance labels.
    """
    from xml.sax.saxutils import escape
    from pathlib import Path
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, PageBreak, HRFlowable, KeepTogether)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font = 'Helvetica'
    boldfont = 'Helvetica-Bold'
    regular = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    if regular.exists() and bold.exists():
        if 'RPDejaVu' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('RPDejaVu', str(regular)))
            pdfmetrics.registerFont(TTFont('RPDejaVuBold', str(bold)))
        font, boldfont = 'RPDejaVu', 'RPDejaVuBold'

    green=colors.HexColor('#194B39'); mid=colors.HexColor('#368263')
    pale=colors.HexColor('#E9F3ED'); ink=colors.HexColor('#223A30')
    grey=colors.HexColor('#637B6F'); line=colors.HexColor('#D5E4DA')
    buff=colors.HexColor('#FFF5E3')
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=41,rightMargin=41,
          topMargin=61,bottomMargin=46,title='Royal Plants - Fiche d enquête externe',
          author='Royal Plants SmartTrace')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RPLead',fontName=boldfont,fontSize=17,leading=23,textColor=green,spaceAfter=7))
    styles.add(ParagraphStyle(name='RPSection',fontName=boldfont,fontSize=11,leading=16,textColor=green,spaceBefore=13,spaceAfter=9))
    styles.add(ParagraphStyle(name='RPBody',fontName=font,fontSize=8.5,leading=13,textColor=ink,spaceAfter=5))
    styles.add(ParagraphStyle(name='RPLabel',fontName=boldfont,fontSize=8.1,leading=12,textColor=green))
    styles.add(ParagraphStyle(name='RPValue',fontName=font,fontSize=8.4,leading=13,textColor=ink))
    styles.add(ParagraphStyle(name='RPSmall',fontName=font,fontSize=7.3,leading=11,textColor=grey))
    styles.add(ParagraphStyle(name='RPWhite',fontName=boldfont,fontSize=8,leading=11,textColor=colors.white))
    styles.add(ParagraphStyle(name='RPWarning',fontName=font,fontSize=8,leading=12,textColor=colors.HexColor('#75531E')))
    P=lambda t,style='RPBody':Paragraph(escape(str(t)),styles[style])
    story=[]
    historical=bool(data.get('historical'))
    lot=data['lot']
    def heading(txt):story.append(P(txt,'RPSection'))
    def pfield(label,value=None):
        value = str(value).strip() if value is not None else ''
        if not value or value in ('Non renseigné','À compléter','None','—','Indéterminé — Excel historique'):
            value='.................................................................................................'
        t=Table([[P(label,'RPLabel'),P(value,'RPValue')]],colWidths=[177,352],hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),
                              ('TOPPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,-1),.3,line)]))
        story.append(t)
    def writing(label,rows=2):
        story.append(P(label,'RPLabel'))
        for _ in range(rows):story.append(P('.....................................................................................................................','RPSmall'))
        story.append(Spacer(1,4))
    def tabular(header,records,widths=None,max_rows=16):
        if not records:
            story.append(P('Aucune donnée correspondante dans les sources disponibles.','RPSmall'));return
        rows=[[P(x,'RPWhite') for x in header]]
        for record in records[:max_rows]:rows.append([P(str(x) if x not in (None,'') else '—','RPSmall') for x in record])
        t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),green),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,pale]),
         ('GRID',(0,0),(-1,-1),.3,line),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),
         ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.append(t)
        if len(records)>max_rows:story.append(P(f'{len(records)-max_rows} ligne(s) supplémentaires non affichées dans ce résumé.','RPSmall'))

    story.append(P('FICHE D’ENQUÊTE','RPLead'))
    story.append(P('EXTERNE  |  Document préparatoire pour investigation et validation humaine','RPSmall'))
    # Printable external investigation sheet; completion and review remain human tasks.
    # Provenance remains available in the application and through the historical source references.
    if not historical:
        note='Informations opérationnelles à contrôler par le responsable avant validation.'
        callout=Table([[P(note,'RPWarning')]],colWidths=[529])
        callout.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),buff),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#E9D8AC')),
            ('LEFTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
        story.append(Spacer(1,9));story.append(callout)
    story.append(P('Généré le : '+data.get('generated_at','—'),'RPSmall'))
    case=data.get('case') or {}
    if case:
        heading('Dossier d’enquête · '+str(case.get('status','BROUILLON')).replace('_',' '))
        for k,label in [('subject','Sujet de réclamation'),('customer','Agriculteur / client'),
                        ('region','Région'),('claim_date','Date réclamation'),
                        ('planting_date','Date plantation'),('affected_quantity','Quantité concernée')]:
            pfield(label,case.get(k))
    heading('01  Identification du dossier')
    for label,value in _header_values(data):pfield(label,value)
    heading('02  Réclamation & constat initial')
    for name,field in [('Commercial',None),('Agriculteur / client','customer'),('Région','region'),
                       ('Date de réclamation','claim_date'),('Date de plantation','planting_date')]:
        pfield(name,case.get(field) if field else None)
    pfield('Réclamation antérieure (Oui / Non)')
    if case.get('subject'):pfield('Sujet de la réclamation',case['subject'])
    else:writing('Sujet de la réclamation',3)
    if case.get('investigation_notes'):pfield('Constat / analyse',case['investigation_notes'])
    else:writing('Analyse initiale et avis de l’ingénieur',3)
    story.append(PageBreak())

    story.append(P('I. PARTIE AGRONOMIQUE','RPLead'))
    story.append(P('Observations terrain — à renseigner par le personnel habilité','RPSmall'))
    for label in ('Période de plantation','Stockage avant repiquage','Orientation des lignes',
                  'Nature du sol (sableux / argileux / autre)','Culture abritée (Oui / Non)',
                  'Culture intercalaire','Situation hydraulique / irrigation',
                  'Nature et salinité de l’eau','Fumure de fond et quantités',
                  'Désherbage chimique','Culture sur banquette (Oui / Non)',
                  'Température, précipitations et vent'):
        pfield(label)
    if case.get('agronomic_notes'):pfield('Notes agronomiques',case['agronomic_notes'])
    if case.get('soil_notes'):pfield('Observations du sol',case['soil_notes'])
    if case.get('irrigation_notes'):pfield('Irrigation',case['irrigation_notes'])
    if case.get('climate_notes'):pfield('Climat',case['climate_notes'])
    if case.get('treatments_notes'):pfield('Traitements observés',case['treatments_notes'])
    writing('Les deux dernières fertigations — produit, dose et date',2)
    writing('Les deux derniers traitements au champ — produit, dose et date',2)
    writing('Cultures au voisinage, précédent cultural et remarques',2)
    story.append(PageBreak())

    story.append(P('II. PARTIE PÉPINIÈRE','RPLead'))
    story.append(P('Informations rattachées au lot sélectionné. Vérifier les références et les unités.','RPSmall'))
    heading('Production / semis')
    prod=data.get('production_excel',[]) if historical else []
    if historical:
        tabular(['Lot source','Article / variété','Date de semis','Qté semée'],[
          [r.get('lot_ref'),r.get('article') or r.get('variety'),r.get('sowing_date'),r.get('seeds_sown')]
          for r in prod],[126,175,107,121],12)
    else:
        pfield('Référence du lot',lot.get('code'));pfield('Date de semis',lot.get('sown_on'))
        pfield('Quantité semée',lot.get('quantity_sown'))
    heading('Greffage et événements associés')
    if historical:
        graft=data.get('grafting_excel',[])
        tabular(['Lot','Variété','Serre','Taux déclaré'],[
            [r.get('lot_ref'),r.get('variety') or r.get('article'),r.get('greenhouse'),
             (str(r.get('grafting_rate_pct'))+' %') if r.get('grafting_rate_pct') is not None else None]
            for r in graft],[137,171,105,116],10)
    else:
        tabular(['Opération','Date','État enregistré'],[[e.get('type'),e.get('date'),e.get('state')]
            for e in data.get('events',[])],[200,150,179],12)
    heading('Livraisons rattachées')
    tabular(['Agriculteur / client','Quantité / unité','Date','N° BL'],[
        [d.get('client'),d.get('quantity'),d.get('date'),d.get('reference')]
        for d in data.get('deliveries',[])],[180,125,112,112],14)
    story.append(PageBreak())
    story.append(P('III. CONCLUSIONS & VALIDATION','RPLead'))
    writing('Pièces jointes / photos (références des annexes)',3)
    if case.get('administrative_opinion'):pfield('Avis administratif',case['administrative_opinion'])
    else:writing('Avis administratif',5)
    if case.get('engineer_opinion'):pfield('Conclusion de l’ingénieur',case['engineer_opinion'])
    else:writing('Conclusion de l’ingénieur / actions proposées',4)
    story.append(Spacer(1,17))
    t=Table([[P('Ingénieur','RPLabel'),P('Agriculteur','RPLabel'),P('Administration','RPLabel')],
       [P('Signature : ...................','RPSmall'),P('Signature : ...................','RPSmall'),P('Visa : ...................','RPSmall')]],
       colWidths=[176,176,177])
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,line),('BACKGROUND',(0,0),(-1,0),pale),
       ('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),19)]))
    story.append(t)
    story.append(Spacer(1,19))
    provenance=data.get('source_note','Source : données opérationnelles MongoDB, à examiner.')
    story.append(P('PROVENANCE & LIMITES','RPLabel'))
    # Avoid overlong notes spilling into multiple pages; keep precise compact source warning.
    story.append(P(provenance[:1000],'RPSmall'))
    story.append(P('Brouillon généré par SmartTrace. Les champs laissés libres ne sont pas des données manquantes inventées; ils nécessitent une enquête réelle. Ce document ne remplace pas une signature ou approbation.','RPSmall'))
    def page(canvas,doc):
        canvas.saveState();w,h=A4
        canvas.setFillColor(green);canvas.rect(0,h-39,w,39,fill=1,stroke=0)
        canvas.setFont(boldfont,11);canvas.setFillColor(colors.white);canvas.drawString(42,h-25,'ROYAL PLANTS  /  SMARTTRACE')
        canvas.setStrokeColor(line);canvas.line(41,34,w-41,34)
        canvas.setFont(font,7.1);canvas.setFillColor(grey)
        canvas.drawString(41,22,'Fiche d’enquête externe  •  Brouillon non signé')
        canvas.drawRightString(w-41,22,f'Page {doc.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return out.getvalue()


@router.get('/lots/{lot_id}/export')
def export_lot_investigation(lot_id:str, request:Request,
    format:str=Query('pdf',pattern='^(pdf|docx)$'),user=Depends(authenticated_user)):
    data=prepare_report(database(request),lot_id,user)
    content=_docx_bytes(data) if format=='docx' else _pdf_bytes(data)
    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document' if format=='docx' else 'application/pdf'
    filename='fiche-enquete-'+''.join(x for x in data['lot']['code'] if x.isalnum() or x in '-_')+'.'+format
    return StreamingResponse(BytesIO(content), media_type=mime,
        headers={'Content-Disposition':f'attachment; filename="{filename}"',
                 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@router.get('/historique/lots/{lot_code}/export')
def export_historical_investigation(lot_code: str, request: Request,
    format: str = Query('pdf', pattern='^(pdf|docx)$'),
    user=Depends(require_role('admin'))):
    """Admin-only draft of a historical Excel lot. Does NOT activate or certify stock."""
    from . import history
    source = history.detail(lot_code)
    summary = source['summary']
    production = source['production']
    graft = source['grafting']
    deliveries = source['deliveries']
    first = production[0] if production else (graft[0] if graft else {})
    def unique(items, name):
        return ', '.join(sorted({str(v[name]) for v in items if v.get(name) not in (None, '')})) or None
    lot = {
        'code':summary['lot_code'],
        'species':unique(production,'species') or unique(graft,'species'),
        'variety':unique(production,'variety') or unique(graft,'variety'),
        'article':unique(production,'article') or unique(graft,'article'),
        'campaign':summary.get('campaign'),
        'site_code':unique(production,'production_site_or_depot'),
        'quantity_sown':None, 'plants_in_stock':None,
    }
    info = {'lot':lot, 'generated_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
      'historical':True, 'events':[], 'deliveries':[
        {'client':d.get('client') or 'Non renseigné', 'quantity':f"{d.get('item_quantity') if d.get('item_quantity') is not None else '—'} {d.get('unit') or '(unité non précisée)'}",
        'date':d.get('document_date') or 'Non renseignée', 'reference':d.get('delivery_note_number') or 'Non renseigné'}
        for d in deliveries[:300]],
      'historical_rows': [
        {'type':'Semis déclaré (Excel)', 'date':row.get('sowing_date') or 'Non renseignée', 'state':f"Ligne source {row.get('source_row', '—')} · non certifié"}
        for row in production[:300]],
      'production_excel':production[:50], 'grafting_excel':graft[:50],
      'source_note':f"SOURCE : ARCHIVES EXCEL HISTORIQUES. Rapprochement candidat par code à cinq chiffres {summary['lot_code']}. {len(production)} lignes production, {len(graft)} lignes greffage et {len(deliveries)} lignes livraison. Détails limités aux 50 premières lignes par source et aux 300 premières livraisons dans cet export. Les champs manquants restent à vérifier; les signatures ne sont pas collectées. " + ' '.join(source.get('warnings', []))
    }
    # Historical production rows are historical evidence, NOT operational trace_events.
    info['events'] = info.pop('historical_rows')
    content = _docx_bytes(info) if format == 'docx' else _pdf_bytes(info)
    mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if format == 'docx' else 'application/pdf'
    return StreamingResponse(BytesIO(content), media_type=mime,
       headers={'Content-Disposition':f'attachment; filename="fiche-enquete-historique-{summary["lot_code"]}.{format}"',
                'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})
