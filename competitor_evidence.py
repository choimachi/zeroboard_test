# -*- coding: utf-8 -*-
"""Read-only, conservative extraction of publicly provided note page metadata.
No full-text scraping, no purchase, no sales inference, no API call.
"""
import html
import re
from datetime import datetime

DATE_KEYS = ('article:published_time', 'datePublished', 'date', 'pubdate', 'publish_date')


def _walk_jsonld(nodes):
    def walk(x, depth=0):
        if depth > 12:
            return
        if isinstance(x, list):
            for child in x[:80]:
                yield from walk(child, depth + 1)
        elif isinstance(x, dict):
            yield x
            for val in x.values():
                if isinstance(val, (dict, list)):
                    yield from walk(val, depth + 1)
    for node in nodes:
        yield from walk(node)


def _safe_date(raw):
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not re.match(r'^\d{4}-\d\d-\d\d(?:$|[Tt ])', value):
        return None
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value[:35]
    except ValueError:
        return None


def extract(doc, raw_html=''):
    """Return evidence with explicit provenance and uncertainty.
    Only JSON-LD explicit Offer price is treated as a structured *candidate*.
    """
    dates = []
    for key in DATE_KEYS:
        parsed = _safe_date(doc.meta.get(key))
        if parsed:
            dates.append({'value': parsed, 'source': 'HTML meta '+key})
    for obj in _walk_jsonld(doc.jsonld):
        for key in ('datePublished', 'dateCreated'):
            parsed = _safe_date(obj.get(key))
            if parsed and (obj.get('@type') or key == 'datePublished'):
                dates.append({'value': parsed, 'source': 'JSON-LD '+key})
    unique_dates = list({x['value']: x for x in dates}.values())[:4]
    # Description is only a short page-provided marketing snippet, not paid article text.
    desc = doc.meta.get('og:description') or doc.meta.get('description') or ''
    desc = re.sub(r'\s+', ' ', html.unescape(str(desc))).strip()[:240]
    # note's visible page excerpt is not a reliable way to infer price/paywall.
    return {
        'published_date_claim': unique_dates[0]['value'] if unique_dates else None,
        'publication_evidence': unique_dates,
        'public_description_excerpt': desc,
        'structured_prices': _extract_prices(doc.jsonld),
        'paywall_status': '\u672a\u78ba\u8a8d\uff08\u516c\u958b\u60c5\u5831\u304b\u3089\u6709\u6599\u30fb\u7121\u6599\u3092\u5224\u5b9a\u3057\u3066\u3044\u307e\u305b\u3093\uff09',
        'description_source': 'HTML og:description/description' if desc else '\u672a\u53d6\u5f97',
        'evidence_limits': '\u516c\u958b\u65e5\u306e\u5019\u88dc\u306f\u8a18\u4e8b\u5074\u30e1\u30bf\u30c7\u30fc\u30bf\u306e\u7533\u544a\u3067\u3042\u308a\u72ec\u7acb\u691c\u8a3c\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\u516c\u958b\u4fa1\u683c\u306e\u5019\u88dc\u306fJSON-LD Offer\u306e\u307f\u3002\u8ca9\u58f2\u4ef6\u6570\u30fb\u53ce\u76ca\u30fb\u5b9f\u9700\u8981\u306f\u672a\u78ba\u8a8d\u3002'
    }


def _extract_prices(jsonld):
    offers = []
    for obj in _walk_jsonld(jsonld):
        kind = obj.get('@type')
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(isinstance(t, str) and t.lower().endswith('offer') for t in kinds):
            continue
        raw = obj.get('price')
        if raw is None or isinstance(raw, bool):
            continue
        price = str(raw).strip()
        if not re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?', price):
            continue
        currency = str(obj.get('priceCurrency', '')).upper()
        if currency and not re.fullmatch(r'[A-Z]{3}', currency):
            continue
        offers.append({'price': price, 'currency': currency or '\u901a\u8ca8\u672a\u8a18\u8f09', 'source': 'JSON-LD Offer', 'verification': '\u5143\u30da\u30fc\u30b8\u8981\u78ba\u8a8d'})
        if len(offers) >= 3:
            break
    return offers
