"""CEO-triggered product evidence discovery. Public RSS search metadata only.

No private data, authenticated scraping, purchases, automated publishing, or
assertions that snippets establish real sales. Always report unknowns explicitly.
"""
import datetime as dt
import email.utils
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
MAX_CANDIDATES_PER_DAY = 2
MAX_ITEMS_PER_CANDIDATE = 12
MODEL = os.getenv('RESEARCH_MODEL', 'gpt-5-mini')


def readable(value, limit=380):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', unescape(value or ''))).strip()[:limit]


def parse_feed(xml_bytes, label, retrieved_at):
    root = ET.fromstring(xml_bytes)
    out=[]
    for node in root.findall('.//item')[:15]:
        url=(node.findtext('link') or '').strip()
        if urllib.parse.urlsplit(url).scheme not in ('http','https'):
            continue
        title=readable(node.findtext('title'),220)
        if not title:
            continue
        raw_date=node.findtext('pubDate') or ''
        published=None
        try:
            parsed=email.utils.parsedate_to_datetime(raw_date)
            if parsed.tzinfo:
                published=parsed.astimezone(JST).date().isoformat()
        except (ValueError,TypeError,OverflowError):
            pass
        out.append({'title':title,'url':url[:1800],'excerpt':readable(node.findtext('description')),
                    'source':label,'published_date':published,'retrieved_at':retrieved_at})
    return out


def search_public_metadata(title, reader, max_items=MAX_ITEMS_PER_CANDIDATE):
    """Search public RSS metadata via fixed Bing RSS endpoint; failures explicit."""
    searched_at=dt.datetime.now(JST).isoformat(timespec='seconds')
    subject=re.sub(r'\s+',' ',str(title or '')).strip()[:70]
    audience=str(reader or '').strip()[:32]
    queries=[
        (f'{subject} {audience} ææ note ä¾¡æ ¼', 'å¬éè¨äºã»ä¾¡æ ¼åè£'),
        (f'{subject} site:note.com ææ', 'noteç«¶ååè£'),
        (f'{subject} ãã³ãã¬ã¼ã ææ è²©å£² å£ã³ã', 'ç«¶åã»ã¬ãã¥ã¼åè£'),
    ]
    evidence=[]; errors=[];seen=set()
    for query,label in queries:
        url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'ZEROBOARD/1.0 research assistant (RSS metadata only)','Accept':'application/rss+xml, application/xml;q=0.9'})
            with urllib.request.urlopen(req,timeout=10) as response:
                raw=response.read(320_000)
            batch=parse_feed(raw,label,searched_at)
            for item in batch:
                identity=hashlib.sha256(item['url'].encode()).hexdigest()
                if identity not in seen and len(evidence)<max_items:
                    seen.add(identity);evidence.append(item)
        except Exception as exc:
            errors.append(f'{label}ï¼{type(exc).__name__}ï¼å¬éæ¤ç´¢ãåå¾ã§ãã¾ããï¼')
    for n,item in enumerate(evidence,1): item['id']=f'E{n:02d}'
    return evidence, errors, searched_at


EVALUATION_SCHEMA={
 'type':'object','properties':{
  'customer_pain':{'type':'string'},
  'news_attention':{'type':'string'},
  'purchase_demand':{'type':'string'},
  'competitors':{'type':'array','items':{'type':'object','properties':{
   'name':{'type':'string'},'public_price':{'type':'string'},'purchase_or_review':{'type':'string'},
   'evidence_ids':{'type':'array','items':{'type':'string'}},'certainty':{'type':'string'}
  },'required':['name','public_price','purchase_or_review','evidence_ids','certainty'],'additionalProperties':False}},
  'production_tasks':{'type':'array','items':{'type':'string'}},
  'unknowns':{'type':'array','items':{'type':'string'}},
  'low_cost_validation':{'type':'array','items':{'type':'string'}},
  'recommendation':{'type':'string'},'rationale':{'type':'string'},
  'supporting_evidence_ids':{'type':'array','items':{'type':'string'}}
 }, 'required':['customer_pain','news_attention','purchase_demand','competitors','production_tasks',
                'unknowns','low_cost_validation','recommendation','rationale','supporting_evidence_ids'],
 'additionalProperties':False}


def safe_result(data, evidence):
    valid={x['id'] for x in evidence}
    if not isinstance(data,dict): raise ValueError('AIã®è©ä¾¡å½¢å¼ãä¸æ­£ã§ã')
    cleaned=dict(data)
    if cleaned.get('recommendation') not in ('ä¼è­°ã§æ¤è¨','è¿½å èª¿æ»','è¦éã'):
        cleaned['recommendation']='è¿½å èª¿æ»'
    cleaned['supporting_evidence_ids']=[x for x in data.get('supporting_evidence_ids',[]) if x in valid]
    competitors=[]
    for row in data.get('competitors',[])[:5]:
        if not isinstance(row,dict): continue
        ids=[x for x in row.get('evidence_ids',[]) if x in valid]
        if ids: competitors.append({**row,'evidence_ids':ids})
    cleaned['competitors']=competitors
    cleaned['production_tasks']=[str(x)[:240] for x in data.get('production_tasks',[])[:8]]
    cleaned['unknowns']=[str(x)[:240] for x in data.get('unknowns',[])[:10]]
    if not evidence:
        cleaned['purchase_demand']='ç¢ºèªã§ããå¤é¨æ ¹æ ãªãï¼æ¤ç´¢çµæãªãï¼ãè³¼å¥éè¦ã¯æªç¢ºèªã'
        cleaned['competitors']=[]
        cleaned['recommendation']='è¿½å èª¿æ»'
    return cleaned


def evaluate_candidate(candidate, evidence):
    """One short OpenAI call; no claim of full article reading or proven sales."""
    from openai import OpenAI
    inputs={'candidate':{k:str(candidate.get(k) or '')[:600] for k in ('title','reader','paid_value','validation')},
            'observations':[{'id':x['id'],'title':x['title'],'excerpt':x['excerpt'],
                             'published_date':x['published_date'],'retrieved_at':x['retrieved_at'],
                             'source':x['source']} for x in evidence]}
    instructions=('ããªãã¯ç¬ç«ããååéè¦ã®æ¤è¨¼æå½ãæ¤ç´¢çµæã¯å¬éRSSè¦åºãã»æç²ã ãã§è¨äºæ¬ææªèª­ã'
                  'ãã¥ã¼ã¹ã®è©±é¡æ§ã¨ãå®éã®è³¼è²·éè¦ãæç¢ºã«åé¢ããã'
                  'ç«¶ååè£ã¯æ¤ç´¢çµæã«å¯¾å¿ããIDãããå®å¨åè£ã ãã'
                  'ä¾¡æ ¼ã¯æè¨ããã¦ããã¨ãã ãè¡¨è¨ãããªããã°ãæªç¢ºèªãã'
                  'å®éã®è³¼å¥ã»è²©å£²ä»¶æ°ã»ã¬ãã¥ã¼ä»¶æ°ã¯è£ä»ãããªããã°å¿ããæªç¢ºèªãã'
                  'ãè³¼å¥éè¦ãã®æ ¹æ ã¯ä¾¡æ ¼æå ±ã»åãªãè¨äºè¦åºãã¨åºå¥ããã'
                  'é¡§å®¢èª²é¡ãç«¶åãå¬éä¾¡æ ¼ãç¢ºèªå¯è½ãªè²©å£²ã»ã¬ãã¥ã¼è¨¼æ ãå¶ä½ä½æ¥­ãæªç¢ºèªäºé ã'
                  'ä½è²»ç¨ã®æ¤è¨¼æ¹æ³ãæ¥æ¬èªã§ç­ãæ¸ããè¨¼æ ããªããã°ä¸è¶³ãæç¤ºããæ ¹æ ãåµä½ããªãã'
                  'å·ä½çãªURLã¯å¥åã«è¼ããªãã®ã§IDãåºå¸ã¨ããã'
                  'recommendationã¯ãä¼è­°ã§æ¤è¨ããè¿½å èª¿æ»ããè¦éããã®ããããã'
                  'ä¼è­°ã§æ¤è¨ã¯æ¡ç¨ã»è²©å£²è¨±å¯ã§ã¯ãªããJSONä»¥å¤ã¯è¿ããªãã')
    response=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=50,max_retries=1).responses.create(
        model=MODEL, reasoning={'effort':'low'}, instructions=instructions,
        input=json.dumps(inputs,ensure_ascii=False)[:12000],max_output_tokens=3500,
        text={'format':{'type':'json_schema','name':'product_evidence_check',
                        'schema':EVALUATION_SCHEMA,'strict':True}})
    if response.status!='completed':
        raise ValueError('AIåæãæªå®äºã®ãããçµæãä¿å­ãã¾ãã')
    evaluation=safe_result(json.loads(response.output_text),evidence)
    usage=response.usage
    inp=int(getattr(usage,'input_tokens',0) or 0)
    out=int(getattr(usage,'output_tokens',0) or 0)
    # Same user-configurable estimate as the daily research task.
    usd_jpy=float(os.getenv('RESEARCH_USDJPY_ESTIMATE','160'))
    cost=round((inp*float(os.getenv('RESEARCH_INPUT_USD_PER_M','1.00'))+
                out*float(os.getenv('RESEARCH_OUTPUT_USD_PER_M','8.00')))*usd_jpy/1_000_000,4)
    return evaluation,cost,inp,out


def meeting_brief(record):
    """Transfer source evidence and uncertainty as meeting input; CEO starts meeting."""
    info=record.get('evaluation') or {}
    entries=record.get('evidence') or []
    cites={x.get('id'):x for x in entries}
    used=set(info.get('supporting_evidence_ids') or [])
    for cmp in info.get('competitors') or []:used.update(cmp.get('evidence_ids') or [])
    sources=[{'id':i,'title':cites[i].get('title'),'url':cites[i].get('url'),
              'published_date':cites[i].get('published_date'),'retrieved_at':cites[i].get('retrieved_at')}
             for i in sorted(used) if i in cites]
    context={'åè£å':record.get('candidate_title'),'å¯¾è±¡é¡§å®¢':record.get('candidate_reader'),
             'é¡§å®¢ã®æ©ã¿':info.get('customer_pain'),'ãã¥ã¼ã¹ã®è©±é¡æ§':info.get('news_attention'),
             'è³¼å¥éè¦ã®æ¤è¨¼':info.get('purchase_demand'),'ç«¶ååå':info.get('competitors'),
             'å¶ä½ã¿ã¹ã¯':info.get('production_tasks'),'æªç¢ºèªäºé ':info.get('unknowns'),
             'ä½è²»ç¨æ¤è¨¼æ¡':info.get('low_cost_validation'),'èª¿æ»AIã®æ¨å¥¨':info.get('recommendation'),
             'è£ä»ãã¨ãªãå¬éURL':sources,'èª¿æ»æ¥æ':record.get('retrieved_at'),
             'éå¤§ãªå¶ç´':'RSSå¬éã¡ã¿ãã¼ã¿ã®ã¿ãè²©å£²å®ç¸¾ã»ä¾¡æ ¼ã»å£ã³ãã®æªç¢ºèªäºé ã¯æ ¹æ ã¨æ±ããªãã'}
    return ('ãZEROBOARDååæ¤è¨¼çµæã«åºã¥ãçµå¶ä¼è­°ï¼CEOæçµå¤æ­å¾ã¡ã\n'
            'æ¬¡ã®åååè£ã«ã¤ãã¦ãæ¦ç¥ã»ãã¼ã±ã»è²¡åã»ãªã¹ã¯ã®4å½¹å¡ã§å®è¡å¯å¦ãæ¤è¨ã'
            'æ ¹æ ã¨ä»®èª¬ãåºå¥ããæªç¢ºèªã®è³¼å¥éè¦ãå®ç¸¾ã¨ã¿ãªããªãã'
            'ã¾ãä½è²»ç¨ã®éè¦æ¤è¨¼ã¨å¤æ­æ¡ä»¶ãå·ä½çã«ææ¡ããCEOã®æ¿èªã¾ã§ã¯å¬éã»æ¯åºããªãã\n'
            +json.dumps(context,ensure_ascii=False,default=str)[:15000])
