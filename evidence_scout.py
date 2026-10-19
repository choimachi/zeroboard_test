"""Ver.37: conservative evidence audit of public RSS/search metadata.

This module makes zero API calls, does not fetch URLs, and never treats snippets,
listed prices, likes, or views as confirmed purchases or seller revenues.
"""
import re
from urllib.parse import urlparse

PRICE = re.compile(r'(?<!\d)(?:¥|￥)\s?\d{1,3}(?:,\d{3})*(?!\d)|(?<!\d)\d{2,6}\s?円')
REAL_PURCHASE_WORDS = ('購入者レビュー','購入済み','認証済み購入','verified purchase','購入件数')
REVIEW_WORDS = ('レビュー','口コミ','評判','感想','review')
SALES_WORDS = ('売上','販売数','購入数','販売実績','売れた')
PRODUCT_WORDS = ('有料','販売','商品','教材','講座','ワークショップ','テンプレート','価格','note')
STOPWORDS = {'について','ための','できる','する','これ','入門','副業','向け','無料','有料','簡易','使える','支援','情報','実際','記事','価格','こと','もの','商品','費用','方法'}


def _tokens(text):
    text = str(text or '').lower()
    chunks = re.findall(r'[一-龯ぁ-んァ-ンー]{3,}|[a-z][a-z0-9+.#-]{2,}', text)
    tokens=[]
    for chunk in chunks:
        if re.fullmatch(r'[a-z0-9+.#-]+',chunk):
            tokens.append(chunk)
        else:
            # Japanese titles often have no spaces; retrieve a few distinctive
            # contiguous strings as *candidate relevance leads*, not evidence.
            for size in (6,5):
                tokens.extend(chunk[i:i+size] for i in range(max(0,len(chunk)-size+1)))
    return [t for t in dict.fromkeys(tokens) if t not in STOPWORDS][:100]


def source_review(source, title, reader=''):
    """List metadata leads requiring CEO's manual verification, not proof."""
    head = str(source.get('title') or '')
    excerpt = str(source.get('excerpt') or '')
    url = str(source.get('url') or '')
    host = urlparse(url).netloc.lower()
    combined = (head+' '+excerpt).lower()
    topic = _tokens(title)
    # Strict exact overlaps; never boost on generic adjacent news.
    matches = [word for word in set(topic) if word in combined and len(word)>=3]
    # String containment can over-match on longer Japanese phrases: mark as a clue only.
    on_topic = bool(matches)
    is_note = host == 'note.com' or host.endswith('.note.com')
    is_catalog = any(tag in host for tag in ('stores.jp','booth.pm','udemy.com','base.shop','gumroad.com','note.com'))
    has_product_language = any(word in combined for word in PRODUCT_WORDS)
    price_mention = PRICE.findall(head+' '+excerpt)
    review_mention = any(word in combined for word in REVIEW_WORDS)
    actual_purchase_mention = any(word in combined for word in REAL_PURCHASE_WORDS)
    sales_mention = any(word in combined for word in SALES_WORDS)
    if not on_topic:
        relevance = '関連未確認'
    elif is_catalog and has_product_language:
        relevance = '競合商品候補（原ページ未確認）'
    elif has_product_language:
        relevance = '商品関連の言及（原ページ未確認）'
    else:
        relevance = '話題の関連情報（購入根拠ではない）'
    return {
        'id': str(source.get('id') or ''), 'title':head, 'url':url,
        'published_date':source.get('published_date') or '不明',
        'retrieved_at':source.get('retrieved_at') or '不明',
        'relevance':relevance, 'matching_terms':sorted(matches),
        'price_mention':price_mention[:3],
        'price_status':'検索抜粋上の表記のみ。商品ページの販売価格は未確認' if price_mention else '未確認',
        'review_status':'レビューに関する記述あり。本文・実在・件数未確認' if review_mention else '未確認',
        'purchase_status':'購入に関する記述あり。証拠・件数未確認' if (actual_purchase_mention or sales_mention) else '未確認',
        'evidence_class': '購入・販売を裏付ける証拠ではない（検索見出し・抜粋）'
    }


def audit_idea(idea):
    reviews=[source_review(src,idea.get('title'),idea.get('reader')) for src in (idea.get('linked_sources') or [])]
    promising=[r for r in reviews if r['relevance']=='競合商品候補（原ページ未確認）']
    relevant=[r for r in reviews if r['relevance']!='関連未確認']
    return {
        'source_reviews':reviews,
        'competitor_leads':promising,
        'related_sources':len(relevant),
        'total_sources':len(reviews),
        'confirmed_competitor_prices':0,
        'confirmed_sales_or_purchases':0,
        'verified_demand':False,
        'next_action':('候補の商品ページをCEOが開き、販売形態・価格・レビューを確認する'
                       if promising else '類似する有料商品の原ページを探し、価格と対象読者を確認する'),
        'caveat':'RSSの見出し・抜粋だけでは、競合の現行価格・購入実績・レビューの真正性は確認できません。'
    }


def brief(idea, audit):
    """Business-meeting memo without invented sales evidence."""
    lines = [
        '【Ver.37 EVIDENCE SCOUT／商品需要・競合の追加検証依頼】',
        '商品候補：'+str(idea.get('title') or ''),
        '想定読者（仮説）：'+str(idea.get('reader') or ''),
        '届ける価値（仮説）：'+str(idea.get('paid_value') or ''),
        '購入実績：未確認／価格：原ページ未確認／レビュー：原ページ未確認',
        '収集ソースの分類：'+str(audit['related_sources'])+'/'+str(audit['total_sources'])+' 件が商品テーマに関連する可能性',
        '次に行う検証：'+audit['next_action'],
        'AI役員への依頼：関連ニュースと支払意思の証拠を混同せず、別の商品候補とも比較する。',
        '制作・公開・支出をせず、CEOに追加調査案だけ提出する。',
    ]
    for r in audit['source_reviews'][:4]:
        lines.append(f"- {r['relevance']} | {r['title'][:110]} | 公開:{r['published_date']} | 取得:{r['retrieved_at']} | {r['url'][:350]}")
    return '\n'.join(lines)[:4500]
