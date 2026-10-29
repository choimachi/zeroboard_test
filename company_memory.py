"""Ver.53 COMPANY MEMORY — protected persistence of draft snapshots and CEO decisions.

Only call with a server-side service-role Supabase client AFTER CEO authentication.
Never expose these objects or API credentials to unauthenticated visitors.
No OpenAI, note publishing, payments, automatic approval, or background execution.
"""
from __future__ import annotations
import json
import ceo_approval

MAX_DRAFT_BYTES = 1_500_000


def _json_ready(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def save_draft(db, draft: dict) -> str:
    draft_id = ceo_approval.fingerprint(draft)
    payload = _json_ready(draft)
    size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    if size > MAX_DRAFT_BYTES:
        raise ValueError('草稿が保存上限（約1.5MB）を超えています。')
    parent_id = ((draft.get('ai_revision') or {}).get('parent_draft_id_sha256')
                 or (draft.get('feedback_loop') or {}).get('parent_draft_id_sha256') or None)
    if parent_id == draft_id:
        raise ValueError('草稿IDと親IDが一致しています。')
    row = {'draft_id': draft_id, 'title': str(draft.get('title') or '')[:240],
           'parent_draft_id': parent_id, 'snapshot': payload}
    # Immutable history: insert only if absent. Do not modify previously saved drafts.
    found = db.table('company_drafts').select('draft_id').eq('draft_id', draft_id).limit(1).execute().data or []
    if not found:
        try:
            db.table('company_drafts').insert(row).execute()
        except Exception:
            # Another session may have inserted same hash concurrently; verify before surfacing error.
            found = db.table('company_drafts').select('draft_id').eq('draft_id', draft_id).limit(1).execute().data or []
            if not found:
                raise
    return draft_id


def save_decision(db, draft: dict, record: dict) -> None:
    draft_id = ceo_approval.fingerprint(draft)
    if record.get('draft_id_sha256') != draft_id:
        raise ValueError('CEO判断と草稿IDが一致しません。')
    if record.get('decision') not in ceo_approval.DECISIONS:
        raise ValueError('不正な判断種別です。')
    save_draft(db, draft)
    db.table('company_decisions').insert({
        'draft_id': draft_id,
        'decision': record['decision'],
        'record': _json_ready(record)
    }).execute()


def list_drafts(db, limit=50):
    return (db.table('company_drafts')
            .select('draft_id,title,parent_draft_id,saved_at')
            .order('saved_at', desc=True).limit(min(max(limit, 1), 100))
            .execute().data or [])


def load_draft(db, draft_id: str) -> dict:
    rows = (db.table('company_drafts').select('draft_id,snapshot')
            .eq('draft_id', draft_id).limit(1).execute().data or [])
    if not rows:
        raise ValueError('該当する草稿が見つかりません。')
    data = rows[0]['snapshot']
    if not isinstance(data, dict) or ceo_approval.fingerprint(data) != draft_id:
        raise ValueError('保存された草稿に整合性エラーがあります。')
    return data


def load_decisions(db, draft_id: str):
    rows = (db.table('company_decisions').select('record')
            .eq('draft_id', draft_id).order('recorded_at', desc=False)
            .limit(100).execute().data or [])
    return [r['record'] for r in rows if isinstance(r.get('record'), dict)]
