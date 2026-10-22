"""Ver.44: zero-cost differentiation hypotheses from already fetched PUBLIC headlines/snippets.

No requests, no API, no unverified claims about paid text, sales or demand.
"""
import re

FEATURES = (
    ('checklist', ('チェックリスト', '確認表', 'チェック表')),
    ('template', ('テンプレート', 'テンプレ', 'ひな形', '雛形')),
    ('steps', ('手順', 'ステップ', 'ロードマップ', 'やり方')),
    ('example', ('実例', '実践例', 'サンプル', '作例', '事例')),
    ('worksheet', ('ワークシート', '記入', '書き込み', '記録シート')),
    ('feedback', ('添削', 'フィードバック', '個別相談', '相談会')),
)
SUGGESTIONS = (
    ('checklist', '購入後すぐ使える確認チェックリストを付ける'),
    ('template', 'そのまま記入できるテンプレートを付ける'),
    ('steps', '初日から実行できる小さな手順を明示する'),
    ('example', '再現可能な作例と失敗例を掲載する'),
    ('worksheet', '行動と結果を記録できるワークシートを付ける'),
    ('feedback', '質問受付などのサポートは運用可能な場合だけ検討する'),
)

def analyze(title, reader='', value='', articles=None):
    articles = (articles or [])[:3]
    title = str(title or '').strip()[:180]
    reader = str(reader or '').strip()[:140]
    value = str(value or '').strip()[:300]
    competitors = []
    public_features = set()
    for article in articles:
        headline = str(article.get('title') or article.get('headline_hint') or '')[:220]
        snippet = str(article.get('public_description_excerpt') or '')[:240]
        public = headline + ' ' + snippet
        mentions = [{'code': code, 'term': next(term for term in words if term in public)}
                    for code, words in FEATURES if any(term in public for term in words)]
        public_features.update(v['code'] for v in mentions)
        competitors.append({
            'title': headline,
            'url': str(article.get('url') or ''),
            'mentions': mentions,
            'public_description_available': bool(snippet),
            'price_status': article.get('price_status') or '未確認',
            'paywall_status': article.get('paywall_status') or '未確認',
            'inference': '見出し・公開説明に記載された語句のみ。本文の実提供物・有料範囲は未確認。',
        })
    # Avoid "competitors do not provide X"; silence of snippets is not absence.
    candidates = []
    for code, idea in SUGGESTIONS:
        candidates.append({
            'idea': idea,
            'signal': ('競合の見出し/公開説明に関連語あり（差別化済みかは不明）'
                       if code in public_features else
                       '取得した見出し/公開説明には関連語なし（競合に存在しないという意味ではない）'),
            'verification': '関連する競合の原ページを目視確認し、購入者に価値があるか小規模検証する',
        })
    audience_line = f'想定読者「{reader}」が' if reader else '想定読者が'
    return {
        'status': 'hypothesis_only',
        'product_title': title, 'intended_reader': reader or '未設定',
        'proposed_paid_value': value or '未設定',
        'competitor_public_mentions': competitors,
        'differentiation_options': candidates,
        'customer_outcome_hypothesis': audience_line + '読後に何を完成できるかを具体化する（未検証の提案）',
        'free_validation': [
            '競合の元記事を最大3件目視確認し、有料範囲・納品物・価格を記録する',
            '想定読者3〜5人に困りごとと既存の代替手段を聞く（購入意思と区別する）',
            '無料サンプル/目次を公開し、保存・質問・事前登録などの反応を記録する',
            '販売前に価格・権利・出典・提供可能な成果物をCEOが確認する',
        ],
        'limitations': '本文・有料部分・購入件数・売上・真の需要・競合に機能がないことは未確認。差別化案は仮説であり、販売承認ではありません。',
    }


def meeting_brief(result):
    lines = [
        '【Ver.44 公開情報を基にした差別化仮説：CEO判断待ち】',
        '商品候補：' + result.get('product_title', ''),
        '想定読者（仮説）：' + result.get('intended_reader', ''),
        '有料で届ける価値（企画・未検証）：' + result.get('proposed_paid_value', ''),
        '公開記事の見出し・説明から検出された要素：',
    ]
    for a in result.get('competitor_public_mentions', [])[:3]:
        lines += ['- ' + a.get('title', '') + ' | ' + a.get('url', ''),
                  '  公開文言で確認した要素：' + ('、'.join(x['term'] for x in a.get('mentions', [])) or '今回の辞書では検出なし')]
    lines.append('独自価値案（すべて仮説）：')
    lines.extend('- ' + x['idea'] for x in result.get('differentiation_options', [])[:4])
    lines.append('低コスト検証：')
    lines.extend('- ' + x for x in result.get('free_validation', [])[:3])
    lines.extend([
        '重要：未確認情報を事実とせず、競合記事が提供していないと断言しない。',
        'AI経営会議では公開・課金・外部支出を承認しない。CEO承認まで制作/販売は保留。',
    ])
    return '\n'.join(lines)[:6500]
