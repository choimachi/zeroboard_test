"""Ver.51 CEO APPROVAL DESK: review/decision records, no side effects.

All records are local to the Streamlit session until explicitly downloaded.
No database writes, network calls, posting, billing, or paid AI requests.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone

DECISIONS = {
    'approve': '出品準備へ進むことを承認（公開・販売は未承認）',
    'revise': '修正指示',
    'hold': '保留',
    'reject': '却下',
}


def _canonical(result: dict) -> dict:
    if not isinstance(result, dict) or result.get('version') != '50':
        raise ValueError('Ver.50の一括実行結果が必要です。')
    final = result.get('final_text')
    if not isinstance(final, dict) or not all(isinstance(final.get(k), str) for k in ('guide', 'prompt', 'example')):
        raise ValueError('確認する教材の本文・プロンプト・作例が揃っていません。')
    return {
        'title': result.get('title'), 'reader': result.get('reader'),
        'goal': result.get('goal'), 'created_at_utc': result.get('created_at_utc'),
        'final_text': final, 'summary': result.get('summary'),
        'second_review': result.get('second_review'),
    }


def fingerprint(result: dict) -> str:
    payload = json.dumps(_canonical(result), ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def create_record(result: dict, decision: str, reason: str,
                  acknowledged_risks: bool = False) -> dict:
    _canonical(result)
    if decision not in DECISIONS:
        raise ValueError('無効な判断です。')
    reason = str(reason or '').strip()
    if decision in ('revise', 'reject') and len(reason) < 5:
        raise ValueError('修正指示・却下には具体的な理由を5文字以上入力してください。')
    if decision == 'approve' and not acknowledged_risks:
        raise ValueError('未確認事項を確認し、出品準備への移行だけを承認してください。')
    if len(reason) > 2000:
        raise ValueError('理由は2000文字以内にしてください。')
    review = result.get('second_review') or {}
    findings = review.get('findings') or []
    return {
        'schema_version': 1,
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'draft_id_sha256': fingerprint(result),
        'draft_created_at_utc': result.get('created_at_utc'),
        'title': str(result.get('title') or ''),
        'decision': decision, 'decision_label': DECISIONS[decision],
        'reason': reason,
        'acknowledged_unverified_risks': bool(acknowledged_risks),
        'open_rule_check_findings': len(findings),
        'next_step': {
            'approve': '価格・著作権・事実・需要・実用性を人間が確認した後、別途出品準備を進める。公開・販売は未承認。',
            'revise': '理由に沿って編集し、新しいドラフトを生成して再検査・再審査する。',
            'hold': '未解決事項を保管して、別途確認する。',
            'reject': '当該ドラフトの商品化を見送る。',
        }[decision],
        'publication_approved': False,
        'sale_approved': False,
        'payment_approved': False,
        'api_spending_approved': False,
        'persistence': 'streamlit_session_and_optional_download_only',
    }


def export_json(records: list[dict]) -> bytes:
    if not isinstance(records, list):
        raise TypeError('記録が不正です。')
    return (json.dumps({'schema_version': 1, 'records': records}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
