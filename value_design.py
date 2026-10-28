"""ZEROBOARD Ver.45: transparent, zero-API, editable product-outline hypotheses.

Does not fetch websites, estimate revenue, assert competition gaps, or publish.
"""
from datetime import datetime, timezone

FORMATS = {
    '実践ガイド＋ワークシート': '自分の条件に沿った実行計画と1つの試作品',
    'チェックリスト＋テンプレート': '判断に使えるチェック表と記入済みテンプレート',
    '入門教材＋演習': '基本を説明できる状態と完成した演習課題',
    'ケーススタディ＋検証表': '事例比較表と小さな検証計画',
}


def build(title, reader, goal, fmt, competitor_items=None):
    title = str(title or '').strip()[:160]
    reader = str(reader or '').strip()[:160]
    goal = str(goal or '').strip()[:240]
    if not title or not reader or not goal:
        raise ValueError('商品名・読者・購入後の完成物を入力してください。')
    if fmt not in FORMATS:
        raise ValueError('商品形式が不正です。')
    competitor_items = (competitor_items or [])[:3]
    sources = []
    for item in competitor_items:
        sources.append({'title': str(item.get('title') or item.get('headline_hint') or '')[:220],
                        'url': str(item.get('url') or ''),
                        'source_scope': '公開見出し・公開説明のみ。本文・有料範囲・売上は未確認'})
    return {
        'version': '45', 'status': 'DRAFT_NOT_APPROVED',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'product_title': title, 'reader_hypothesis': reader,
        'format': fmt, 'buyer_outcome_hypothesis': goal,
        'free_section': [
            {'heading': '読者の悩みと対象範囲', 'deliverable': f'「{reader}」に役立つ範囲と対象外を明示する'},
            {'heading': '最初に知るべき考え方', 'deliverable': '基礎知識・よくある失敗・判断の観点を説明する'},
            {'heading': '無料で試すミニ課題', 'deliverable': '短い課題と自己チェックで購入前に価値を試せるようにする'},
        ],
        'paid_section': [
            {'heading': '完成までの手順', 'deliverable': f'「{goal}」に向けた順番付きの手順（制作前の設計案）'},
            {'heading': '記入式の実践テンプレート', 'deliverable': '入力例・空欄版・使い方の注意をセットで用意する'},
            {'heading': '品質チェックと改善', 'deliverable': '完成基準・よくある失敗例・修正例をまとめる'},
            {'heading': '7日間の実行プラン', 'deliverable': '毎日の目標・作業・確認方法を提案する。成果を保証しない'},
        ],
        'attachments_hypothesis': [
            '記入できるワークシート（実ファイルは未制作）',
            '購入者用チェックリスト（実ファイルは未制作）',
            '作例と失敗例（再現テスト・権利確認が必要）',
        ],
        'acceptance_checks': [
            '読者が購入後に完成させるものを一文で説明できるか',
            '無料部分だけでも学べる内容があるか',
            '有料部分が無料部分の単なる言い換えになっていないか',
            'テンプレート・作例が実際に使えるか制作・動作確認したか',
            '出典・著作権・正確性・誇大表現を確認したか',
            '競合原ページを目視し、独自価値の主張が妥当か確認したか',
            '価格・公開・販売・支出についてCEOが明示的に承認したか',
        ],
        'validation': [
            '想定読者3〜5人に困りごとを聞き、回答を記録する（需要の証明ではない）',
            '無料ミニ課題を見せ、理解できたかと改善点を質問する',
            '目次と完成物の見本を見せ、必要性と代替手段を確かめる',
        ],
        'sources': sources,
        'limitations': '構成は制作前の仮説です。販売価格・需要・競合の有料本文・売上は未確認。記事本文・テンプレートの実物は制作されていません。',
    }


def meeting_brief(plan):
    lines = [
        '【Ver.45 VALUE DESIGN：制作前の商品設計案・CEO判断待ち】',
        '商品：' + plan['product_title'],
        '読者（仮説）：' + plan['reader_hypothesis'],
        '形式：' + plan['format'],
        '購入後の完成物（目標・未検証）：' + plan['buyer_outcome_hypothesis'],
        '無料部分：',
    ]
    lines.extend('- ' + x['heading'] + '：' + x['deliverable'] for x in plan['free_section'])
    lines.append('有料部分（制作案）：')
    lines.extend('- ' + x['heading'] + '：' + x['deliverable'] for x in plan['paid_section'])
    lines.append('検証が必要な点：')
    lines.extend('- ' + x for x in plan['validation'])
    lines.append('競合公開ページ（見出し・説明だけを参照）：')
    lines.extend('- ' + (x['title'] or '未確認') + ' | ' + x['url'] for x in plan['sources'])
    lines.append(plan['limitations'])
    lines.append('経営会議への議題セットは公開・制作・販売・支出の承認ではありません。')
    return '\n'.join(lines)[:6800]
