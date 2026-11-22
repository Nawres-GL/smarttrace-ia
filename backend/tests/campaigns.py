"""Royal Plants agricultural campaign: C25 = 2024-10-01 through 2025-09-30.

Use the date of sowing for a production lot. Never infer a campaign from
suffix /25 or from a delivery when a sowing date is available.
"""
from datetime import date, datetime


def parse_business_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def campaign_for_date(value):
    day = parse_business_date(value)
    if day is None:
        return None
    return f"C{(day.year + (day.month >= 10)) % 100:02d}"


def campaign_bounds(campaign):
    if not campaign or len(campaign) != 3 or campaign[0] != "C" or not campaign[1:].isdigit():
        raise ValueError("Format de campagne attendu : C25")
    end_year = 2000 + int(campaign[1:])
    return date(end_year - 1, 10, 1), date(end_year, 9, 30)


def inferred_lot_campaign(production, grafting, deliveries):
    """Return (campaign, provenance). Source dates are evaluated by priority.

    The returned campaign is an index/display value, not a certified
    agronomic statement. Delivery-only codes use the earliest delivery date.
    """
    for rows, field, source in (
        (production, 'sowing_date', 'date_semis'),
        (production, 'germination_date_out', 'date_sortie_germination'),
        (grafting, 'validated_on', 'validation_greffage'),
        (deliveries, 'document_date', 'date_document_livraison'),
    ):
        dates = [parse_business_date(r.get(field)) for r in rows]
        dates = [d for d in dates if d]
        if dates:
            campaigns = {campaign_for_date(d) for d in dates}
            # Multiple source rows with dates from different campaigns
            # are ambiguous. Do not silently pick one.
            if len(campaigns) != 1:
                return None, 'dates_contradictoires'
            return next(iter(campaigns)), source
    return None, 'date_absente'
