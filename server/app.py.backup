from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AzureOpenAI
from starlette.websockets import WebSocketDisconnect
import os, json, re, logging, base64
from datetime import datetime
import asyncio
from urllib.parse import quote

load_dotenv()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

# 이미지/로그 디렉토리
os.makedirs("debug_images", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ============================
# Goal-scoped logger
# ============================
class GoalLogger:
    def __init__(self):
        self.current_goal = None
        self.log_file_path = None
        self.session_start_time = None

    def start_new_goal(self, goal: str):
        self.current_goal = goal
        self.session_start_time = datetime.now()
        timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        safe_goal = re.sub(r'[^\w\s-]', '', goal)[:20]
        safe_goal = re.sub(r'[-\s]+', '_', safe_goal)
        filename = f"{timestamp}-{safe_goal}.log"
        self.log_file_path = os.path.join("logs", filename)
        self.log("SERVER", "GOAL_START", f"새로운 목표 시작: {goal}")
        logger.info(f"📝 목표별 로그 시작: {self.log_file_path}")

    def log(self, source: str, event_type: str, message: str, extra_data: dict | None = None):
        if not self.log_file_path:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = {
            "timestamp": timestamp,
            "source": source,
            "event_type": event_type,
            "message": message,
            "extra_data": extra_data or {},
        }
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"로그 저장 실패: {e}")

    def log_server_event(self, event_type: str, message: str, extra_data: dict | None = None):
        self.log("SERVER", event_type, message, extra_data)

    def log_client_event(self, event_type: str, message: str, extra_data: dict | None = None):
        self.log("CLIENT", event_type, message, extra_data)

# 전역 로거
goal_logger = GoalLogger()

# ============================
# Known site mapping (private/managed only)
# ============================
SITE_MAPPING = {
    "국가교통정보센터": "https://www.its.go.kr",
    "정부24": "https://www.gov.kr",
    "국세청": "https://www.nts.go.kr",
    "건강보험공단": "https://www.nhis.or.kr",
    "한국은행": "https://www.bok.or.kr",
    # 주요 서비스 (특별 케이스)
    "네이버": "https://naver.com",
    "다음": "https://daum.net",
}

def find_site_url(query: str) -> str | None:
    q = (query or '').lower().strip()
    for name, url in SITE_MAPPING.items():
        if name.lower() in q or q in name.lower():
            logger.info(f"사이트 매핑 발견: {query} -> {url}")
            return url
    logger.info(f"매핑에 없는 사이트: {query}")
    return None

# ============================
# FastAPI app
# ============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# ============================
# 요구사항 → 웹페이지 가이드 변환
# ============================
def translate_requirement_to_web_guide(user_message: str, page_type: str = None) -> str:
    """일반적인 요구사항을 웹페이지 구체적 가이드로 변환"""
    logger.info(f"🔄 요구사항 변환 시작: {user_message}")
    
    # 일반적인 패턴들
    patterns = {
        "로그인": {
            "guide": "로그인 폼의 아이디/비밀번호 입력 후 로그인 버튼 클릭",
            "selectors": ["input[type='email']", "input[type='password']", "button[type='submit']"]
        },
        "검색": {
            "guide": "검색창에 키워드 입력 후 검색 버튼 클릭 또는 엔터",
            "selectors": ["input[type='search']", "input[placeholder*='검색']", "button[type='submit']"]
        }
    }
    
    # 키워드 매칭
    for keyword, info in patterns.items():
        if keyword in user_message:
            logger.info(f"✅ 패턴 매칭: {keyword} → {info['guide']}")
            return info['guide']
    
    logger.info("❓ 특정 패턴 없음 - 원본 요구사항 유지")
    return user_message

# ============================
# 페이지 이해도 분석
# ============================
def analyze_page_understanding(dom_summary: list) -> dict:
    """DOM 분석은 LLM에게 위임 - 기본 정보만 반환"""
    logger.info("📊 페이지 기본 정보만 추출 (분석은 LLM이 담당)")
    
    return {
        "dom_elements": len(dom_summary),
        "analysis_method": "llm_delegation"
    }

# ============================
# 목표 진행도 평가
# ============================
def evaluate_goal_progress(goal: str, current_step: int, total_steps: int, page_analysis: dict, last_action: dict = None) -> dict:
    """기본적인 진행도만 계산 - 상세 평가는 LLM이 담당"""
    logger.info(f"🎯 기본 진행도 계산: {goal}")
    
    progress_percentage = (current_step / total_steps * 100) if total_steps > 0 else 0
    
    return {
        "progress_percentage": progress_percentage,
        "current_step": current_step,
        "total_steps": total_steps,
        "evaluation_method": "llm_based"
    }

# Simple intent gate: need DOM?
# ============================
def analyze_prompt_needs_dom(user_message: str) -> bool:
    logger.info(f"🔍 프롬프트 분석 시작: {user_message}")
    nav = ["이동", "가기", "들어가", "접속", "열기", "홈페이지", "사이트", "웹사이트"]
    domk = [
        "클릭", "입력", "검색", "로그인", "조회", "확인", "읽기", "보기", "선택", "다운로드",
        "버튼", "링크", "메뉴", "폼", "필드", "텍스트", "내용", "정보", "데이터",
    ]
    s = user_message.lower()
    if any(k in s for k in domk):
        logger.info("✅ DOM 필요 키워드 발견")
        return True
    if any(k in s for k in nav):
        logger.info("❌ DOM 불필요 - 단순 이동")
        return False
    logger.info("⚠️ 애매함 - DOM 필요로 분류")
    return True

# ============================
# LLM helpers
# ============================
async def call_llm(prompt: str):
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        res = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.1,
        )
        return res.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM 호출 실패: {e}")
        return None

async def call_llm_with_image(prompt: str, image_data: str):
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        res = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                ],
            }],
            max_tokens=500,
            temperature=0.1,
        )
        return res.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision API 호출 실패: {e}")
        return None

# ============================
# Prompt builders (short & crisp)
# ============================

def build_planning_prompt_with_image(goal: str, dom_summary: list, context: dict | None = None) -> str:
    ctx = context or {}
    return f"""
You are a browser automation planner with multi-phase DOM analysis capabilities.

🧠 **PHASE 1: PAGE STRUCTURE ANALYSIS**
First, analyze the overall page layout and identify:
- Main content areas (header, nav, main, sidebar, footer)
- Page type (email list, search results, article, form, etc.)
- Key sections relevant to the goal

🎯 **PHASE 2: GOAL-FOCUSED ANALYSIS**  
Then focus on areas related to the goal:
- Find sections that contain target elements
- Identify interaction patterns (lists, forms, buttons)
- Locate navigation paths to reach the goal

⚡ **PHASE 3: ACTION PLANNING**
Finally, create specific action steps:
- Use stable, semantic selectors
- Prioritize visually prominent elements
- Plan error-resistant automation sequence

Goal: "{goal}"
Current step: {ctx.get('step', 0)}

DOM Elements (analyze in phases):
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Perform the 3-phase analysis and create a plan. Return ONLY the JSON array:

[{{"step": <int>, "action": "goto|click|fill|hover|waitUntil|google_search|end", 
  "selector": "<css>", "text":"<opt>", "value":"<opt>", "url":"<opt>", "reason":"<phase_based_analysis>"}}]
"""

def build_execution_prompt_with_image(goal: str, plan: list, current_step: int, dom_summary: list, context: dict | None = None) -> str:
    ctx = context or {}
    
    # 현재 단계에 따른 적절한 액션 가이드
    if current_step == 0 or not plan:
        action_guide = f"""
🚀 **FIRST STEP ANALYSIS**:
The goal is: "{goal}"
Since this is the first step, analyze what needs to be done:
- If we need to go to Naver Mail, use: {{"action":"goto","url":"https://mail.naver.com"}}
- If we're already on the right page, proceed with the next logical action
- Focus on getting closer to the goal
"""
    else:
        current_plan_step = plan[current_step-1] if current_step <= len(plan) else None
        action_guide = f"""
🎯 **PLANNED STEP EXECUTION**:
Current Step: {current_step}/{len(plan)}
Planned Action: {json.dumps(current_plan_step, ensure_ascii=False) if current_plan_step else 'Plan step not found'}
Execute this planned action or adapt if the page has changed.
"""
    
    return f"""
Execute the next action toward the goal using DOM analysis.

{action_guide}

🔍 **DOM ANALYSIS**:
1. Understand current page state from the DOM
2. Identify the best element for the required action  
3. Create a reliable action that moves toward the goal

Goal: "{goal}"
Current Step: {current_step}

Current DOM State:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Analyze the situation and return ONLY the JSON action:

{{"action":"click|fill|goto|google_search|hover|waitUntil|end", "selector":"<css>", 
  "text":"<opt>", "value":"<opt>", "url":"<opt>", "timeout":1000}}
"""

def build_evaluation_prompt_with_image(goal: str, dom_summary: list, context: dict | None = None) -> str:
    ctx = context or {}
    return f"""
Evaluate progress using systematic DOM analysis.

📊 **STEP 1: PAGE STATE ASSESSMENT**
First, understand what happened:
- What page are we currently on?
- What content is now visible?
- Did the last action succeed or fail?

🎯 **STEP 2: GOAL ALIGNMENT CHECK**
Then check progress toward the goal:
- Does current DOM content match the user's goal?
- Are we closer to achieving the objective?
- What evidence supports completion or progress?

🚦 **STEP 3: NEXT ACTION DECISION**
Finally, decide what should happen next:
- COMPLETED: Goal is fully achieved (provide DOM evidence)
- CONTINUE: Making progress, continue with current approach
- REPLAN: Current approach isn't working, need new strategy

Goal: "{goal}"
Step: {ctx.get('step', 0)}
Last action: {json.dumps(ctx.get('lastAction'), ensure_ascii=False) if ctx.get('lastAction') else 'None'}

Current DOM State:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Perform the 3-step evaluation. Return ONLY ONE JSON object:

For COMPLETED: {{"status":"completed","reason":"<step_by_step_analysis>","evidence":"<specific_dom_evidence>"}}
For REPLAN: {{"status":"replan","reason":"<why_approach_failed>","new_plan_needed":true}}
For CONTINUE: {{"status":"continue","action":"click|fill|goto|hover|waitUntil","selector":"<css>","value":"<opt>","url":"<opt>","reason":"<next_step_analysis>"}}
"""

# Legacy single-step builder kept for fallback

def build_prompt_with_image(goal: str, dom_summary: list, step: int, context: dict | None = None) -> str:
    ctx = context or {}
    return f"""
You are a browser control agent (MCP) with visual understanding.
Return ONLY one JSON action. Prefer direct visible elements. Return {{"action":"end"}} if done.

Goal: "{goal}"
Step: {step}
DOM:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Schema:
{{"action":"click|fill|goto|google_search|hover|waitUntil|end","selector":"<css>","text":"<opt>",
  "value":"<opt>","url":"<for goto/google_search>","query":"<for google_search>","condition":"<opt>","timeout":1000}}
"""

# ============================
# Small utilities
# ============================

def compress_dom(dom: list) -> list:
    """객체 필터링 없이 속성만 정리한 DOM 요약"""
    
    result = []
    for el in dom:
        if not el.get("selector"):
            continue
            
        # 기본 정보만 포함
        entry = {
            "tag": el.get("tag", ""),
            "selector": el.get("selector", "")
        }
        
        # 주요 속성만 포함 (값이 있을 때만)
        for k in ("id", "name", "type", "class", "href", "value", "text"):
            if el.get(k):
                entry[k] = el[k]
        
        result.append(entry)
    
    # 간단한 통계 로깅
    logger.info(f"📊 DOM 압축 통계:")
    logger.info(f"   - 원본 요소: {len(dom)}개")
    logger.info(f"   - 최종 결과: {len(result)}개 요소 (필터링 없이 속성만 정리)")
    
    return result  # 모든 요소 포함


def save_debug_image(image_data: str, step: int, goal: str | None = None) -> str | None:
    try:
        logger.info(f"💾 이미지 저장 시작 (스텝: {step}, 목표: {goal})")
        original_data = image_data
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        goal_safe = ""
        if goal:
            goal_safe = "_" + re.sub(r"[^\w-]", "_", "_".join(goal.split()[:3]))[:20]
        filename = f"debug_images/step_{step}{goal_safe}_{ts}.png"
        with open(filename, 'wb') as f:
            f.write(image_bytes)
        logger.info(f"✅ 이미지 저장: {filename} ({len(image_bytes)} bytes)")
        return filename
    except Exception as e:
        logger.error(f"❌ 이미지 저장 실패: {e}")
        return None


def clean_action(action: dict) -> dict:
    a = dict(action)
    if a.get("action") in ["click", "hover"]:
        a.pop("value", None)
    if a.get("action") != "extract":
        a.pop("extract", None)
        a.pop("attribute", None)
    return a

# 더 견고한 JSON 추출: 중괄호 균형 파서

def extract_top_level_json(s: str) -> str | None:
    s = s.strip()
    # 배열 우선
    if s and s[0] == '[':
        bal = 0
        for i, ch in enumerate(s):
            if ch == '[':
                bal += 1
            elif ch == ']':
                bal -= 1
                if bal == 0:
                    return s[:i+1]
        return None
    # 객체
    start = s.find('{')
    if start == -1:
        return None
    bal = 0
    for i in range(start, len(s)):
        if s[i] == '{':
            bal += 1
        elif s[i] == '}':
            bal -= 1
            if bal == 0:
                return s[start:i+1]
    return None

# 간단해진 자연어 → 명령문 정제기

async def refine_prompt_with_llm(user_message: str) -> str:
    url = find_site_url(user_message)
    if url:
        return f"{url}로 이동"
    site_keywords = ["사이트","홈페이지","웹사이트","페이지","들어가","접속","이동"]
    if any(k in user_message for k in site_keywords):
        return f"Google에서 '{user_message}' 검색 후 원하는 결과 클릭"

    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-15-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )
    prompt = f"""
Convert the user's intent into ONE direct browser command (Korean).
Prefer concise imperative. If it's pure navigation, output only '<URL>로 이동'.

입력: "{user_message}"

예시:
- "유튜브 들어가서 구독함 열어줘" → "https://youtube.com로 이동 후 '구독' 클릭"
- "검색창에 AI 입력하고 검색" → "검색창에 'AI' 입력 후 검색 버튼 클릭"
- "로그인 페이지로 가" → "로그인 링크 클릭"
명령문:
"""
    res = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        messages=[{"role":"user","content":prompt}],
        max_tokens=80,
        temperature=0.1,
    )
    return res.choices[0].message.content.strip().replace("\n"," ")

# ============================
# WebSocket endpoint
# ============================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket 연결 수락됨 (Stateless 서버)")
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                if payload.get('type') != 'client_log':
                    logger.info(f"📨 메시지 수신: {len(raw)} chars | type={payload.get('type')}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 파싱 실패: {e}")
                continue

            # ---------- init ----------
            if payload.get("type") == "init":
                try:
                    user_goal = payload["message"]
                    logger.info(f"🆕 새 목표: {user_goal}")
                    goal_logger.start_new_goal(user_goal)

                    goal_logger.log_server_event("PROMPT_ANALYSIS", f"프롬프트 분석 시작: {user_goal}")
                    needs_dom = analyze_prompt_needs_dom(user_goal)
                    goal_logger.log_server_event("DOM_DECISION", f"DOM 필요 여부: {needs_dom}")

                    if needs_dom:
                        goal_logger.log_server_event("DOM_REQUEST", "DOM이 필요한 작업으로 판단 - DOM 요청")
                        await websocket.send_text(json.dumps({
                            "type": "request_dom",
                            "message": "현재 페이지 정보가 필요합니다.",
                        }))
                    else:
                        goal_logger.log_server_event("DIRECT_PROCESSING", "프롬프트만으로 처리")
                        refined_goal = await refine_prompt_with_llm(user_goal)
                        goal_logger.log_server_event("GOAL_REFINED", f"정제된 목표: {refined_goal}")
                        if "로 이동" in refined_goal:
                            url = refined_goal.split("로 이동")[0]
                            action = {"action": "goto", "url": url}
                            goal_logger.log_server_event("ACTION_GENERATED", f"직접 액션: {action}")
                            await websocket.send_text(json.dumps({
                                "type": "action", "step": 1, "action": action,
                            }))
                        else:
                            goal_logger.log_server_event("RECLASSIFY_DOM", "DOM 필요로 재분류")
                            await websocket.send_text(json.dumps({
                                "type": "request_dom",
                                "message": "현재 페이지 정보가 필요합니다.",
                            }))
                    logger.info("✅ init 처리 완료")
                except Exception as e:
                    logger.error(f"❌ init 처리 중 오류: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error", "detail": f"초기화 중 오류: {str(e)}",
                }))
                continue

            # ---------- client_log ----------
            if payload.get("type") == "client_log":
                goal_logger.log_client_event(payload.get("event_type", "UNKNOWN"), payload.get("message", ""), payload.get("extra_data", {}))
                continue

            # ---------- dom_with_image / evaluation ----------
            if payload.get("type") in ["dom_with_image", "dom_with_image_evaluation"]:
                is_eval = payload.get("type") == "dom_with_image_evaluation" or payload.get("evaluationMode", False)
                logger.info("📊 DOM+이미지 처리 시작" + (" (평가 모드)" if is_eval else ""))

                context = payload.get("context", {})
                goal = context.get("goal", payload.get("message", ""))
                step = context.get("step", 0)
                plan = context.get("plan", [])
                
                if not goal:
                    await websocket.send_text(json.dumps({"type": "error", "detail": "목표가 설정되지 않았습니다."}))
                    continue
                
                try:
                    dom_summary = compress_dom(payload.get("dom", []))
                    logger.info(f"📊 DOM 압축 완료: {len(dom_summary)} 요소")
                    
                    # === 새로운 분석 단계들 ===
                    
                    # 1. 요구사항 → 웹 가이드 변환
                    web_guide = translate_requirement_to_web_guide(goal)
                    logger.info(f"🔄 요구사항 변환: {goal} → {web_guide}")
                    
                    # 2. 페이지 이해도 분석 (LLM 위임 방식)
                    page_analysis = analyze_page_understanding(dom_summary)
                    logger.info(f"📊 페이지 기본 정보: {page_analysis['dom_elements']}개 요소, {page_analysis['analysis_method']} 방식")
                    
                    # 3. 목표 진행도 평가 (기본 계산만)
                    last_action = context.get("lastAction") if context else None
                    total_steps = len(plan) if plan else 1
                    progress_eval = evaluate_goal_progress(goal, step, total_steps, page_analysis, last_action)
                    logger.info(f"🎯 진행도: {progress_eval['progress_percentage']:.1f}% 완료 ({progress_eval['current_step']}/{progress_eval['total_steps']} 단계)")
                    
                    # 분석 결과를 클라이언트에 전송
                    analysis_result = {
                        "type": "page_analysis",
                        "web_guide": web_guide,
                        "page_understanding": page_analysis,
                        "progress_evaluation": progress_eval,
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send_text(json.dumps(analysis_result, ensure_ascii=False))
                    logger.info("📊 페이지 분석 결과 전송 완료")
                except Exception as e:
                    logger.error(f"❌ DOM 압축 실패: {e}")
                    continue
                
                image_data = payload.get("image")
                if image_data:
                    save_debug_image(image_data, step, goal)
                
                # Plan (if empty & step==0)
                if not plan and step == 0:
                    goal_logger.log_server_event("PLANNING_START", f"이미지 기반 계획 수립 (DOM {len(dom_summary)})")
                    prompt = build_planning_prompt_with_image(goal, dom_summary, context)
                    plan_resp = await (call_llm_with_image(prompt, image_data) if image_data else call_llm(prompt))
                    if plan_resp:
                        jtxt = extract_top_level_json(plan_resp)
                        if jtxt:
                            try:
                                parsed = json.loads(jtxt)
                                goal_logger.log_server_event("PLAN_GENERATED", f"{len(parsed)} 단계 계획")
                                await websocket.send_text(json.dumps({"type": "plan", "plan": parsed}))
                                continue
                            except json.JSONDecodeError as e:
                                goal_logger.log_server_event("ERROR", f"Planning JSON 파싱 실패: {e}")

                # Execute or Evaluate
                if is_eval:
                    prompt = build_evaluation_prompt_with_image(goal, dom_summary, context)
                    response = await (call_llm_with_image(prompt, image_data) if image_data else call_llm(prompt))
                else:
                    if image_data:
                        prompt = build_execution_prompt_with_image(goal, plan, step, dom_summary, context) if plan else build_prompt_with_image(goal, dom_summary, step, context)
                        response = await call_llm_with_image(prompt, image_data)
                    else:
                        prompt = f"Goal: {goal}\nStep: {step}\nDOM: {json.dumps(dom_summary, ensure_ascii=False, indent=2)}\nReturn next action as JSON."
                        response = await call_llm(prompt)

                if not response:
                    await websocket.send_text(json.dumps({"type": "error", "detail": "LLM 응답 없음"}))
                    continue

                logger.info(f"🧠 LLM 전체 응답: {response}")
                jtxt = extract_top_level_json(response)
                logger.info(f"🔍 추출된 JSON: {jtxt}")
                if not jtxt:
                    logger.error(f"❌ JSON 추출 실패 - 원본: {response}")
                    await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {response}"}))
                    continue
                try:
                    result = json.loads(jtxt)
                    if not is_eval:
                        # google_search → goto 변환
                        if result.get("action") == "google_search" and result.get("query") and not result.get("url"):
                            result["url"] = f"https://www.google.com/search?q={quote(result['query'])}"
                            result["action"] = "goto"
                        action = clean_action(result)
                        if action.get("action") == "end":
                            await websocket.send_text(json.dumps({"type": "end"}))
                        else:
                            await websocket.send_text(json.dumps({"type": "action", "step": step, "action": action}))
                    else:
                        status = result.get("status")
                        if status == "completed":
                            await websocket.send_text(json.dumps({
                                "type": "completed",
                                "reason": result.get("reason", "목표가 달성되었습니다."),
                                "evidence": result.get("evidence", ""),
                            }))
                        elif status == "replan":
                            await websocket.send_text(json.dumps({
                                "type": "replan",
                                "reason": result.get("reason", "계획을 다시 수립해야 합니다."),
                                "new_plan_needed": True,
                            }))
                        elif status == "continue":
                            action = clean_action(result)
                            await websocket.send_text(json.dumps({"type": "action", "step": step, "action": action}))
                except json.JSONDecodeError as e:
                    await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 오류: {e}"}))

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket 연결 해제됨")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "detail": str(e)}))
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
