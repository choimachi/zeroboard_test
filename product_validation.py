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
    (f'{subject } {audience } \u6709\u6599 note \u4fa1\u683c','\u516c\u958b\u8a18\u4e8b\u30fb\u4fa1\u683c\u5019\u88dc'),
    (f'{subject } site:note.com \u6709\u6599','note\u7af6\u5408\u5019\u88dc'),
    (f'{subject } \u30c6\u30f3\u30d7\u30ec\u30fc\u30c8 \u6559\u6750 \u8ca9\u58f2 \u53e3\u30b3\u30df','\u7af6\u5408\u30fb\u30ec\u30d3\u30e5\u30fc\u5019\u88dc'),
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
            errors .append (f'{label }\uff1a{type (exc ).__name__ }\uff08\u516c\u958b\u691c\u7d22\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\uff09')
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
    if not isinstance (data ,dict ):raise ValueError ('AI\u306e\u8a55\u4fa1\u5f62\u5f0f\u304c\u4e0d\u6b63\u3067\u3059')
    cleaned =dict (data )
    if cleaned .get ('recommendation')not in ('\u4f1a\u8b70\u3067\u691c\u8a0e','\u8ffd\u52a0\u8abf\u67fb','\u898b\u9001\u308a'):
        cleaned ['recommendation']='\u8ffd\u52a0\u8abf\u67fb'
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
        cleaned ['purchase_demand']='\u78ba\u8a8d\u3067\u304d\u308b\u5916\u90e8\u6839\u62e0\u306a\u3057\uff08\u691c\u7d22\u7d50\u679c\u306a\u3057\uff09\u3002\u8cfc\u5165\u9700\u8981\u306f\u672a\u78ba\u8a8d\u3002'
        cleaned ['competitors']=[]
        cleaned ['recommendation']='\u8ffd\u52a0\u8abf\u67fb'
    return cleaned 


def evaluate_candidate (candidate ,evidence ):
    """One short OpenAI call; no claim of full article reading or proven sales."""
    from openai import OpenAI 
    inputs ={'candidate':{k :str (candidate .get (k )or '')[:600 ]for k in ('title','reader','paid_value','validation')},
    'observations':[{'id':x ['id'],'title':x ['title'],'excerpt':x ['excerpt'],
    'published_date':x ['published_date'],'retrieved_at':x ['retrieved_at'],
    'source':x ['source']}for x in evidence ]}
    instructions =('\u3042\u306a\u305f\u306f\u72ec\u7acb\u3057\u305f\u5546\u54c1\u9700\u8981\u306e\u691c\u8a3c\u62c5\u5f53\u3002\u691c\u7d22\u7d50\u679c\u306f\u516c\u958bRSS\u898b\u51fa\u3057\u30fb\u629c\u7c8b\u3060\u3051\u3067\u8a18\u4e8b\u672c\u6587\u672a\u8aad\u3002'
    '\u30cb\u30e5\u30fc\u30b9\u306e\u8a71\u984c\u6027\u3068\u3001\u5b9f\u969b\u306e\u8cfc\u8cb7\u9700\u8981\u3092\u660e\u78ba\u306b\u5206\u96e2\u3059\u308b\u3002'
    '\u7af6\u5408\u5019\u88dc\u306f\u691c\u7d22\u7d50\u679c\u306b\u5bfe\u5fdc\u3059\u308bID\u304c\u3042\u308b\u5b9f\u5728\u5019\u88dc\u3060\u3051\u3002'
    '\u4fa1\u683c\u306f\u660e\u8a18\u3055\u308c\u3066\u3044\u308b\u3068\u304d\u3060\u3051\u8868\u8a18\u3057\u3001\u306a\u3051\u308c\u3070\u300c\u672a\u78ba\u8a8d\u300d\u3002'
    '\u5b9f\u969b\u306e\u8cfc\u5165\u30fb\u8ca9\u58f2\u4ef6\u6570\u30fb\u30ec\u30d3\u30e5\u30fc\u4ef6\u6570\u306f\u88cf\u4ed8\u3051\u304c\u306a\u3051\u308c\u3070\u5fc5\u305a\u300c\u672a\u78ba\u8a8d\u300d\u3002'
    '\u300c\u8cfc\u5165\u9700\u8981\u300d\u306e\u6839\u62e0\u306f\u4fa1\u683c\u60c5\u5831\u30fb\u5358\u306a\u308b\u8a18\u4e8b\u898b\u51fa\u3057\u3068\u533a\u5225\u3059\u308b\u3002'
    '\u9867\u5ba2\u8ab2\u984c\u3001\u7af6\u5408\u3001\u516c\u958b\u4fa1\u683c\u3001\u78ba\u8a8d\u53ef\u80fd\u306a\u8ca9\u58f2\u30fb\u30ec\u30d3\u30e5\u30fc\u8a3c\u62e0\u3001\u5236\u4f5c\u4f5c\u696d\u3001\u672a\u78ba\u8a8d\u4e8b\u9805\u3001'
    '\u4f4e\u8cbb\u7528\u306e\u691c\u8a3c\u65b9\u6cd5\u3092\u65e5\u672c\u8a9e\u3067\u77ed\u304f\u66f8\u304f\u3002\u8a3c\u62e0\u304c\u306a\u3051\u308c\u3070\u4e0d\u8db3\u3092\u660e\u793a\u3057\u3001\u6839\u62e0\u3092\u5275\u4f5c\u3057\u306a\u3044\u3002'
    '\u5177\u4f53\u7684\u306aURL\u306f\u5165\u529b\u306b\u8f09\u305b\u306a\u3044\u306e\u3067ID\u3092\u51fa\u5178\u3068\u3059\u308b\u3002'
    'recommendation\u306f\u300c\u4f1a\u8b70\u3067\u691c\u8a0e\u300d\u300c\u8ffd\u52a0\u8abf\u67fb\u300d\u300c\u898b\u9001\u308a\u300d\u306e\u3044\u305a\u308c\u304b\u3002'
    '\u4f1a\u8b70\u3067\u691c\u8a0e\u306f\u63a1\u7528\u30fb\u8ca9\u58f2\u8a31\u53ef\u3067\u306f\u306a\u3044\u3002JSON\u4ee5\u5916\u306f\u8fd4\u3055\u306a\u3044\u3002')
    response =OpenAI (api_key =os .environ ['OPENAI_API_KEY'],timeout =50 ,max_retries =1 ).responses .create (
    model =MODEL ,reasoning ={'effort':'low'},instructions =instructions ,
    input =json .dumps (inputs ,ensure_ascii =False )[:12000 ],max_output_tokens =3500 ,
    text ={'format':{'type':'json_schema','name':'product_evidence_check',
    'schema':EVALUATION_SCHEMA ,'strict':True }})
    if response .status !='completed':
        raise ValueError ('AI\u5206\u6790\u304c\u672a\u5b8c\u4e86\u306e\u305f\u3081\u3001\u7d50\u679c\u3092\u4fdd\u5b58\u3057\u307e\u305b\u3093')
    evaluation =safe_result (json .loads (response .output_text ),evidence )
    usage =response .usage 
    inp =int (getattr (usage ,'input_tokens',0 )or 0 )
    out =int (getattr (usage ,'output_tokens',0 )or 0 )
    # Same user-configurable estimate as the daily research task.
    usd_jpy =float (os .getenv ('RESEARCH_USDJPY_ESTIMATE','160'))
    cost =round ((inp *float (os .getenv ('RESEARCH_INPUT_USD_PER_M','1.00'))+
    out *float (os .getenv ('RESEARCH_OUTPUT_USD_PER_M','8.00')))*usd_jpy /1_000_000 ,4 )
    return evaluation ,cost ,inp ,out 


def meeting_brief (record ):
    """Transfer source evidence and uncertainty as meeting input; CEO starts meeting."""
    info =record .get ('evaluation')or {}
    entries =record .get ('evidence')or []
    cites ={x .get ('id'):x for x in entries }
    used =set (info .get ('supporting_evidence_ids')or [])
    for cmp in info .get ('competitors')or []:used .update (cmp .get ('evidence_ids')or [])
    sources =[{'id':i ,'title':cites [i ].get ('title'),'url':cites [i ].get ('url'),
    'published_date':cites [i ].get ('published_date'),'retrieved_at':cites [i ].get ('retrieved_at')}
    for i in sorted (used )if i in cites ]
    context ={'\u5019\u88dc\u540d':record .get ('candidate_title'),'\u5bfe\u8c61\u9867\u5ba2':record .get ('candidate_reader'),
    '\u9867\u5ba2\u306e\u60a9\u307f':info .get ('customer_pain'),'\u30cb\u30e5\u30fc\u30b9\u306e\u8a71\u984c\u6027':info .get ('news_attention'),
    '\u8cfc\u5165\u9700\u8981\u306e\u691c\u8a3c':info .get ('purchase_demand'),'\u7af6\u5408\u5546\u54c1':info .get ('competitors'),
    '\u5236\u4f5c\u30bf\u30b9\u30af':info .get ('production_tasks'),'\u672a\u78ba\u8a8d\u4e8b\u9805':info .get ('unknowns'),
    '\u4f4e\u8cbb\u7528\u691c\u8a3c\u6848':info .get ('low_cost_validation'),'\u8abf\u67fbAI\u306e\u63a8\u5968':info .get ('recommendation'),
    '\u88cf\u4ed8\u3051\u3068\u306a\u308b\u516c\u958bURL':sources ,'\u8abf\u67fb\u65e5\u6642':record .get ('retrieved_at'),
    '\u91cd\u5927\u306a\u5236\u7d04':'RSS\u516c\u958b\u30e1\u30bf\u30c7\u30fc\u30bf\u306e\u307f\u3002\u8ca9\u58f2\u5b9f\u7e3e\u30fb\u4fa1\u683c\u30fb\u53e3\u30b3\u30df\u306e\u672a\u78ba\u8a8d\u4e8b\u9805\u306f\u6839\u62e0\u3068\u6271\u308f\u306a\u3044\u3002'}
    return ('\u3010ZEROBOARD\u5546\u54c1\u691c\u8a3c\u7d50\u679c\u306b\u57fa\u3065\u304f\u7d4c\u55b6\u4f1a\u8b70\uff1aCEO\u6700\u7d42\u5224\u65ad\u5f85\u3061\u3011\n'
    '\u6b21\u306e\u5546\u54c1\u5019\u88dc\u306b\u3064\u3044\u3066\u3001\u6226\u7565\u30fb\u30de\u30fc\u30b1\u30fb\u8ca1\u52d9\u30fb\u30ea\u30b9\u30af\u306e4\u5f79\u54e1\u3067\u5b9f\u884c\u53ef\u5426\u3092\u691c\u8a0e\u3002'
    '\u6839\u62e0\u3068\u4eee\u8aac\u3092\u533a\u5225\u3057\u3001\u672a\u78ba\u8a8d\u306e\u8cfc\u5165\u9700\u8981\u3092\u5b9f\u7e3e\u3068\u307f\u306a\u3055\u306a\u3044\u3002'
    '\u307e\u305a\u4f4e\u8cbb\u7528\u306e\u9700\u8981\u691c\u8a3c\u3068\u5224\u65ad\u6761\u4ef6\u3092\u5177\u4f53\u7684\u306b\u63d0\u6848\u3057\u3001CEO\u306e\u627f\u8a8d\u307e\u3067\u306f\u516c\u958b\u30fb\u652f\u51fa\u3057\u306a\u3044\u3002\n'
    +json .dumps (context ,ensure_ascii =False ,default =str )[:15000 ])
