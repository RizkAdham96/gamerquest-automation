import json
from social.ai_client import call_grok
from social.config import SOCIAL_FORMATS
from social.history import get_recent_history
MAX_CONTENT_ITEMS=10; MAX_EXCERPT_CHARS=500; MAX_PROMPT_CHARS=16000; RECENT_HISTORY_ITEMS=8; CONCEPT_COUNT=3

def _clean_text(value,limit=None):
    text="" if value is None else str(value).strip(); return text[:limit] if limit is not None else text

def _compact_history_item(item):
    if not isinstance(item,dict): return {}
    return {"topic":_clean_text(item.get("topic"),120),"angle":_clean_text(item.get("angle"),160),"format":_clean_text(item.get("format"),60),"hook":_clean_text(item.get("hook"),180),"cta":_clean_text(item.get("cta"),180)}
def _content_sort_key(item): return _clean_text(item.get("created_at") or item.get("published_at") or item.get("date")) if isinstance(item,dict) else ""
def prepare_content_for_ai(content):
    valid=[x for x in content if isinstance(x,dict)]; news=sorted([x for x in valid if x.get("source_type")!="deal"],key=_content_sort_key,reverse=True); deals=sorted([x for x in valid if x.get("source_type")=="deal"],key=_content_sort_key,reverse=True); selected=news[:8]+deals[:2]
    if len(selected)<MAX_CONTENT_ITEMS:
        chosen={id(x) for x in selected}; remaining=sorted([x for x in valid if id(x) not in chosen],key=_content_sort_key,reverse=True); selected.extend(remaining[:MAX_CONTENT_ITEMS-len(selected)])
    out=[]
    for item in selected[:MAX_CONTENT_ITEMS]:
        tags=item.get("tags",[]) if isinstance(item.get("tags",[]),list) else []
        out.append({"title":_clean_text(item.get("title"),220),"excerpt":_clean_text(item.get("excerpt") or item.get("description"),MAX_EXCERPT_CHARS),"slug":_clean_text(item.get("slug"),180),"category":_clean_text(item.get("category"),80),"source_type":_clean_text(item.get("source_type"),40),"created_at":_clean_text(item.get("created_at"),80),"tags":[_clean_text(t,60) for t in tags[:5]]})
    return out
def _safe_prompt(prompt):
    prompt=prompt.strip()
    if len(prompt)>MAX_PROMPT_CHARS: raise RuntimeError(f"Social AI prompt exceeds safe size: {len(prompt)} characters.")
    return prompt
def parse_json_response(raw_response):
    text=raw_response.strip()
    if text.startswith("```"): text=text.replace("```json","",1).replace("```","").strip()
    try: return json.loads(text)
    except json.JSONDecodeError as error: raise RuntimeError(f"AI returned invalid JSON: {error}") from error
def build_prompt(content):
    history=[_compact_history_item(x) for x in get_recent_history(RECENT_HISTORY_ITEMS) if isinstance(x,dict)]; sample=prepare_content_for_ai(content)
    return _safe_prompt(f'''Create exactly {CONCEPT_COUNT} DIFFERENT compact GamerQuest.fr carousel CONCEPTS designed to drive website visits. Use only supplied facts; never invent facts. Avoid recent topics/hooks/angles/formats/CTAs. Do NOT write slides/captions/hashtags/visual prompts yet. Allowed formats: {json.dumps(SOCIAL_FORMATS,ensure_ascii=False)} Recent history: {json.dumps(history,ensure_ascii=False)} Content: {json.dumps(sample,ensure_ascii=False)} Return ONLY JSON array objects with topic, angle, format, hook and integer 0-10 scores freshness, click_potential, curiosity, shareability, originality, gamerquest_relevance.''')
def build_expansion_prompt(idea,content):
    sample=prepare_content_for_ai(content); base={k:idea.get(k) for k in ("topic","angle","format","hook")}
    return _safe_prompt(f'''Create final Instagram/Facebook carousel for GamerQuest.fr. Concept: {json.dumps(base,ensure_ascii=False)} Sources: {json.dumps(sample,ensure_ascii=False)} STRICT: every factual statement must be explicitly supported. Never infer platforms, multiplayer, dates, prices, future pricing, features, compatibility or availability. Exactly 5 concise slides, caption, CTA, 3-6 hashtags, visual prompt per slide. Return ONLY JSON: {{"slides":[{{"title":"...","body":"...","visual_prompt":"..."}}],"caption":"...","cta":"...","hashtags":["#GamerQuest"]}}''')
def generate_ideas(content):
    if not content:return []
    data=parse_json_response(call_grok(build_prompt(content)))
    if not isinstance(data,list):raise RuntimeError("AI response must be a JSON array.")
    return data[:CONCEPT_COUNT]
def expand_idea(idea,content):
    if not isinstance(idea,dict):return None
    data=parse_json_response(call_grok(build_expansion_prompt(idea,content)))
    if not isinstance(data,dict):raise RuntimeError("AI carousel response must be a JSON object.")
    result=idea.copy()
    for key in ("slides","caption","cta","hashtags"):result[key]=data.get(key,[] if key in ("slides","hashtags") else "")
    return result
def verify_carousel(idea,content):
    sample=prepare_content_for_ai(content); package={k:idea.get(k) for k in ("topic","hook","slides","caption","cta")}
    prompt=_safe_prompt(f'''Fact-check PACKAGE against ONLY SOURCE. SOURCE: {json.dumps(sample,ensure_ascii=False)} PACKAGE: {json.dumps(package,ensure_ascii=False)} Check every factual claim, especially dates/platforms/multiplayer/prices/future pricing/availability/features. Explicit support required. Return ONLY JSON {{"valid":true,"unsupported_claims":[],"reason":""}}. Any unsupported claim means valid false.''')
    data=parse_json_response(call_grok(prompt))
    if not isinstance(data,dict) or not isinstance(data.get("valid"),bool):raise RuntimeError("AI fact-check response is invalid.")
    claims=data.get("unsupported_claims",[]); claims=claims if isinstance(claims,list) else []
    return {"valid":data["valid"],"unsupported_claims":claims,"reason":_clean_text(data.get("reason"),500)}
def repair_carousel(idea,content,unsupported_claims):
    sample=prepare_content_for_ai(content); package={k:idea.get(k) for k in ("slides","caption","cta","hashtags")}
    prompt=_safe_prompt(f'''Repair this GamerQuest carousel using ONLY SOURCE facts. SOURCE: {json.dumps(sample,ensure_ascii=False)} CURRENT PACKAGE: {json.dumps(package,ensure_ascii=False)} UNSUPPORTED CLAIMS: {json.dumps(unsupported_claims,ensure_ascii=False)} Remove or rewrite ONLY what is needed to eliminate unsupported claims. Do not add new facts. Preserve exactly 5 slides when current package has 5. Return ONLY JSON with slides (title, body, visual_prompt), caption, cta, hashtags.''')
    data=parse_json_response(call_grok(prompt))
    if not isinstance(data,dict):raise RuntimeError("AI repair response must be a JSON object.")
    result=idea.copy()
    for key in ("slides","caption","cta","hashtags"):result[key]=data.get(key,package.get(key,[] if key in ("slides","hashtags") else ""))
    return result
