"""Text-only Responses adapter with explicit pricing and no automatic retries.

Normalized receipts fit the existing experiment loop; openai_response preserves
the actual response. cost_usd is a usage-based estimate, never an invoice.
"""
from decimal import Decimal, ROUND_FLOOR
import json
import os
import re
import shlex
from urllib import request, error

ENDPOINT = 'https://api.openai.com/v1/responses'
MODEL = 'gpt-6.1-sol'
PRICING = {
    'model':MODEL, 'as_of':'2026-10-29', 'service_tier':'default',
    'cache_ttl':'30m', 'input_per_million':'2', 'cached_input_per_million':'0.10',
    'cache_write_per_million':'2.50', 'output_per_million':'10',
    'max_input_bound':200000, 'long_context_threshold':272000,
    'source':'https://developers.openai.com/api/docs/models/gpt-6.1-sol',
    'cache_source':'https://developers.openai.com/api/docs/guides/prompt-caching',
}


def load_key(path=None):
    if path is None:
        key=os.environ.get('OPENAI_API_KEY')
        if not key:raise ValueError('Set OPENAI_API_KEY or supply --dotenv PATH')
        return key
    values=[]
    for line in path.read_text().splitlines():
        line=line.strip().removeprefix('export ')
        if not line or line.startswith('#') or '=' not in line:continue
        name,value=line.split('=',1)
        if name.strip()!='OPENAI_API_KEY':continue
        parts=shlex.split(value,comments=True)
        if len(parts)!=1 or not parts[0]:raise ValueError('Invalid OpenAI dotenv entry')
        values.append(parts[0])
    if not values or len(set(values))!=1:raise ValueError('Missing or conflicting OpenAI dotenv entries')
    return values[0]


def payload(messages, output=16384):
    if len(messages)!=2 or any(not isinstance(m.get('content'),str) for m in messages):
        raise ValueError('Expected two text-only messages')
    return {'model':MODEL,'input':[{'role':'developer','content':messages[0]['content']},
                                   {'role':'user','content':messages[1]['content']}],
        'reasoning':{'effort':'high'},'max_output_tokens':output,
        'service_tier':'default','store':False,'stream':False,'tools':[],'tool_choice':'none',
        'prompt_cache_options':{'mode':'implicit','ttl':'30m'},
        'text':{'format':{'type':'json_schema','name':'lean_proof','strict':True,
            'schema':{'type':'object','properties':{'proof':{'type':'string'}},
                      'required':['proof'],'additionalProperties':False}}}}


def plan_request(messages, remaining, prices):
    if prices!=PRICING:raise ValueError('Unrecognized direct-API price snapshot')
    body=payload(messages)
    n=len(json.dumps(body,ensure_ascii=False,separators=(',',':')).encode())+4096
    if n>=prices['max_input_bound']:raise ValueError('Input exceeds conservative token bound')
    ip=max(Decimal(prices[k]) for k in ['input_per_million','cached_input_per_million','cache_write_per_million'])/1000000
    op=Decimal(prices['output_per_million'])/1000000
    out=min(16384,int(((remaining-n*ip-Decimal('.005'))/op).to_integral_value(rounding=ROUND_FLOOR))-256)
    if out<4096:return None
    body['max_output_tokens']=out
    bound=n*ip+(out+256)*op+Decimal('.005')
    assert bound<=remaining
    return body,bound,n


def _tokens(value):
    if type(value) is not int or value<0:raise ValueError('Missing or invalid token usage')
    return value


def normalize(raw,prices):
    """Account all output including reasoning even for incomplete responses."""
    content=None;amount=None;usage={};why=None
    try:
        if prices!=PRICING:raise ValueError('Unrecognized pricing')
        if not isinstance(raw,dict):raise ValueError('Invalid response')
        if not re.fullmatch(r'gpt-6\.1-sol(?:-\d{4}-\d{2}-\d{2})?',raw.get('model','')):
            raise ValueError('Unpriced response model')
        if raw.get('service_tier')!='default':raise ValueError('Unpriced service tier')
        u=raw['usage'];details=u['input_tokens_details']
        inp=_tokens(u.get('input_tokens'));out=_tokens(u.get('output_tokens'))
        cached=_tokens(details.get('cached_tokens'));writes=_tokens(details.get('cache_write_tokens'))
        reasoning=_tokens(u['output_tokens_details'].get('reasoning_tokens'))
        if inp>=prices['max_input_bound'] or cached+writes>inp or reasoning>out:
            raise ValueError('Usage exceeds priced scope')
        if u.get('total_tokens',inp+out)!=inp+out:raise ValueError('Inconsistent total token usage')
        # No audio/image/tool usage is priced by this text-only adapter.
        for d in [details,u['output_tokens_details']]:
            if any(v for k,v in d.items() if k in {'audio_tokens','image_tokens','video_tokens'}):
                raise ValueError('Non-text usage is not priced')
        amount=str(((inp-cached-writes)*Decimal(prices['input_per_million'])
             +cached*Decimal(prices['cached_input_per_million'])
             +writes*Decimal(prices['cache_write_per_million'])
             +out*Decimal(prices['output_per_million']))/1000000)
        usage={'cost':amount,'prompt_tokens':inp,'completion_tokens':out,
               'prompt_tokens_details':{'cached_tokens':cached,'cache_write_tokens':writes},
               'completion_tokens_details':{'reasoning_tokens':reasoning}}
    except (KeyError,TypeError,ValueError) as exc:
        why=str(exc) if isinstance(exc,ValueError) else 'Missing usage fields'
    if isinstance(raw,dict) and raw.get('status')=='completed':
        texts=[];valid=True
        items=raw.get('output',[])
        if not isinstance(items,list):items=[];valid=False
        for item in items:
            if not isinstance(item,dict):valid=False;continue
            if item.get('type')=='reasoning':continue
            if item.get('type')!='message' or item.get('role')!='assistant':valid=False;continue
            parts=item.get('content',[])
            if not isinstance(parts,list):valid=False;continue
            for part in parts:
                if not isinstance(part,dict):valid=False;continue
                if part.get('type')!='output_text' or not isinstance(part.get('text'),str):valid=False
                else:texts.append(part['text'])
        if valid and texts:content=''.join(texts)
    raw=raw if isinstance(raw,dict) else {}
    return {'id':raw.get('id'),'model':raw.get('model'),'provider':'OpenAI-direct',
        'choices':[{'message':{'role':'assistant','content':content}}], 'usage':usage,
        'cost_basis':'usage_estimate' if amount is not None else 'unknown',
        'accounting_error':why,'openai_response':raw}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def query(body,prices,timeout=600):
    if prices!=PRICING:raise ValueError('Unrecognized pricing')
    inp=body.get('input',[])
    out=body.get('max_output_tokens')
    if (type(out) is not int or not 4096<=out<=16384 or len(inp)!=2
        or body!=payload([{'content':i.get('content')} for i in inp],out)):
        raise ValueError('Unexpected direct API request options')
    key=load_key()
    call=request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with request.build_opener(NoRedirect).open(call,timeout=timeout) as response:
            raw=json.loads(response.read())
    except (error.URLError,TimeoutError,OSError,ValueError) as exc:
        # A request may have been processed: preserve uncertainty and never retry.
        raw={'transport_error':type(exc).__name__,'http_status':getattr(exc,'code',None)}
    return normalize(raw,prices)
