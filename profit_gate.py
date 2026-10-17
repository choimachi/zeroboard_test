"""ZEROBOARD Ver.35: Conservative pre-production product evidence gate.

A public RSS headline does not establish purchase demand, note sales, or price.
This module NEVER calls an API and NEVER approves publication/payment.
"""
import re

UNKNOWN_MARKERS = ('未確認', '不明', '未検証', '根拠なし', '確認でき', '未取得', '検証が必要')

def _norm(value):
    return re.sub(r"\s+", " ", str(value or '')).strip()

def assess(record):
    info = (record or {}).get('evaluation') or {}
    problems = []
    strengths = []
    reader = _norm(record.get('candidate_reader'))
    pain = _norm(info.get('customer_pain'))
    demand = _norm(info.get('purchase_demand'))
    competitors = info.get('competitors') or []
    tasks = info.get('production_tasks') or []
    if not reader or reader in ('未確認', 'なし'):
        problems.append('購入者像が特定できていない')
    else:
        strengths.append('想定読者の記述あり（購買証拠ではない）')
    if not pain or pain in ('未確認', 'なし'):
        problems.append('読者の具体的な困りごとが不明')
    else:
        strengths.append('顧客課題の仮説あり')
    if not demand or any(k in demand for k in UNKNOWN_MARKERS):
        problems.append('購入意思・支払い実績を裏付ける独立証拠が未確認')
    else:
        problems.append('購入需要の説明は存在するが、RSS抜粋だけでは検証済みとみなせない')
    if not competitors:
        problems.append('競合商品を出典と結び付けて確認できていない')
    elif all(any(k in _norm(c.get('public_price')) for k in UNKNOWN_MARKERS) or not _norm(c.get('public_price')) for c in competitors):
        problems.append('競合の公開価格が確認できていない')
    else:
        strengths.append('競合価格の記載候補あり（原ページで確認が必要）')
    if not tasks:
        problems.append('有料部分に必要な制作作業が不明')
    else:
        strengths.append('制作タスクの仮説あり')
    # Conservative by design: no automatic paid draft approval on RSS metadata.
    return {'decision': '追加検証（制作保留）', 'problems': problems,
            'strengths': strengths, 'low_cost_tests': list(info.get('low_cost_validation') or [])[:3],
            'reason': '見出し・検索抜粋は市場の話題性を示すだけで、noteの販売実績や購買需要を証明しない。'}

def short_brief(record):
    info=record.get('evaluation') or {}
    verdict=assess(record)
    def clip(value, n=240): return _norm(value)[:n] or '未確認'
    return '\n'.join([
        '【制作前チェック／未承認の市場商品案】',
        '候補：'+clip(record.get('candidate_title')),
        '読者：'+clip(record.get('candidate_reader')),
        '困りごと（仮説）：'+clip(info.get('customer_pain')),
        '購入需要：'+clip(info.get('purchase_demand')),
        '未確認事項：'+'／'.join(clip(x,80) for x in (info.get('unknowns') or [])[:4]),
        '審査：'+verdict['decision'],
        '目的：購買根拠が弱ければ記事を量産せず低コストで検証する。',
        '禁止：未検証データを売上・レビュー・販売価格の実績として断言しない。',
        'CEOが承認しない限り外部公開・発注・支出を行わない。'
    ])
