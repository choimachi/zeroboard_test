"""CEO-triggered product evidence discovery. Public RSS search metadata only.

No private data, authenticated scraping, purchases, automated publishing, or
assertions that snippets establish real sales. Always report unknowns explicitly.
"""
import datetime as dt 
import email .utils 
import hashlib 
import json 
import os 
import re 
import urllib .parse 
import urllib .request 
import xml .etree .ElementTree as ET 
from html import unescape 
from zoneinfo import ZoneInfo 

JST =ZoneInfo ('Asia/Tokyo')
MAX_CANDIDATES_PER_DAY =2 
MAX_ITEMS_PER_CANDIDATE =12 
MODEL =os .getenv ('RESEARCH_MODEL','gpt-5-mini')


def readable (value ,limit =380 ):
    return re .sub (r'\s+',' ',re .sub (r'<[^>]*>',' ',unescape (value or ''))).strip ()[:limit ]


def parse_feed (xml_bytes ,label ,retrieved_at ):
    root =ET .fromstring (xml_bytes )
    out =[]
    for node in root .findall ('.//item')[:15 ]:
        url =(node .findtext ('link')or '').strip ()
        if urllib .parse .urlsplit (url ).scheme not in ('http','https'):
            continue 
        title =readable (node .findtext ('title'),220 )
        if not title :
            continue 
        raw_date =node .findtext ('pubDate')or ''
        published =None 
        try :
            parsed =email .utils .parsedate_to_datetime (raw_date )
            if parsed .tzinfo :
                published =parsed .astimezone (JST ).date ().isoformat ()
        except (ValueError ,TypeError ,OverflowError ):
            pass 
        out .append ({'title':title ,'url':url [:1800 ],'excerpt':readable (node .findtext ('description')),
        'source':label ,'published_date':published ,'retrieved_at':retrieved_at })
    return out 


def search_public_metadata (title ,reader ,max_items =MAX_ITEMS_PER_CANDIDATE ):
    """Search public RSS metadata via fixed Bing RSS endpoint; failures explicit."""
    searched_at =dt .datetime .now (JST ).isoformat (timespec ='seconds')
    subject =re .sub (r'\s+',' ',str (title or '')).strip ()[:70 ]
    audience =str (reader or '').strip ()[:32 ]
    queries =[
    (f'{subject } {audience } 有料 note 価格','公開記事・価格候補'),
    (f'{subject } site:note.com 有料','note競合候補'),
    (f'{subject } テンプレート 教材 販売 口コミ','競合・レビュー候補'),
    ]
    evidence =[];errors =[];seen =set ()
    for query ,label in queries :
        url ='https://www.bing.com/search?format=rss&q='+urllib .parse .quote (query )
        try :
            req =urllib .request .Request (url ,headers ={'User-Agent':'ZEROBOARD/1.0 research assistant (RSS metadata only)','Accept':'application/rss+xml, application/xml;q=0.9'})
            with urllib .request .urlopen (req ,timeout =10 )as response :
                raw =response .read (320_000 )
            batch =parse_feed (raw ,label ,searched_at )
            for item in batch :
                identity =hashlib .sha256 (item ['url'].encode ()).hexdigest ()
                if identity not in seen and len (evidence )<max_items :
                    seen .add (identity );evidence .append (item )
        except Exception as exc :
            errors .append (f'{label }：{type (exc ).__name__ }（公開検索を取得できません）')
    for n ,item in enumerate (evidence ,1 ):item ['id']=f'E{n :02d}'
    return evidence ,errors ,searched_at 


EVALUATION_SCHEMA ={
'type':'object','properties':{
'customer_pain':{'type':'string'},
'news_attention':{'type':'string'},
'purchase_demand':{'type':'string'},
'competitors':{'type':'array','items':{'type':'object','properties':{
'name':{'type':'string'},'public_price':{'type':'string'},'purchase_or_review':{'type':'string'},
'evidence_ids':{'type':'array','items':{'type':'string'}},'certainty':{'type':'string'}
},'required':['name','public_price','purchase_or_review','evidence_ids','certainty'],'additionalProperties':False }},
'production_tasks':{'type':'array','items':{'type':'string'}},
'unknowns':{'type':'array','items':{'type':'string'}},
'low_cost_validation':{'type':'array','items':{'type':'string'}},
'recommendation':{'type':'string'},'rationale':{'type':'string'},
'supporting_evidence_ids':{'type':'array','items':{'type':'string'}}
},'required':['customer_pain','news_attention','purchase_demand','competitors','production_tasks',
'unknowns','low_cost_validation','recommendation','rationale','supporting_evidence_ids'],
'additionalProperties':False }


def safe_result (data ,evidence ):
    valid ={x ['id']for x in evidence }
    if not isinstance (data ,dict ):raise ValueError ('AIの評価形式が不正です')
    cleaned =dict (data )
    if cleaned .get ('recommendation')not in ('会議で検討','追加調査','見送り'):
        cleaned ['recommendation']='追加調査'
    cleaned ['supporting_evidence_ids']=[x for x in data .get ('supporting_evidence_ids',[])if x in valid ]
    competitors =[]
    for row in data .get ('competitors',[])[:5 ]:
        if not isinstance (row ,dict ):continue 
        ids =[x for x in row .get ('evidence_ids',[])if x in valid ]
        if ids :competitors .append ({**row ,'evidence_ids':ids })
    cleaned ['competitors']=competitors 
    cleaned ['production_tasks']=[str (x )[:240 ]for x in data .get ('production_tasks',[])[:8 ]]
    cleaned ['unknowns']=[str (x )[:240 ]for x in data .get ('unknowns',[])[:10 ]]
    if not evidence :
        cleaned ['purchase_demand']='確認できる外部根拠なし（検索結果なし）。購入需要は未確認。'
        cleaned ['competitors']=[]
        cleaned ['recommendation']='追加調査'
    return cleaned 


def evaluate_candidate (candidate ,evidence ):
    """One short OpenAI call; no claim of full article reading or proven sales."""
    from openai import OpenAI 
    inputs ={'candidate':{k :str (candidate .get (k )or '')[:600 ]for k in ('title','reader','paid_value','validation')},
    'observations':[{'id':x ['id'],'title':x ['title'],'excerpt':x ['excerpt'],
    'published_date':x ['published_date'],'retrieved_at':x ['retrieved_at'],
    'source':x ['source']}for x in evidence ]}
    instructions =('あなたは独立した商品需要の検証担当。検索結果は公開RSS見出し・抜粋だけで記事本文未読。'
    'ニュースの話題性と、実際の購買需要を明確に分離する。'
    '競合候補は検索結果に対応するIDがある実在候補だけ。'
    '価格は明記されているときだけ表記し、なければ「未確認」。'
    '実際の購入・販売件数・レビュー件数は裏付けがなければ必ず「未確認」。'
    '「購入需要」の根拠は価格情報・単なる記事見出しと区別する。'
    '顧客課題、競合、公開価格、確認可能な販売・レビュー証拠、制作作業、未確認事項、'
    '低費用の検証方法を日本語で短く書く。証拠がなければ不足を明示し、根拠を創作しない。'
    '具体的なURLは入力に載せないのでIDを出典とする。'
    'recommendationは「会議で検討」「追加調査」「見送り」のいずれか。'
    '会議で検討は採用・販売許可ではない。JSON以外は返さない。')
    response =OpenAI (api_key =os .environ ['OPENAI_API_KEY'],timeout =50 ,max_retries =1 ).responses .create (
    model =MODEL ,reasoning ={'effort':'low'},instructions =instructions ,
    input =json .dumps (inputs ,ensure_ascii =False )[:12000 ],max_output_tokens =3500 ,
    text ={'format':{'type':'json_schema','name':'product_evidence_check',
    'schema':EVALUATION_SCHEMA ,'strict':True }})
    if response .status !='completed':
        raise ValueError ('AI分析が未完了のため、結果を保存しません')
    evaluation =safe_result (json .loads (response .output_text ),evidence )
    usage =response .usage 
    inp =int (getattr (usage ,'input_tokens',0 )or 0 )
    out =int (getattr (usage ,'output_tokens',0 )or 0 )
    # Same user-configurable estimate as the daily research task.
    usd_jpy =float (os .getenv ('RESEARCH_USDJPY_ESTIMATE','160'))
    cost =round ((inp *float (os .getenv ('RESEARCH_INPUT_USD_PER_M','1.00'))+
    out *float (os .getenv ('RESEARCH_OUTPUT_USD_PER_M','8.00')))*usd_jpy /1_000_000 ,4 )
    return evaluation ,cost ,inp ,out 


def _short(value, limit=340):
    return re.sub(r"\s+", " ", str(value or "未確認")).strip()[:limit]


def note_pitch(record):
    """A hypothesis-only outline based on existing evidence; no new API call."""
    info = record.get('evaluation') or {}
    title = _short(record.get('candidate_title'), 140)
    reader = _short(record.get('candidate_reader'), 180)
    tasks = [_short(x, 130) for x in (info.get('production_tasks') or [])[:5]]
    concerns = [_short(x, 130) for x in (info.get('unknowns') or [])[:5]]
    return {
        'title': f"【実践ガイド案】{title}",
        'reader': reader,
        'free_value': '対象読者の悩みと調査で分かった範囲を公開し、何が未確認かを明示する。',
        'paid_value': ('読者が自分で使える手順・チェックリスト・記入用テンプレートを提供する。'
                       '次の制作候補：' + '／'.join(tasks or ['実践テンプレート作成']) +
                       '。未検証のニーズを売れた実績として書かない。'),
        'instructions': ('市場調査からの候補。記事本文未読・販売実績未確認。\n'
                         '対象読者：'+reader+'\n顧客課題：'+_short(info.get('customer_pain'))+
                         '\n購入需要の検証状況：'+_short(info.get('purchase_demand'))+
                         '\n未確認事項：'+ '／'.join(concerns or ['競合価格・購入需要・レビュー'])+
                         '\n価格は仮説。検索結果の内容を検証せずに引用・転記しない。'+
                         '具体的な作業手順とオリジナルの記入テンプレートを中心に制作する。'
                         '公開・販売はCEOの承認後。')
    }


def meeting_brief(record):
    """Short readable evidence memo. No raw JSON or fabricated paid demand."""
    info = record.get('evaluation') or {}
    evidence = {x.get('id'): x for x in (record.get('evidence') or [])}
    ids = list(dict.fromkeys(
        list(info.get('supporting_evidence_ids') or []) +
        [e for c in (info.get('competitors') or []) for e in (c.get('evidence_ids') or [])]
    ))[:6]
    competitors = []
    for c in (info.get('competitors') or [])[:3]:
        competitors.append('- '+_short(c.get('name'), 100)+' / 公開価格：'+
                           _short(c.get('public_price'), 70)+' / 購入・レビュー：'+
                           _short(c.get('purchase_or_review'), 110))
    citations = []
    for key in ids:
        if key in evidence:
            e=evidence[key]
            citations.append(f"- [{key}] {_short(e.get('title'), 90)} / {_short(e.get('url'), 230)} / 公開日:{e.get('published_date') or '未確認'} / 取得日時:{e.get('retrieved_at') or '未記録'}")
    items = lambda k,n: ' / '.join(_short(x, 140) for x in (info.get(k) or [])[:n]) or '未確認'
    return '\n'.join([
        '【ZEROBOARD / 根拠付き商品候補・CEO判断待ち】',
        '目的：noteで初売上1件を目指し、まず低費用・非公開の需要検証を行う。',
        '商品候補：'+_short(record.get('candidate_title'), 180),
        '想定読者：'+_short(record.get('candidate_reader'), 180),
        '顧客の悩み：'+_short(info.get('customer_pain')),
        'ニュースの話題性：'+_short(info.get('news_attention')),
        '購入需要の根拠（未確認なら未確認）：'+_short(info.get('purchase_demand')),
        '競合：\n'+('\n'.join(competitors) or '- 公開情報で未確認'),
        '制作作業：'+items('production_tasks', 5),
        '低費用の検証方法：'+items('low_cost_validation', 4),
        '未確認事項：'+items('unknowns', 5),
        '調査AIの推奨：'+_short(info.get('recommendation'), 60),
        '根拠リンク（検索結果の見出し・抜粋のみ）：\n'+('\n'.join(citations) or '- 根拠リンク未確認'),
        '重要制約：本文未読、売上・購入実績・価格・レビューの未確認事項は実績扱い禁止。',
        '経営会議への依頼：4役員が事実と仮説を分け、0〜1000円の検証案、差別化、note記事の無料/有料部分、停止基準を提案。',
        'CEOの承認まで：公開・有料課金・広告出稿・外部発注・支出は一切しない。'
    ])[:6500]
