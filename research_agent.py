"""ZEROBOARD Ver.31 daily evidence-first research agent.

Runs in GitHub Actions independently of Streamlit. Public RSS metadata only;
never downloads or republishes full copyrighted news articles.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
MODEL = os.getenv('RESEARCH_MODEL', 'gpt-5-mini')
MAX_ITEMS_EACH = 5
MAX_PROMPT_CHARS = 13500
# Conservative *configurable* cost estimate, NOT provider-side billing/cap.
BUDGET_YEN = 500.0
MAX_ESTIMATED_RUN_YEN = 25.0
USDJPY = float(os.getenv('RESEARCH_USDJPY_ESTIMATE', '160'))
INPUT_USD_PER_M = float(os.getenv('RESEARCH_INPUT_USD_PER_M', '1.00'))
OUTPUT_USD_PER_M = float(os.getenv('RESEARCH_OUTPUT_USD_PER_M', '8.00'))
MAX_OUTPUT_TOKENS = 6000
FEEDS = [
 ('国内', 'Google News 日本 経済', 'https://news.google.com/rss/search?q='+urllib.parse.quote('日本 経済 金利 物価')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('国内', 'Google News 日本 政策 AI', 'https://news.google.com/rss/search?q='+urllib.parse.quote('日本 政策 AI 政治')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('海外', 'BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
 ('海外', 'Google News World Economy', 'https://news.google.com/rss/search?q='+urllib.parse.quote('global economy trade central bank')+'&hl=en-US&gl=US&ceid=US:en'),
 ('海外', 'Google News Technology', 'https://news.google.com/rss/search?q='+urllib.parse.quote('artificial intelligence policy regulation')+'&hl=en-US&gl=US&ceid=US:en'),
]


def clean_text(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', unescape(value or ''))).strip()[:380]


def rss_items(xml_data, region, feed_name):
    root = ET.fromstring(xml_data)
    items = []
    for item in root.findall('.//item')[:15]:
        title = clean_text(item.findtext('title'))
        link = (item.findtext('link') or '').strip()
        if not title or not link.startswith(('http://','https://')):
            continue
        items.append({'region': region, 'source': feed_name, 'title': title,
                      'url': link[:1800], 'published': clean_text(item.findtext('pubDate')),
                      'excerpt': clean_text(item.findtext('description'))})
    return items


def fetch_metadata():
    all_items, errors = [], []
    for region, name, url in FEEDS:
        try:
            request = urllib.request.Request(url, headers={'User-Agent':'ZEROBOARD-Research/1.0 (RSS metadata only)'})
            with urllib.request.urlopen(request, timeout=12) as res:
                data = res.read(500_000)
            all_items.extend(rss_items(data, region, name))
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {str(exc)[:120]}')
    used, selected = set(), []
    for region in ('国内', '海外'):
        pool = [i for i in all_items if i['region'] == region]
        for item in pool:
            normalized = re.sub(r'\W+', '', item['title']).lower()
            key = hashlib.sha256(normalized.encode()).hexdigest()
            if key in used:
                continue
            used.add(key)
            selected.append(item)
            if sum(x['region']==region for x in selected) >= MAX_ITEMS_EACH:
                break
    for idx, item in enumerate(selected, 1):
        item['id'] = f'S{idx:02d}'
    return selected, errors


def reserved_cost_yen():
    # Lower-bound for guarded preflight? No; upper approximation only.
    # Actual token count/pricing may differ, so hard enforcement is impossible here.
    return MAX_ESTIMATED_RUN_YEN


def estimate_yen(usage):
    input_tokens = int(getattr(usage, 'input_tokens', 0) or 0)
    output_tokens = int(getattr(usage, 'output_tokens', 0) or 0)
    return round((input_tokens*INPUT_USD_PER_M + output_tokens*OUTPUT_USD_PER_M)/1_000_000*USDJPY, 4), input_tokens, output_tokens


# Strict structured output prevents malformed/truncated free-form JSON from being
# silently treated as a valid report. This is not a factual verification system.
RESEARCH_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "object", "properties": {
            "headline": {"type": "string"}, "detail": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}}
        }, "required": ["headline", "detail", "source_ids"], "additionalProperties": False}},
        "comparisons": {"type": "array", "items": {"type": "object", "properties": {
            "theme": {"type": "string"}, "japan_view": {"type": "string"},
            "global_view": {"type": "string"}, "caveat": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}}
        }, "required": ["theme", "japan_view", "global_view", "caveat", "source_ids"], "additionalProperties": False}},
        "product_ideas": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "reader": {"type": "string"},
            "paid_value": {"type": "string"}, "validation": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}}
        }, "required": ["title", "reader", "paid_value", "validation", "source_ids"], "additionalProperties": False}},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["summary", "highlights", "comparisons", "product_ideas", "warnings"],
    "additionalProperties": False
}


def parse_research_response(response):
    """Parse a complete structured response; never accept truncated JSON."""
    status = getattr(response, 'status', None)
    if status and status != 'completed':
        details = getattr(response, 'incomplete_details', None)
        raise ValueError(f'AI出力が未完了（{status}、理由: {details}）。JSONを保存しません。')
    raw = (getattr(response, 'output_text', '') or '').strip()
    if not raw:
        raise ValueError('AIが空の回答を返しました。データは保存しません。')
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f'AI出力が不完全なJSONです（{exc.msg}）。データは保存しません。') from exc
    if not isinstance(report, dict):
        raise ValueError('AI出力がJSONオブジェクトではありません。')
    return report


def analyze_with_ai(items):
    from openai import OpenAI
    if not items:
        raise ValueError('情報源が0件のため推測によるレポート生成はしません。')
    slim = [{k:i[k] for k in ('id','region','source','title','published','excerpt')} for i in items]
    prompt = ('公開RSSの見出し・短い抜粋だけから日本語で調査報告を作ってください。全文は未読です。'
              'すべての具体的主張にsource_idsを付け、実際に与えられたIDだけ引用する。'
              '国内・海外メディア間で同一の出来事が確認できないとき比較を捏造しない。'
              '政治的立場を推奨せず、媒体の見出しに見える論点の違いを中立に記述する。'
              'ニュースの真偽や市場の売上は未検証と明記し、センセーショナルな断定を避ける。'
              '事業案の価格・需要は検証仮説として示し、外部記事の翻訳転載や無断販売を提案しない。'
              '短いJSONを返すこと。summaryは180文字以内、highlights最大3件、comparisons最大1件、product_ideas最大2件、warnings最大3件。'
              '各headlineとtitleは40文字以内、その他の説明文は各80文字以内。情報不足なら空配列にする。'
              '各要素のsource_idsには実在するS番号のみ使用。')
    response = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=45, max_retries=1).responses.create(
        model=MODEL, reasoning={'effort': 'low'}, instructions=prompt,
        input=json.dumps(slim, ensure_ascii=False)[:MAX_PROMPT_CHARS],
        max_output_tokens=MAX_OUTPUT_TOKENS,
        text={"format": {"type": "json_schema", "name": "daily_research_report",
                         "schema": RESEARCH_REPORT_SCHEMA, "strict": True}})
    report = parse_research_response(response)
    valid_ids = {i['id'] for i in items}
    for field, max_num in (('highlights',5),('comparisons',2),('product_ideas',3)):
        value = report.get(field)
        if not isinstance(value,list):
            raise ValueError(f'AI出力に{field}配列がありません。')
        report[field] = [x for x in value[:max_num] if isinstance(x,dict)
                         and isinstance(x.get('source_ids'),list)
                         and len(x['source_ids'])>0
                         and all(y in valid_ids for y in x['source_ids'])]
    report['summary'] = str(report.get('summary') or '')[:900]
    report['warnings'] = [str(w)[:300] for w in (report.get('warnings') or [])[:8]]
    cost, inp, out = estimate_yen(response.usage)
    return report, cost, inp, out


def run(dry_run=False):
    today = dt.datetime.now(JST).date().isoformat()
    if dry_run:
        items=[{'region':'国内','source':'サンプル（架空）','title':'テスト用国内ニュース','url':'https://example.com/jp',
                'published':'','excerpt':'実ニュースではありません','id':'S01'},
               {'region':'海外','source':'サンプル（架空）','title':'Test world news','url':'https://example.com/en',
                'published':'','excerpt':'This is not real news','id':'S02'}]
        print(json.dumps({'date':today,'dry_run':True,'source_items':items,'message':'API通信・DB保存なし'}, ensure_ascii=False,indent=2))
        return 0
    for key in ('OPENAI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'):
        if not os.getenv(key):
            print(f'Missing required secret: {key}',file=sys.stderr)
            return 2
    from supabase import create_client
    db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    # Fail closed on DB access errors; never burn API tokens when unable to track budget.
    existing = db.table('research_daily_reports').select('id').eq('report_date',today).limit(1).execute().data
    if existing:
        print('Already published today; skip OpenAI request')
        return 0
    month_start = today[:7]+'-01'
    usage_rows = db.table('research_daily_reports').select('estimated_cost_yen').gte('report_date',month_start).execute().data or []
    spent = sum(float(x.get('estimated_cost_yen') or 0) for x in usage_rows)
    if spent + reserved_cost_yen() > BUDGET_YEN:
        print(f'Estimated monthly safety threshold reached: {spent:.2f} yen; no API call')
        return 0
    items, errors = fetch_metadata()
    if not items:
        print('RSS取得失敗：分析せず終了 '+repr(errors),file=sys.stderr)
        return 1
    report, cost, input_tokens, output_tokens = analyze_with_ai(items)
    payload = {'report_date':today,'source_items':items,'report':report,'feed_errors':errors,
               'model':MODEL,'estimated_cost_yen':cost,'input_tokens':input_tokens,'output_tokens':output_tokens}
    # Unique report_date additionally protects against duplicate saves.
    db.table('research_daily_reports').insert(payload).execute()
    print(f'Saved {today}: {len(items)} items; estimated cost {cost:.2f} yen; token usage {input_tokens}/{output_tokens}')
    return 0


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dry-run',action='store_true',help='Run without network/API/DB; show sample payload')
    args=parser.parse_args()
    try:
        sys.exit(run(dry_run=args.dry_run))
    except Exception as exc:
        print(f'Research agent stopped safely: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)
