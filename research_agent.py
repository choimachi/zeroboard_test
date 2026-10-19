"""ZEROBOARD Ver.36 daily evidence-first research agent.

Runs in GitHub Actions independently of Streamlit. Public RSS metadata only;
never downloads or republishes full copyrighted news articles.
"""
import argparse
import datetime as dt
import email.utils
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
MAX_MARKET_ITEMS = 3
MAX_SOURCE_AGE_DAYS = 21
MAX_PROMPT_CHARS = 13500
# Conservative *configurable* cost estimate, NOT provider-side billing/cap.
BUDGET_YEN = 500.0
MAX_ESTIMATED_RUN_YEN = 25.0
USDJPY = float(os.getenv('RESEARCH_USDJPY_ESTIMATE', '160'))
INPUT_USD_PER_M = float(os.getenv('RESEARCH_INPUT_USD_PER_M', '1.00'))
OUTPUT_USD_PER_M = float(os.getenv('RESEARCH_OUTPUT_USD_PER_M', '8.00'))
MAX_OUTPUT_TOKENS = 6000
FEEDS = [
 ('国内', '日本経済・金利', 'https://news.google.com/rss/search?q='+urllib.parse.quote('日本経済 金利 物価')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('国内', '日本政策・社会', 'https://news.google.com/rss/search?q='+urllib.parse.quote('日本 政策 社会')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('国内', '日本AI・ビジネス', 'https://news.google.com/rss/search?q='+urllib.parse.quote('日本 AI ビジネス 規制')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('海外', 'BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
 ('海外', 'World Economy', 'https://news.google.com/rss/search?q='+urllib.parse.quote('world economy trade central bank')+'&hl=en-US&gl=US&ceid=US:en'),
 ('海外', 'World Technology', 'https://news.google.com/rss/search?q='+urllib.parse.quote('AI regulation investment technology')+'&hl=en-US&gl=US&ceid=US:en'),
 # These feeds show public *signals* and discussions, NOT note sales data.
 ('市場', 'デジタル商品・note', 'https://news.google.com/rss/search?q='+urllib.parse.quote('note 有料記事 テンプレート 初心者 販売')+'&hl=ja&gl=JP&ceid=JP:ja'),
 ('市場', '小規模事業・副業', 'https://news.google.com/rss/search?q='+urllib.parse.quote('副業 AI 活用 小規模事業')+'&hl=ja&gl=JP&ceid=JP:ja'),
]



def clean_text(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', unescape(value or ''))).strip()[:380]


def normalized_published_date(value):
    try:
        parsed=email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo: return parsed.astimezone(JST).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return None


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
                      'published_date': normalized_published_date(item.findtext('pubDate')),
                      'retrieved_at': dt.datetime.now(JST).isoformat(timespec='seconds'),
                      'excerpt': clean_text(item.findtext('description'))})
    return items


def age_days(published, now=None):
    """Return JST-relative age where RSS date is parseable; future/unknown => None."""
    if not published:
        return None
    try:
        d=email.utils.parsedate_to_datetime(published)
        if d.tzinfo is None:
            return None
        now=now or dt.datetime.now(dt.timezone.utc)
        age=(now.astimezone(dt.timezone.utc)-d.astimezone(dt.timezone.utc)).total_seconds()/86400
        return int(age) if age>=0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def pick_diverse(items, max_count, used):
    """Round-robin across feeds before taking a second item; skip dated old news."""
    pools={}
    for item in items:
        age=age_days(item.get('published'))
        if age is not None and age>MAX_SOURCE_AGE_DAYS:
            continue
        normalized=re.sub(r'\W+', '', item['title']).lower()
        key=hashlib.sha256(normalized.encode()).hexdigest()
        if key in used:
            continue
        entry=dict(item)
        entry['_key']=key
        entry['age_days']=age
        pools.setdefault(item['source'],[]).append(entry)
    selected=[]
    while pools and len(selected)<max_count:
        made_progress=False
        for source in list(pools):
            pool=pools[source]
            while pool and pool[0]['_key'] in used:
                pool.pop(0)
            if pool and len(selected)<max_count:
                entry=pool.pop(0)
                used.add(entry.pop('_key'))
                selected.append(entry)
                made_progress=True
            if not pool:
                del pools[source]
        if not made_progress:
            break
    return selected


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
    for region, limit in (('国内',MAX_ITEMS_EACH),('海外',MAX_ITEMS_EACH),('市場',MAX_MARKET_ITEMS)):
        selected.extend(pick_diverse([i for i in all_items if i['region']==region],limit,used))
    for idx, item in enumerate(selected,1):
        item['id']=f'S{idx:02d}'
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
        "market_signals": {"type": "array", "items": {"type": "object", "properties": {
            "theme": {"type": "string"}, "observation": {"type": "string"},
            "opportunity": {"type": "string"}, "validation": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}}
        }, "required": ["theme", "observation", "opportunity", "validation", "source_ids"], "additionalProperties": False}},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["summary", "highlights", "comparisons", "product_ideas", "market_signals", "warnings"],
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


def analyze_with_ai(items, previous_titles=None):
    from openai import OpenAI
    if not items:
        raise ValueError('情報源が0件のため推測によるレポート生成はしません。')
    slim = [{k:i[k] for k in ('id','region','source','title','published','excerpt')} for i in items]
    previous_titles = [str(t)[:130] for t in (previous_titles or []) if t][:12]
    prompt = ('ZEROBOARD市場調査AI。入力は公開RSSの見出しと短い抜粋のみであり、全文・売上・note人気ランキングは未確認。'
              '日本語の短いJSONだけ返す。すべての主張は見出しで観測されたことと推測を区別し実在source_idsを付ける。'
              'highlights最大3件、comparisons最大1件、market_signals最大2件、product_ideas最大2件、warnings最大3件。'
              'summaryは150字、各説明文は80字以内。'
              'comparisonsは同じ出来事を報じる国内・海外の双方の根拠があるときだけ作る。'
              '単なる日本経済ニュース対英国経済ニュースの比較は禁止。情報不足ならcomparisons=[]。'
              'market_signalsは「市場」カテゴリの情報や他の出典に観測できる実際の話題と、未検証の機会・低費用テストを区別。'
              'noteの売れ行き・スキ数・販売件数・価格は入力にないので創作しない。'
              'product_ideasは広く売れる可能性のある商品（note考察・分析記事を含む）を優先し、無料/有料の具体的価値と無料の検証方法を提案。'
              '単なるニュース要約・専門家向け架空レポート・実体験の捏造・高額制作前提は禁止。購入需要が弱いテーマは企画にしない。'
              '過去に提案済み・購買根拠不足のテーマを言い換えただけで再提案しない。'
              '別の読者層と別の困りごとを持つ代替案を探す。'
              '毎回、実用・手順型と考察・分析型を比較する。無理に2案出さず、根拠が不足なら0案でよい。'
              '記事制作を自動開始してはならない。'
              'ニュース翻訳の無断転載は禁止。経済・政治報道の評価は中立に。'
              'source_idsは与えられたID以外禁止。')

    response = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=45, max_retries=1).responses.create(
        model=MODEL, reasoning={'effort': 'low'}, instructions=prompt,
        input=json.dumps({'rss_items':slim,'past_ideas_to_avoid':previous_titles}, ensure_ascii=False)[:MAX_PROMPT_CHARS],
        max_output_tokens=MAX_OUTPUT_TOKENS,
        text={"format": {"type": "json_schema", "name": "daily_research_report",
                         "schema": RESEARCH_REPORT_SCHEMA, "strict": True}})
    report = parse_research_response(response)
    valid_ids = {i['id'] for i in items}
    for field, max_num in (('highlights',3),('comparisons',1),('market_signals',2),('product_ideas',2)):
        value = report.get(field)
        if not isinstance(value,list):
            raise ValueError(f'AI出力に{field}配列がありません。')
        report[field] = [x for x in value[:max_num] if isinstance(x,dict)
                         and isinstance(x.get('source_ids'),list)
                         and len(x['source_ids'])>0
                         and all(y in valid_ids for y in x['source_ids'])]
    # Never show a domestic/overseas contrast when sources are all from one side.
    regions={i['id']:i['region'] for i in items}
    report['comparisons']=[c for c in report['comparisons']
        if {'国内','海外'}.issubset({regions.get(x) for x in c['source_ids']})]
    report['research_methods']={
        'scope':'RSS見出し・短い抜粋のみ / 記事全文未読 / note販売数未確認',
        'selection':'公開情報源別に分散・21日超の既知日付は除外。記事公開日と取得日時は別記録',
        'coverage':{group:sum(i['region']==group for i in items) for group in ('国内','海外','市場')},
        'report_version':36, 'avoided_recent_ideas': len(previous_titles)}
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
    # Previously proposed themes: reuse saved DB text to avoid repeated weak products.
    # Do not issue another API request to rank products.
    history = db.table('research_daily_reports').select('report').order('report_date',desc=True).limit(10).execute().data or []
    previous_titles=[]
    for row in history:
        for idea in (row.get('report') or {}).get('product_ideas') or []:
            if isinstance(idea,dict) and idea.get('title'):
                previous_titles.append(str(idea['title']))
    report, cost, input_tokens, output_tokens = analyze_with_ai(items, previous_titles=previous_titles)
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
