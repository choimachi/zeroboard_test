# -*- coding: utf-8 -*-
"""Ver.42: rank publicly listed note links before fetching up to three pages.
No AI/API calls, no sales-demand estimates, no external JS/browser automation.
"""
import html
import re
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote
from urllib.error import HTTPError, URLError

import note_direct_scout as note

# Explicitly disclosed related-word groups: heuristic topical evidence, not verified competitors.
TOPIC_GROUPS = (
    ('副業', 'AI副業', '副収入', '収益化', '稼ぐ', '稼ぎ方'),
    ('AI', '生成AI', 'ChatGPT', 'チャットGPT', '人工知能'),
    ('初心者', '入門', 'はじめ方', '始め方', '初めて', '基礎'),
    ('教材', 'ガイド', '手順', 'ロードマップ', 'ハンドブック', '講座'),
    ('住宅ローン', 'ローン', '返済', '金利', '利上げ'),
    ('投資', '新NISA', '株式', '資産運用', '積立'),
    ('クラウド', 'GPU', 'AIインフラ', 'SRE', 'サーバー'),
    ('商品', 'デジタル商品', 'テンプレート', '販売', 'BOOTH'),
    ('相談', '個別相談', 'ワークショップ', 'コンサル', '面談'),
)
STOP_WORDS = {'について', 'ため', '方法', '記事', '向け', 'できる', 'する', 'ミニ', 'とは', '解説', '完全', '最新', '実践', '使った'}


def _terms(s):
    s = str(s or '').lower()
    # Partially segment Japanese title without extra dependencies.
    parts = re.findall(r'[a-z][a-z0-9+]{1,}|[ァ-ヶー]{2,}|[一-龥]{2,}|[ぁ-ん]{3,}', s)
    return list(dict.fromkeys(t for t in parts if t not in STOP_WORDS))[:35]


def _contains(text, word):
    return word.lower() in text.lower()


def rank(title, reader, value, article_title):
    target = ' '.join(map(str, (title or '', reader or '', value or ''))).lower()
    subject = str(article_title or '').lower()
    groups = []
    for group in TOPIC_GROUPS:
        if any(_contains(target, word) for word in group) and any(_contains(subject, word) for word in group):
            groups.append(group[0])
    exact = [t for t in _terms(title) if len(t) >= 3 and t in subject]
    # Evidence limited to listing headline and keyword heuristics.
    points = 3 * len(groups) + 2 * len(exact)
    return points, groups[:6], exact[:6]


class TagArticleLinks(HTMLParser):
    """Collect direct note article anchors and visible anchor text, even nested tags."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._url = None
        self._text = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if self._url:
            self._depth += 1
        if tag == 'a':
            d = dict(attrs)
            url = note.article_url(d.get('href') or '')
            if self._url:
                return
            if url:
                self._url = url
                self._text = [d.get('aria-label', ''), d.get('title', '')]
                self._depth = 1

    def handle_data(self, data):
        if self._url and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag):
        if self._url:
            self._depth -= 1
            if self._depth <= 0:
                self.anchors.append({'url': self._url, 'headline_hint': ' '.join(self._text).strip()[:240]})
                self._url = None
                self._text = []
                self._depth = 0


def scout(tag, title, reader='', value='', max_articles=3):
    """One public tag-page request + <=3 public article requests."""
    tag = str(tag or '').strip()[:40]
    if not tag or any(ch in tag for ch in ('/', '?', '#', '&', '\n', '\r')):
        raise ValueError('タグには短いキーワードを指定してください。')
    max_articles = max(1, min(3, int(max_articles)))
    url = 'https://note.com/hashtag/' + quote(tag)
    result = {'status': 'pending', 'tag': tag, 'tag_url': url, 'candidate': title,
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'requests_attempted': 1, 'articles': [],
              'limitations': '見出しの関連度は仮説です。競合性・需要・購入数・売上・価格は確定していません。'}
    try:
        response = note.request(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        result.update(status='tag_fetch_failed', error_type=type(exc).__name__)
        return result
    result['tag_http_status'] = response.get('http_status')
    if response.get('http_status') != 200 or 'html' not in response.get('content_type','').lower():
        result['status'] = 'tag_page_unavailable'
        return result
    parser = TagArticleLinks()
    parser.feed(response.get('html') or '')
    hints = {}
    for entry in parser.anchors:
        if entry['url'] not in hints or len(entry['headline_hint']) > len(hints[entry['url']]):
            hints[entry['url']] = entry['headline_hint']
    # If note uses anchors with no visible text, still list them, explicitly mark weak evidence.
    # Preserve first-seen order to make zero-score tie breaking deterministic.
    ranked = []
    for i, (link, hint) in enumerate(hints.items()):
        points, groups, exact = rank(title, reader, value, hint)
        ranked.append({'url':link,'headline_hint':hint or 'タグ掲載リンク（見出し取得不可）',
                       'rank_score':points, 'matched_topics':groups, 'exact_terms':exact,
                       'original_order':i})
    ranked.sort(key=lambda x: (-x['rank_score'], x['original_order']))
    selected = ranked[:max_articles]
    result['tag_article_links_found'] = len(hints)
    result['tag_links_scored_positive'] = sum(x['rank_score'] > 0 for x in ranked)
    result['selection_method'] = 'タグページのリンク見出しから関連語を照合。点数同率は掲載順。需要・販売実績のスコアではない。'
    result['ranked_preview'] = ranked[:10]
    for item in selected:
        time.sleep(0.7)
        out = dict(item)
        out.update({'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                    'published_date_claim':None, 'structured_prices':[],
                    'price_status':'未確認', 'purchase_status':'未確認', 'review_status':'未確認'})
        result['requests_attempted'] += 1
        try:
            page = note.request(item['url'])
            out['http_status'] = page.get('http_status')
            if (page.get('http_status') == 200 and 'html' in page.get('content_type','').lower()
                    and note.article_url(page.get('final_url',''))):
                doc = note.Metadata()
                doc.feed(page.get('html') or '')
                out['title'] = html.unescape(doc.meta.get('og:title',doc.page_title) or '').strip()[:200]
                out['published_date_claim'] = doc.meta.get('article:published_time') or doc.meta.get('datePublished')
                out['structured_prices'] = note.extract_price(doc.jsonld)
                out['price_status'] = ('構造化価格候補（原ページ確認必須）' if out['structured_prices'] else '未確認')
                out['status'] = 'metadata_read'
                out['relevance_status'] = '見出し上の関連語あり（競合性未確認）' if out['rank_score'] else '見出しからは関連性未確認'
            else:
                out['status'] = 'article_unavailable'
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            out.update(status='fetch_failed',error_type=type(exc).__name__)
        result['articles'].append(out)
    result['status'] = 'complete' if result['articles'] else 'no_article_links'
    return result
