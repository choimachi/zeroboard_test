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
        'paywall_status': 'æªç¢ºèªï¼å¬éæå ±ããææã»ç¡æãå¤å®ãã¦ãã¾ããï¼',
        'description_source': 'HTML og:description/description' if desc else 'æªåå¾',
        'evidence_limits': 'å¬éæ¥ã®åè£ã¯è¨äºå´ã¡ã¿ãã¼ã¿ã®ç³åã§ããç¬ç«æ¤è¨¼ã§ã¯ããã¾ãããå¬éä¾¡æ ¼ã®åè£ã¯JSON-LD Offerã®ã¿ãè²©å£²ä»¶æ°ã»åçã»å®éè¦ã¯æªç¢ºèªã'
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
        offers.append({'price': price, 'currency': currency or 'éè²¨æªè¨è¼', 'source': 'JSON-LD Offer', 'verification': 'åãã¼ã¸è¦ç¢ºèª'})
        if len(offers) >= 3:
            break
    return offers
