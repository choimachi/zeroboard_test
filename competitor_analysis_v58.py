"""Ver.58: offline inventory and honest competitor comparison scaffolding.

Inputs are previously saved, unverified Ver.57 research records. This module never
fetches URLs, infers prices/features, declares a product verified, or runs an API.
"""
from __future__ import annotations
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING = {'fbclid','gclid','gbraid','wbraid','mc_cid','mc_eid','ref','source'}

def canonical_url(raw):
    if not isinstance(raw,str) or len(raw)>2000: return ''
    try:
        p=urlsplit(raw.strip())
        if p.scheme!='https' or not p.hostname or p.username or p.password: return ''
        if p.hostname in ('localhost',) or p.hostname.endswith('.local'): return ''
        host=p.hostname.lower().removeprefix('www.')
        query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
                      if not k.lower().startswith('utm_') and k.lower() not in TRACKING))
        path=p.path.rstrip('/') or '/'
        return urlunsplit(('https',host,path,query,''))
    except (ValueError,TypeError):return ''

def _short(text, n=180):
    return re.sub(r'\s+',' ',str(text or '')).strip()[:n]

def build(report_rows, title, draft_id):
    """Returns distinct URL leads and an honest incomplete comparison. No verification."""
    if not re.fullmatch(r'[0-9a-f]{64}',str(draft_id)):
        raise ValueError('草稿IDが不正です。')
    seen={}
    dated=[]
    for rr in report_rows or []:
        if rr.get('draft_id')!=draft_id: continue
        rid=str(rr.get('report_id') or '')
        date=str(rr.get('researched_at_utc') or '')[:19]
        dated.append(date)
        for s in rr.get('sources') or []:
            if not isinstance(s,dict):continue
            url=canonical_url(s.get('url'))
            if not url:continue
            if url not in seen:
                seen[url]={'url':url,'title':_short(s.get('title') or url,180),
                           'host':urlsplit(url).hostname,'report_ids':[rid],
                           'first_seen_utc':date,
                           'evidence_status':'原文未確認',
                           'competitor_name':'要確認','price':'要確認',
                           'scope':'要確認','differentiation':'根拠未確認'}
            elif rid not in seen[url]['report_ids']:
                seen[url]['report_ids'].append(rid)
    leads=sorted(seen.values(),key=lambda v:(v['host'],v['url']))
    return {'draft_id':draft_id,'title':_short(title,200),
            'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'saved_report_count':len(dated),'raw_source_count':sum(len(r.get('sources') or []) for r in (report_rows or []) if r.get('draft_id')==draft_id),
            'distinct_url_count':len(leads),'leads':leads,
            'note':'出典URLの候補一覧です。競合・商品の実在性、価格、比較内容、URLの到達可否・権利は未検証。'}

def csv_bytes(result):
    f=io.StringIO(newline='')
    w=csv.writer(f)
    w.writerow(['資料タイトル(未確認)','参照ドメイン','参照URL','競合の商品名','対象読者','価格','内容・機能','差別化の根拠','検証状況'])
    for lead in result['leads']:
        w.writerow([lead['title'],lead['host'],lead['url'],lead['competitor_name'],
                    '要確認',lead['price'],lead['scope'],lead['differentiation'],lead['evidence_status']])
    return ('\ufeff'+f.getvalue()).encode('utf-8')

def json_bytes(result):
    return json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')
