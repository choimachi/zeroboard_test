"""ZEROBOARD Ver.39: bounded, public-page-only market search.

No API billing, browser automation, or sales estimates. All findings are leads until
note.com landing-page metadata is fetched and reviewed by the CEO.
"""
from __future__ import annotations

import html
import base64
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

import active_evidence as legacy

MAX_SEARCHES = 4
MAX_PAGES = 3
SEARCH_HOSTS = {"www.bing.com", "www.google.com", "www.google.co.jp"}
NOTE_HOSTS = legacy.ALLOWED_PAGE_HOSTS
STOP = {"向け", "ため", "相談", "できる", "する", "について", "簡易", "ミニ版", "有料", "レポート", "ワークショップ", "実践", "初心者", "記事", "情報", "個人", "方法", "解説", "チェック", "テンプレート"}


def _clean(text: str, limit: int = 65) -> str:
    result = re.sub(r"[^\w一-龯ぁ-んァ-ンー\s]", " ", str(text or ""))
    return re.sub(r"\s+", " ", result).strip()[:limit]


def _seed_terms(title: str, reader: str = "", paid_value: str = "") -> tuple[str, list[str]]:
    content = " ".join([title, reader, paid_value]).lower()
    if any(word in content for word in ("副業", "aiでできる", "ai活用", "ワークショップ")):
        return "AI 副業", ["ChatGPT 副業 始め方", "AI活用 個別相談", "AI 副業 講座"]
    if any(word in content for word in ("金利", "ローン", "家計", "利上げ")):
        return "金利 家計", ["住宅ローン 金利 シミュレーション", "金利 家計 ワークブック", "金利上昇 対策"]
    if any(word in content for word in ("aiインフラ", "gpu", "クラウド費用", "投資家")):
        return "AI コスト", ["GPU クラウド コスト 分析", "AI インフラ 投資 分析", "クラウド コスト 計算"]
    if any(word in content for word in ("python", "プログラミング")):
        return "Python 初心者", ["Python 初心者 教材", "Python 入門 講座", "Python 学習 ノート"]
    # For other ideas, avoid sending entire AI-generated product labels to search.
    tokens = [t for t in re.split(r"\s+|・|／|\(|\)|（|）", _clean(title, 70)) if len(t) >= 2 and t not in STOP]
    tokens = [re.sub(r"(?:向け|ミニ版|ワークショップ|レポート|相談|簡易)$", "", t) for t in tokens]
    tokens = [t[:16] for t in tokens if len(t) > 2][:2]
    seed = " ".join(tokens) or _clean(title, 18)
    return seed[:36], [seed + " 有料", seed + " 教材", seed + " 相談"]


def build_queries(title: str, reader: str = "", paid_value: str = "", custom: str = "") -> list[str]:
    seed, related = _seed_terms(title, reader, paid_value)
    custom = _clean(custom, 36)
    phrases = [custom or seed] + related
    normalized = []
    for phrase in phrases:
        phrase = _clean(phrase, 46)
        if phrase and phrase not in normalized:
            normalized.append(phrase)
    return normalized[:MAX_SEARCHES]


def _canonical_note(link: str, depth: int = 0) -> str | None:
    """Accept direct note article links and unwrap common search redirects safely."""
    if depth > 3 or not link:
        return None
    try:
        url = html.unescape(str(link)).strip().replace('\\/', '/')
        parsed = urlparse(url)
        if parsed.scheme not in {'https', 'http'}:
            return None
        host = (parsed.hostname or '').lower()
        if host in NOTE_HOSTS:
            if parsed.scheme != 'https':
                return None
            # note URLs: /author/n/n123... and /n/n123... (not profiles/search pages)
            if not re.fullmatch(r'/(?:[^/]+/)?n/n[a-zA-Z0-9_-]{5,}', parsed.path):
                return None
            return urlunparse(('https', host, parsed.path, '', '', ''))
        if host not in SEARCH_HOSTS and host != 'www.bing.co.jp':
            return None
        query = urllib.parse.parse_qs(parsed.query)
        for key in ('url', 'q', 'target', 'r', 'u'):
            for value in query.get(key, []):
                value = urllib.parse.unquote(value)
                if value.startswith('http'):
                    found = _canonical_note(value, depth + 1)
                    if found:
                        return found
                # Bing tracking URLs sometimes use base64 with a two-character prefix.
                if key == 'u' and value.startswith('a1') and len(value) < 4000:
                    encoded = value[2:]
                    try:
                        decoded = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode('utf-8')
                        found = _canonical_note(decoded, depth + 1)
                        if found:
                            return found
                    except (ValueError, UnicodeDecodeError):
                        pass
        return None
    except (ValueError, TypeError):
        return None


def _note_links_in_text(text: str) -> list[str]:
    """Find explicit note links in plain text, HTML attributes and escaped RSS snippets."""
    decoded = html.unescape(str(text or '')).replace('\\/', '/')
    variants = [decoded, urllib.parse.unquote(decoded)]
    candidates = []
    for chunk in variants:
        for match in re.findall(r'https?://(?:www\.)?note\.com/[^\s<>"\\]+', chunk, re.I):
            # Strip trailing punctuation from prose, without accepting non-note hosts.
            found = _canonical_note(match.rstrip('.,;!)]}）、。'))
            if found and found not in candidates:
                candidates.append(found)
    return candidates


def _parse_bing_rss(payload: str) -> list[dict]:
    root = ET.fromstring(payload)
    leads = []
    for item in root.findall('.//item'):
        title = html.unescape(item.findtext('title') or '')[:240]
        desc = html.unescape(re.sub(r'<[^>]*>', ' ', item.findtext('description') or ''))[:360]
        link_value = (item.findtext('link') or '').strip()
        links = [_canonical_note(link_value)] + _note_links_in_text(link_value + ' ' + (item.findtext('description') or ''))
        for link in dict.fromkeys(x for x in links if x):
            leads.append({'url':link, 'title':title, 'snippet':desc,
                          'search_published_at': item.findtext('pubDate') or '未確認'})
    return leads


class _GoogleResults(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        if not href:
            return
        self.hrefs.append(href)
        if href.startswith('/url?'):
            href = 'https://www.google.com' + href
        candidate = _canonical_note(href)
        if candidate and candidate not in self.links:
            self.links.append(candidate)


def _parse_google_html(payload: str) -> list[dict]:
    parser = _GoogleResults()
    parser.feed(payload)
    urls = list(parser.links)
    # Some search-page variants embed escaped URLs rather than a direct anchor.
    for url in _note_links_in_text(payload):
        if url not in urls:
            urls.append(url)
    return [{'url': url, 'title': '', 'snippet': '', 'search_published_at':'未確認'} for url in urls]


def _diagnose(payload: str, engine: str, parsed: list[dict]) -> dict:
    """Counts and sanitized hostnames only; never expose raw search HTML or tokens."""
    diagnostic = {'note_mentions': len(re.findall(r'note\.com', payload, re.I)),
                  'found_note_articles': len(parsed)}
    if engine == 'Bing Web RSS':
        root = ET.fromstring(payload)
        items = root.findall('.//item')
        diagnostic['raw_results'] = len(items)
        hosts = []
        for item in items[:5]:
            host = (urlparse((item.findtext('link') or '').strip()).hostname or 'URLなし')
            if host not in hosts:
                hosts.append(host)
        diagnostic['sample_hosts'] = hosts
    else:
        parser = _GoogleResults()
        parser.feed(payload)
        diagnostic['raw_results'] = len(parser.hrefs)
        hosts = []
        for href in parser.hrefs[:25]:
            if href.startswith('/url?'):
                host = 'www.google.com/転送URL'
            else:
                host = urlparse(href).hostname or '相対リンク'
            if host not in hosts:
                hosts.append(host)
        diagnostic['sample_hosts'] = hosts[:6]
        diagnostic['possible_restriction'] = bool(re.search(r'captcha|unusual traffic|consent\.google|sorry/index', payload, re.I))
    return diagnostic


def research(title: str, reader: str = "", paid_value: str = "", custom: str = "") -> dict:
    """Four search HTTP requests at most, three checked article pages at most."""
    if not str(title).strip(): raise ValueError('商品候補名が必要です')
    queries = build_queries(title, reader, paid_value, custom)
    search_logs, leads, seen, errors = [], [], set(), []
    # 3 distinct Bing web queries + 1 Google general web query (not Google News).
    for idx, query in enumerate(queries):
        if idx < 3:
            engine = 'Bing Web RSS'
            url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': 'site:note.com '+query, 'format': 'rss'})
            parser = _parse_bing_rss
        else:
            engine = 'Google Web HTML'
            url = 'https://www.google.com/search?' + urllib.parse.urlencode({'q':'site:note.com/ '+query, 'num':'10'})
            parser = _parse_google_html
        log = {'engine':engine, 'query':query, 'candidate_count':0, 'status':'取得不可'}
        try:
            payload, _ = legacy._fetch(url, SEARCH_HOSTS)
            parsed = parser(payload)
            diag = _diagnose(payload, engine, parsed)
            log.update(diag)
            log['candidate_count'] = len(parsed)
            count = diag['raw_results']
            mentions = diag['note_mentions']
            sample_hosts = ', '.join(diag['sample_hosts'][:3]) or 'なし'
            if parsed:
                log['status'] = f'記事URL抽出成功（検索リンク{count}・note表記{mentions}）'
            elif diag.get('possible_restriction'):
                log['status'] = '検索サービス側の制限ページ疑い（要確認）'
            elif count == 0:
                log['status'] = '検索リンク0件／検索サービスの応答形式を要確認'
            elif mentions == 0:
                log['status'] = f'検索リンク{count}件・note.com表記0件／候補不在か検索応答の問題（リンク先: {sample_hosts}）'
            else:
                log['status'] = f'検索リンク{count}件・note.com表記{mentions}件、記事URL抽出0件（リンク先: {sample_hosts}）'
            for item in parsed:
                if item['url'] not in seen:
                    seen.add(item['url'])
                    item['search_query'] = query
                    item['search_engine'] = engine
                    leads.append(item)
        except Exception as exc:
            log['status'] = '失敗: '+type(exc).__name__
            errors.append(engine+' / '+query+': '+type(exc).__name__+': '+str(exc)[:125])
        search_logs.append(log)
    results = []
    for item in leads[:MAX_PAGES]:
        try:
            page = legacy._page_info(item['url'])
            page['search_query'] = item['search_query']
            page['search_engine'] = item['search_engine']
            page['search_published_at'] = item['search_published_at']
            page['status'] = 'note.com記事ページの公開メタ情報を取得（売上は未確認）'
            results.append(page)
        except Exception as exc:
            results.append({'url':item['url'],'title':item.get('title') or 'タイトル未確認',
                            'status':'元ページを取得できず：検索上の候補にとどまる',
                            'search_query':item['search_query'],'search_engine':item['search_engine'],
                            'price_status':'未確認','review_status':'未確認','purchase_status':'未確認',
                            'article_published_at':'未確認'})
            errors.append('noteページ: '+type(exc).__name__+': '+str(exc)[:125])
    return {'candidate_title':title, 'query':queries[0], 'queries':queries,
            'retrieved_at':legacy.datetime.now(legacy.timezone.utc).isoformat(),
            'search_logs':search_logs, 'articles':results, 'errors':errors,
            'attempted_search_sources':len(search_logs),
            'checked_pages':sum('公開メタ情報を取得' in r['status'] for r in results),
            'explicit_price_leads':sum(bool(r.get('price_evidence')) for r in results),
            'verified_purchases':0,
            'conclusion':'検索結果は競合の候補であり、価格・購入人数・売上・需要を証明しません。価格は元ページでCEOが確認してください。',
            'limits':'BingのRSSとGoogle一般Web検索の取得可否・検索範囲に依存します。記事候補0件は競合不在を意味せず、検索停止・ブロック・検索URLの間接化・HTML仕様変更もあり得ます。',
            'search_limit':'最大4検索＋最大3記事の公開HTTPアクセス。OpenAI API不使用。'}


def meeting_brief(idea: dict, result: dict) -> str:
    lines = ['【Ver.39／競合追加調査・CEO最終判断待ち】',
             '商品：'+str(idea.get('title','')),
             '読者（仮説）：'+str(idea.get('reader','')),
             '有料価値（仮説）：'+str(idea.get('paid_value','')),
             '調査クエリ：'+', '.join(result['queries']),
             '元ページ取得：'+str(result['checked_pages'])+'件',
             '価格情報の手がかり：'+str(result['explicit_price_leads'])+'件（現行価格ではない）',
             '売上・購入人数・レビュー：未確認']
    for a in result['articles'][:3]:
        lines.append('参考ページ：'+str(a.get('title',''))+'／'+a['url']+'／確認状況：'+a['status'])
    lines.extend(['制約：'+result['limits'],
                  '会議では記事制作の承認をせず、購入需要の証拠の追加確認と他候補の優先順位を議論する。',
                  'CEO承認前の生成・公開・購入・支出は禁止。'])
    return '\n'.join(lines)[:5600]
