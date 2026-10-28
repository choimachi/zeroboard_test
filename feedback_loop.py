"""Ver.52: narrow rule-based CEO feedback loop. No network / AI / publishing.

Supported specifically: adding three fictional SNS examples with input, sample output,
manual correction. Other CEO instructions are NOT automatically treated as fulfilled.
"""
from __future__ import annotations
import copy
import difflib
from datetime import datetime, timezone
import ceo_approval
import quality_control

_EXAMPLES = [
    ('架空の雑貨店', '新入荷の文房具を知らせる', '近隣の文房具好き',
     '新入荷の文房具、気になる方はぜひ店頭へ！',
     '架空の雑貨店から新入荷の文房具をご紹介。写真・在庫・価格を店舗側で確認してから掲載します。気になる商品はお問い合わせください。'),
    ('架空の清掃サービス', 'サービス内容を分かりやすく紹介する', '掃除の相談先を探している人',
     'ピカピカにします！今すぐご予約を！',
     '架空の清掃サービスでは、対応可能な作業内容を分かりやすくご案内します。対応地域・料金・予約方法は運営者が確認の上で記載してください。'),
    ('架空のカフェ', '季節のメニューの紹介文を考える', '近隣のカフェ利用者',
     '大人気の新メニューが登場！',
     '架空のカフェの季節メニューを紹介する投稿案です。商品名・提供期間・価格は事実確認後に追記します。詳細は店頭でご確認ください。'),
]


def _three_examples() -> str:
    parts = ['\n\n## CEO修正指示に基づくSNS投稿の追加作例（すべて架空／要編集）',
             'これはルールで用意した練習用の草稿です。AIへの実通信・実測の結果ではありません。']
    for i, (business, topic, reader, draft, corrected) in enumerate(_EXAMPLES, 1):
        parts.extend([
            f'### 作例{i}：{business}',
            f'**AIへの入力例**：{business}のSNS投稿案を作ってください。想定読者は{reader}。目的は「{topic}」。見出し・本文・次の行動を含めて、未確認の価格・在庫・実績を創作しないでください。',
            f'**生成結果の例（実行ログではない）**：{draft}',
            f'**人間による修正例**：{corrected}',
            '**確認事項**：実在の内容と誤認させない。写真の権利、実在するサービス内容、価格、掲載可否を公開前に人間が確認する。'
        ])
    return '\n\n'.join(parts) + '\n'


def preview_revision(result: dict, decision: dict) -> dict:
    """Prepare a NEW, unapproved draft only when a supported feedback pattern matches."""
    if not isinstance(result, dict) or result.get('version') != '50':
        raise ValueError('Ver.50の草稿が必要です。')
    if not isinstance(decision, dict) or decision.get('decision') != 'revise':
        raise ValueError('CEOの修正指示記録が必要です。')
    parent_id = ceo_approval.fingerprint(result)
    if decision.get('draft_id_sha256') != parent_id:
        raise ValueError('この修正指示は現在の草稿のものではありません。')
    instruction = str(decision.get('reason') or '').strip()
    if not instruction:
        raise ValueError('修正指示がありません。')
    project = str(result.get('blueprint', {}).get('project') or result.get('assets', {}).get('project') or '')
    is_sns = project == 'AIでSNS投稿案を作る'
    asks_examples = ('SNS' in instruction or '投稿' in instruction) and ('完成例' in instruction or '作例' in instruction)
    asks_three = ('3つ' in instruction or '３つ' in instruction or '3本' in instruction or '３本' in instruction or '3件' in instruction)
    asks_input_draft_fix = ('入力' in instruction and ('生成結果' in instruction or '下書き' in instruction) and ('修正' in instruction))
    supported = is_sns and asks_examples and asks_three and asks_input_draft_fix
    if not supported:
        return {'status': 'NEEDS_MANUAL_OR_AI_EDIT', 'instruction': instruction,
                'parent_draft_id': parent_id,
                'message': 'この自由文指示に対応した自動修正ルールは未実装です。修正済みとは扱いません。',
                'proposed_draft': None, 'changes': [], 'before_findings': len(result.get('second_review', {}).get('findings') or [])}
    proposed = copy.deepcopy(result)
    before = result['final_text']['example']
    block = _three_examples()
    marker = '## CEO修正指示に基づくSNS投稿の追加作例'
    if marker in before:
        # Avoid adding duplicates; refuse to present a no-op as a fresh revision.
        return {'status': 'ALREADY_PRESENT', 'instruction': instruction, 'parent_draft_id': parent_id,
                'message': 'この作例はすでに草稿に含まれます。重複追加はしません。',
                'proposed_draft': None, 'changes': [], 'before_findings': len(result.get('second_review', {}).get('findings') or [])}
    proposed['final_text']['example'] = before.rstrip() + '\n' + block
    review = quality_control.review(proposed['assets'], **proposed['final_text'])
    proposed['second_review'] = review
    proposed['summary']['final_findings'] = len(review['findings'])
    proposed['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    proposed['status'] = 'DRAFT_CEO_REVIEW_REQUIRED'
    proposed['feedback_loop'] = {
        'version': '52', 'parent_draft_id_sha256': parent_id,
        'source_decision_recorded_at_utc': decision.get('recorded_at_utc'),
        'source_instruction': instruction,
        'applied_rule': 'three_fictional_sns_examples_v1',
        'verification': 'RULE_BASED_CONTENT_ONLY_NOT_HUMAN_TESTED',
        'publication_approved': False, 'sale_approved': False,
    }
    diff = '\n'.join(difflib.unified_diff(before.splitlines(), proposed['final_text']['example'].splitlines(),
                                           fromfile='修正前の作例', tofile='修正後の作例', lineterm=''))
    return {'status': 'PROPOSAL_READY_UNAPPROVED', 'instruction': instruction,
            'parent_draft_id': parent_id, 'proposed_draft': proposed,
            'changes': ['3つの架空のSNS投稿例に入力例・下書き例・人間の修正例を追加'],
            'diff': diff, 'before_findings': len(result.get('second_review', {}).get('findings') or []),
            'after_findings': len(review['findings']),
            'message': '修正版の草稿を作成しました。ルールベースの参考例で、CEO再承認・事実確認が必要です。'}
