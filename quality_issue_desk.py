"""Ver.56 QUALITY ISSUE DESK: manual, evidence-labelled issue tracking.

Only invoke DB methods with CEO-authenticated service-role client. No AI calls,
external web access, publication, purchasing, or automated verification.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
import ceo_approval
import quality_improvement

STATES = {
    'open': '未対応',
    'investigating': '調査中',
    'ceo_review': 'CEO確認待ち',
    'verified': 'CEOが根拠を確認（自己申告）',
    'not_applicable': '対象外（理由記録済み）',
}
HUMAN_CATEGORIES = {'differentiation', 'accuracy'}


def _id(draft_id, finding):
    # The same issue category/text within the same immutable draft has same ID.
    raw = json.dumps([draft_id, finding['category'], finding['issue']], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def inventory(draft):
    draft_id = ceo_approval.fingerprint(draft)
    plan = quality_improvement.triage(draft)
    human_issues = {(x['category'], x['issue']) for x in plan['human']}
    items = []
    for finding in plan['review']['findings']:
        kind = ('human_evidence' if (finding['category'], finding['issue']) in human_issues
                or finding['category'] in HUMAN_CATEGORIES else 'editorial')
        items.append({
            'issue_id': _id(draft_id, finding), 'draft_id': draft_id,
            'category': finding['category'], 'issue': finding['issue'],
            'level': finding['level'], 'evidence': finding.get('evidence', ''),
            'suggested_action': finding.get('action', ''), 'kind': kind,
        })
    return items


def evidence_hint(item):
    if item['category'] == 'differentiation':
        return '競合の公開ページURL、比較日、比較できた範囲を記録。未公開部分は未確認。'
    if item['category'] == 'accuracy':
        return '権利者・原資料・確認日・実際に再現した手順と結果を記録。'
    return '修正箇所と検証手順、確認した結果を記録。'


def record_for(item, status, note, checked=False):
    if status not in STATES: raise ValueError('状態の指定が不正です。')
    note = str(note or '').strip()
    if len(note) > 2000: raise ValueError('確認メモは2000文字以内にしてください。')
    if status in ('verified', 'not_applicable'):
        if len(note) < 20: raise ValueError('根拠確認済み・対象外には、確認内容や理由を20文字以上記録してください。')
        if not checked: raise ValueError('CEOが内容を確認したチェックが必要です。')
    return {'issue_id':item['issue_id'], 'draft_id':item['draft_id'],
            'category':item['category'], 'issue':item['issue'],
            'kind':item['kind'], 'status':status, 'note':note,
            'confirmed_by_ceo':bool(checked) if status in ('verified','not_applicable') else False,
            'recorded_at_utc':datetime.now(timezone.utc).isoformat()}


def list_records(db, draft_id):
    if not re.fullmatch(r'[0-9a-f]{64}', str(draft_id)): raise ValueError('草稿IDが不正です。')
    return db.table('company_quality_issues').select('*').eq('draft_id', draft_id).limit(100).execute().data or []


def save_record(db, item, status, note, checked=False):
    record = record_for(item, status, note, checked)
    # Restrict update to the status/memo for a given issue. Database row is CEO-authenticated only.
    row = {'issue_id':record['issue_id'], 'draft_id':record['draft_id'],
           'category':record['category'], 'issue':record['issue'],
           'kind':record['kind'], 'status':record['status'], 'note':record['note'],
           'confirmed_by_ceo':record['confirmed_by_ceo'], 'updated_at':record['recorded_at_utc']}
    db.table('company_quality_issues').upsert(row, on_conflict='issue_id').execute()
    return record
