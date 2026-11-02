"""Ver.57: one CEO-authorized, web-grounded research request per button click.

Never marks an issue verified and never publishes; human must inspect sources.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
import uuid

MODEL = 'gpt-5-mini'
MAX_OUTPUT_TOKENS = 2000


def _safe_url(value):
    if not isinstance(value, str) or len(value)>1800: return None
    p=urlparse(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password: return None
    if p.hostname in ('localhost',) or p.hostname.endswith('.local'): return None
    return value


def _get(obj, field, default=None):
    return obj.get(field, default) if isinstance(obj, dict) else getattr(obj, field, default)


def research(client, item, title):
    """Exactly one Responses API create request. Web search *tool* may make >1 billable searches."""
    if not item or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('issue_id', ''))):
        raise ValueError('調査対象の指摘IDが不正です。')
    prompt = ('あなたはZEROBOARDの調査担当です。公開ウェブ情報を検索し、品質指摘の検証材料を日本語でまとめてください。'
              'URLを捏造せず、情報の公開日と検索実行日を区別してください。一次資料を優先し、'
              '競合の非公開売上・レビュー件数・利用許諾・著作権の適法性を推測で断言しないでください。'
              '資料の証拠能力の限界、確認できていない点、CEOが自分で確かめる手順を明記。'
              '引用元は本文内にも示してください。最大700字程度。'
              '\n商品名：'+str(title)[:150]+'\n品質指摘：'+str(item['issue'])[:500]+
              '\n推奨対応：'+str(item.get('suggested_action') or '')[:500])
    response = client.responses.create(
        model=MODEL,
        tools=[{'type':'web_search'}], tool_choice='required',
        include=['web_search_call.action.sources'],
        max_output_tokens=MAX_OUTPUT_TOKENS, input=prompt,
    )
    calls=[x for x in (_get(response,'output') or []) if _get(x,'type')=='web_search_call']
    text=str(_get(response,'output_text') or '').strip()
    if not calls or not text:
        raise ValueError('Web検索の実行または調査本文を確認できませんでした。保存しません。')
    collected=[]
    for call in calls:
        action=_get(call,'action')
        for s in (_get(action,'sources') or []):
            url=_safe_url(_get(s,'url'))
            if url: collected.append({'url':url,'title':str(_get(s,'title') or url)[:250]})
    for output_item in (_get(response,'output') or []):
        for content in (_get(output_item,'content') or []):
            for a in (_get(content,'annotations') or []):
                if _get(a,'type')=='url_citation':
                    url=_safe_url(_get(a,'url'))
                    if url: collected.append({'url':url,'title':str(_get(a,'title') or url)[:250]})
    seen=set(); sources=[]
    for s in collected:
        if s['url'] not in seen:
            sources.append(s);seen.add(s['url'])
    if not sources:
        raise ValueError('Web検索したものの出典URLを取得できませんでした。レポートは未採用です。')
    u=_get(response,'usage')
    return {'report_id':str(uuid.uuid4()),'draft_id':str(item['draft_id']),
            'issue_id':str(item['issue_id']), 'issue':str(item['issue']),
            'report_text':text[:12000], 'sources':sources[:20],
            'researched_at_utc':datetime.now(timezone.utc).isoformat(),
            'model':MODEL, 'web_search_calls':len(calls),
            'input_tokens':_get(u,'input_tokens'), 'output_tokens':_get(u,'output_tokens'),
            'review_status':'unverified_ceo_review',
            'note':'検索結果の要約です。リンク先の内容・権利・販売需要を自動で実証したものではありません。'}


def save(db, report):
    if report.get('review_status')!='unverified_ceo_review':
        raise ValueError('CEO確認待ちのレポートのみ保存可能です。')
    row={k:report[k] for k in ('report_id','draft_id','issue_id','issue','report_text',
         'sources','researched_at_utc','model','web_search_calls','review_status')}
    db.table('company_research_reports').insert(row).execute()
    return row['report_id']


def list_reports(db, draft_id):
    if not re.fullmatch(r'[0-9a-f]{64}',str(draft_id)):raise ValueError('草稿IDが不正です。')
    return (db.table('company_research_reports').select('*')
            .eq('draft_id', draft_id).order('researched_at_utc',desc=True).limit(40).execute().data or [])
