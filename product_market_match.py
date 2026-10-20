# -*- coding: utf-8 -*-
"""Ver.41: Evidence-aware candidate-to-note matching. No OpenAI requests."""
import json
import re

# These are topical tags (not a synonym for a product and not proof of a competitor).
RULES = [
    (('AI副業', 'AI活用', 'chatgpt', 'ワークショップ', '副業', 'デジタル商品'), 'AI副業'),
    (('ローン', '住宅', '金利', '利上げ', '家計'), '住宅ローン'),
    (('投資', '株式', 'NISA', 'インデックス'), '投資初心者'),
    (('クラウド', 'GPU', 'インフラ', 'サーバ', 'SRE'), 'クラウド'),
]


def suggest_tag(title, reader='', paid_value=''):
    combined = ' '.join(map(str, (title or '', reader or '', paid_value or ''))).lower()
    for words, tag in RULES:
        if any(word.lower() in combined for word in words):
            return tag
    return '副業'  # generic fallback, manually editable in UI


def get_candidate_label(row):
    return f"#{row.get('id', '?')}｜{row.get('candidate_title') or '題名未登録'}"[:150]


def get_paid_value(row):
    ev = row.get('evaluation') or {}
    if not isinstance(ev, dict):
        return ''
    return str(ev.get('paid_value') or ev.get('customer_pain') or '')[:700]


def compare(candidate_title, candidate_reader, result):
    """Title-only topical matching. Never claim sales or exact competition."""
    tokens = [w.lower() for w in re.findall(r'[A-Za-z]{3,}|[ァ-ヶー]{3,}|[一-龥]{2,}|[ぁ-ん]{3,}',
                                                    str(candidate_title or '')+' '+str(candidate_reader or ''))]
    excluded = {'ため', '方法', '記事', '初心者', '向け', 'について', 'できる', 'する', 'レポート', 'ミニ', 'とは', '相談'}
    tokens = list(dict.fromkeys(t for t in tokens if t not in excluded))[:24]
    rows=[]
    for raw in (result.get('articles') or [])[:3]:
        title=str(raw.get('title') or '')
        matches=[t for t in tokens if t in title.lower()]
        rows.append({
            'title':title or 'タイトル未確認', 'url':raw.get('url') or '',
            'headline_overlap':matches[:6],
            'relevance':'見出しに共通語あり（競合性未確認）' if matches else '見出し一致なし（関連性未確認）',
            'published_date':raw.get('published_date_claim') or '未確認',
            'retrieved_at':raw.get('retrieved_at_utc') or '未確認',
            'price':raw.get('structured_prices') or [],
            'price_status':raw.get('price_status') or '未確認',
            'purchase': '未確認', 'reviews':'未確認',
        })
    return rows


def meeting_brief(candidate_title, candidate_reader, tag, result, matched):
    data = {'candidate':candidate_title, 'target_reader_hypothesis':candidate_reader,
            'searched_tag':tag, 'tag_url':result.get('tag_url'),
            'research_timestamp':result.get('checked_at_utc'), 'examples':matched,
            'uncertainties': ['記事タイトルだけでは同一商品や直接競合と判断できない',
                              '購入数・販売数・売上・需要は未確認',
                              '公開価格や公開日は見つからなければ未確認',
                              '原ページで内容と価格を確認し、購入者の悩みを追加調査する必要あり'],
            'recommendation':'制作承認ではなく、原ページ確認と差別化仮説の審議を依頼'}
    return ('【ZEROBOARD Ver.41 PRODUCT MARKET MATCH｜根拠付き市場仮説】\n'
            '4役員は参考記事と市場需要を混同せず、競合性・差別化・価格・実証方法を検討。\n'
            '実際の売上・購入実績を推測で断定せず、CEO承認まで制作・公開・支出は禁止。\n'
            + json.dumps(data, ensure_ascii=False, default=str)[:12000])
