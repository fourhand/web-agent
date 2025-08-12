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
    """DOM 분석은 LLM에게 위임 - 기본 정보 + 로그인 감지"""
    logger.info("📊 페이지 기본 정보 추출 (분석은 LLM이 담당)")
    
    # 로그인 페이지 감지
    is_login_page = detect_login_page(dom_summary)
    
    return {
        "dom_elements": len(dom_summary),
        "analysis_method": "llm_delegation",
        "is_login_page": is_login_page
    }

def detect_login_page(dom_summary: list) -> bool:
    """로그인 페이지 여부 감지 (로그인 성공 상황 고려)"""
    
    # 먼저 로그인 성공 신호 확인
    success_indicators = ["메일함", "inbox", "받은편지함", "logout", "로그아웃", "내정보", "프로필"]
    success_signals = 0
    
    for element in dom_summary:
        text = (element.get("text", "") or "").lower()
        for indicator in success_indicators:
            if indicator in text:
                success_signals += 1
                break
    
    # 로그인 성공 신호가 충분하면 로그인 페이지 아님
    if success_signals >= 1:
        logger.info(f"✅ 로그인 성공 감지: 성공신호 {success_signals}개 발견")
        return False
    
    # 기존 로그인 페이지 감지 로직
    login_indicators = {
        "text_keywords": ["로그인", "login", "sign in", "아이디", "비밀번호", "password", "이메일"],
        "input_types": ["password", "email"],
        "login_classes": ["login", "signin", "auth", "credential"]
    }
    
    text_matches = 0
    password_fields = 0
    login_elements = 0
    
    for element in dom_summary:
        # 텍스트 키워드 체크
        text = (element.get("text", "") or "").lower()
        for keyword in login_indicators["text_keywords"]:
            if keyword in text:
                text_matches += 1
                break
        
        # 비밀번호 필드 체크
        if element.get("type") == "password":
            password_fields += 1
        
        # 로그인 관련 클래스/ID 체크
        element_class = (element.get("class", "") or "").lower()
        element_id = (element.get("id", "") or "").lower()
        for login_class in login_indicators["login_classes"]:
            if login_class in element_class or login_class in element_id:
                login_elements += 1
                break
    
    # 더 엄격한 로그인 페이지 판정 (성공 신호가 없는 경우에만)
    is_login = (
        password_fields > 0 and text_matches >= 1 and login_elements >= 1  # 모든 조건 만족 시에만
    )
    
    logger.info(f"🔐 로그인 페이지 감지: {is_login} (성공신호: {success_signals}, 비밀번호필드: {password_fields}, 텍스트매칭: {text_matches}, 로그인요소: {login_elements})")
    
    return is_login

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


# ============================
# DOM 청킹 시스템
# ============================

def chunk_dom(dom_summary: list, chunk_size: int = 1000) -> list:
    """DOM을 지정된 크기로 청크 분할"""
    chunks = []
    for i in range(0, len(dom_summary), chunk_size):
        chunk = dom_summary[i:i+chunk_size]
        chunks.append(chunk)
    
    logger.info(f"📦 DOM 청킹: {len(dom_summary)}개 요소 → {len(chunks)}개 청크 (청크당 최대 {chunk_size}개)")
    return chunks


async def analyze_dom_chunks(goal: str, dom_summary: list, image_data: str, current_step: int, plan: list) -> dict:
    """DOM 청크를 순차적으로 분석하여 최적 액션 찾기 (컨텍스트 유지)"""
    
    # DOM을 1000개씩 분할
    chunks = chunk_dom(dom_summary, chunk_size=1000)
    candidate_actions = []
    accumulated_context = {
        "page_structure": [],
        "key_areas": [],
        "interactive_elements": [],
        "navigation_found": False,
        "main_content_area": None,
        "action_candidates_count": 0
    }
    
    for i, chunk in enumerate(chunks):
        logger.info(f"🔍 청크 {i+1}/{len(chunks)} 분석 중... ({len(chunk)}개 요소)")
        
        # 이전 컨텍스트를 포함한 청크별 실행 프롬프트 생성
        prompt = build_chunk_execution_prompt_with_context(
            goal, chunk, i+1, len(chunks), current_step, plan, accumulated_context
        )
        
        try:
            response = await call_llm_with_image(prompt, image_data)
            action_json = extract_top_level_json(response)
            
            if action_json:
                parsed_action = json.loads(action_json)
                
                # 컨텍스트 정보 업데이트
                update_accumulated_context(accumulated_context, chunk, parsed_action, response)
                
                if parsed_action.get("action") not in ["none", "no_action"]:
                    candidate_actions.append({
                        "chunk_index": i,
                        "action": parsed_action,
                        "elements_count": len(chunk),
                        "confidence": parsed_action.get("confidence", 0.5),
                        "context_aware": True
                    })
                    accumulated_context["action_candidates_count"] += 1
                    logger.info(f"✅ 청크 {i+1}에서 액션 발견: {parsed_action.get('action')} (신뢰도: {parsed_action.get('confidence', 'N/A')})")
                else:
                    logger.info(f"⏭️ 청크 {i+1}에서 적합한 액션 없음")
        
        except Exception as e:
            logger.error(f"❌ 청크 {i+1} 분석 실패: {e}")
            continue
    
    # 후보 액션들 중 최선 선택
    if candidate_actions:
        logger.info(f"🎯 총 {len(candidate_actions)}개 후보 액션 발견")
        return select_best_action(candidate_actions, goal)
    else:
        logger.info("❌ 모든 청크에서 적합한 액션을 찾지 못함")
        return {"action": "end", "reason": "No suitable action found in any DOM chunk"}


def select_best_action(candidate_actions: list, goal: str) -> dict:
    """여러 후보 액션 중 최선 선택"""
    
    if len(candidate_actions) == 1:
        logger.info("🎯 단일 후보 액션 자동 선택")
        return candidate_actions[0]["action"]
    
    # 신뢰도 기반 정렬
    candidate_actions.sort(key=lambda x: x["action"].get("confidence", 0.5), reverse=True)
    
    # 가장 높은 신뢰도의 액션 선택
    best_action = candidate_actions[0]["action"]
    logger.info(f"🏆 최고 신뢰도 액션 선택: {best_action.get('action')} (신뢰도: {best_action.get('confidence', 'N/A')})")
    
    # 디버깅을 위해 모든 후보 로깅
    for i, candidate in enumerate(candidate_actions):
        action = candidate["action"]
        logger.info(f"   후보 {i+1}: {action.get('action')} (신뢰도: {action.get('confidence', 'N/A')}) - {action.get('reason', 'No reason')}")
    
    return best_action


def build_chunk_execution_prompt(goal: str, chunk: list, chunk_num: int, total_chunks: int, current_step: int, plan: list) -> str:
    """청크별 실행 프롬프트 생성"""
    
    # 계획 정보
    plan_context = ""
    if plan and current_step < len(plan):
        plan_context = f"\n현재 계획 단계: {plan[current_step].get('action', 'Unknown')}"
    
    prompt = f"""🧠 **DOM 청크 분석 및 액션 실행**

**목표:** {goal}
**분석 범위:** 청크 {chunk_num}/{total_chunks} ({len(chunk)}개 요소){plan_context}

**이 청크의 DOM 요소들:**
{json.dumps(chunk, ensure_ascii=False, indent=2)}

**분석 지침:**
1. 🎯 **목표 달성을 위한 최적 액션 찾기**
2. 🔍 **이 청크 내에서만 액션 가능한 요소 탐색**
3. 📊 **신뢰도 점수 부여 (0.0~1.0)**

**액션 우선순위:**
- 🎯 목표와 직접 관련된 버튼/링크 (높은 신뢰도)
- 📧 이메일, 메일 관련 요소 (중간 신뢰도)
- 🧭 내비게이션 요소 (낮은 신뢰도)

**출력 형식:**
적합한 액션이 있으면:
{{"action":"click|fill|goto|google_search|hover|waitUntil", "selector":"<css>", 
  "text":"<optional>", "value":"<optional>", "url":"<optional>", "timeout":1000,
  "confidence": 0.8, "reason": "why this action is suitable"}}

적합한 액션이 없으면:
{{"action":"none", "reason": "no suitable element in this chunk"}}

**Return ONLY the JSON, no other text:**"""
    
    return prompt


def build_chunk_execution_prompt_with_context(goal: str, chunk: list, chunk_num: int, total_chunks: int, 
                                              current_step: int, plan: list, accumulated_context: dict) -> str:
    """컨텍스트를 포함한 청크별 실행 프롬프트 생성"""
    
    # 계획 정보
    plan_context = ""
    if plan and current_step < len(plan):
        plan_context = f"\n현재 계획 단계: {plan[current_step].get('action', 'Unknown')}"
    
    # 누적 컨텍스트 요약
    context_summary = build_context_summary(accumulated_context, chunk_num, total_chunks)
    
    prompt = f"""🧠 **DOM 청크 분석 및 액션 실행 (컨텍스트 포함)**

**목표:** {goal}
**분석 범위:** 청크 {chunk_num}/{total_chunks} ({len(chunk)}개 요소){plan_context}

{context_summary}

**현재 청크의 DOM 요소들:**
{json.dumps(chunk, ensure_ascii=False, indent=2)}

**분석 지침:**
1. 🧠 **이전 분석 결과를 고려하여** 목표 달성을 위한 최적 액션 찾기
2. 🔍 **이 청크 내에서만 액션 가능한 요소 탐색**
3. 📊 **신뢰도 점수 부여 (0.0~1.0)**
4. 🔗 **이전 청크에서 발견된 정보와의 연관성 고려**

**액션 우선순위 (컨텍스트 기반):**
- 🎯 목표와 직접 관련되고 이전 맥락과 일치하는 요소 (최고 신뢰도)
- 📧 이전 청크에서 확인된 패턴과 일치하는 요소 (높은 신뢰도)
- 🧭 새로 발견된 내비게이션/기능 요소 (중간 신뢰도)

**출력 형식:**
적합한 액션이 있으면:
{{"action":"click|fill|goto|google_search|hover|waitUntil", "selector":"<css>", 
  "text":"<optional>", "value":"<optional>", "url":"<optional>", "timeout":1000,
  "confidence": 0.8, "reason": "why this action is suitable with context"}}

적합한 액션이 없으면:
{{"action":"none", "reason": "no suitable element in this chunk"}}

**Return ONLY the JSON, no other text:**"""
    
    return prompt


def build_context_summary(accumulated_context: dict, current_chunk: int, total_chunks: int) -> str:
    """누적 컨텍스트를 요약한 텍스트 생성"""
    
    if current_chunk == 1:
        return "**컨텍스트:** 첫 번째 청크 - 페이지 구조 파악 시작"
    
    summary_parts = []
    
    # 페이지 구조 정보
    if accumulated_context["page_structure"]:
        structures = ", ".join(accumulated_context["page_structure"][-3:])  # 최근 3개만
        summary_parts.append(f"📋 **발견된 페이지 구조:** {structures}")
    
    # 주요 영역 정보
    if accumulated_context["key_areas"]:
        areas = ", ".join(accumulated_context["key_areas"][-3:])  # 최근 3개만
        summary_parts.append(f"🗺️ **주요 영역:** {areas}")
    
    # 인터랙티브 요소
    if accumulated_context["interactive_elements"]:
        elements = ", ".join(accumulated_context["interactive_elements"][-3:])  # 최근 3개만
        summary_parts.append(f"🔘 **발견된 인터랙티브 요소:** {elements}")
    
    # 내비게이션 발견 여부
    if accumulated_context["navigation_found"]:
        summary_parts.append("🧭 **내비게이션 구조 확인됨**")
    
    # 메인 콘텐츠 영역
    if accumulated_context["main_content_area"]:
        summary_parts.append(f"📄 **메인 콘텐츠 영역:** {accumulated_context['main_content_area']}")
    
    # 액션 후보 개수
    if accumulated_context["action_candidates_count"] > 0:
        summary_parts.append(f"🎯 **이전 액션 후보:** {accumulated_context['action_candidates_count']}개 발견")
    
    if not summary_parts:
        return f"**컨텍스트:** 청크 {current_chunk-1}개 분석 완료 - 특별한 발견사항 없음"
    
    return "**🧠 이전 청크 분석 결과:**\n" + "\n".join(f"   - {part}" for part in summary_parts)


def update_accumulated_context(context: dict, chunk: list, parsed_action: dict, response: str):
    """청크 분석 결과를 누적 컨텍스트에 업데이트"""
    
    # 페이지 구조 요소 탐지
    structural_elements = []
    for element in chunk:
        tag = element.get("tag", "").lower()
        if tag in ["nav", "header", "main", "section", "aside", "footer"]:
            structural_elements.append(tag)
        elif "nav" in element.get("class", "").lower():
            structural_elements.append("navigation")
        elif "menu" in element.get("class", "").lower():
            structural_elements.append("menu")
    
    if structural_elements:
        context["page_structure"].extend(structural_elements)
        context["page_structure"] = list(set(context["page_structure"]))  # 중복 제거
    
    # 주요 영역 탐지
    key_areas = []
    for element in chunk:
        text = element.get("text", "").lower()
        class_name = element.get("class", "").lower()
        if any(keyword in text for keyword in ["메일", "mail", "inbox", "받은편지함"]):
            key_areas.append("메일 영역")
        elif any(keyword in class_name for keyword in ["content", "main", "list"]):
            key_areas.append("콘텐츠 영역")
        elif element.get("tag") == "form":
            key_areas.append("폼 영역")
    
    if key_areas:
        context["key_areas"].extend(key_areas)
        context["key_areas"] = list(set(context["key_areas"]))  # 중복 제거
    
    # 인터랙티브 요소 탐지
    interactive_types = []
    for element in chunk:
        tag = element.get("tag", "").lower()
        if tag in ["button", "input", "a", "select", "textarea"]:
            interactive_types.append(tag)
    
    if interactive_types:
        context["interactive_elements"].extend(interactive_types)
        context["interactive_elements"] = list(set(context["interactive_elements"]))  # 중복 제거
    
    # 내비게이션 발견
    if any("nav" in element.get("tag", "").lower() or "nav" in element.get("class", "").lower() 
           for element in chunk):
        context["navigation_found"] = True
    
    # 메인 콘텐츠 영역 식별
    for element in chunk:
        if element.get("tag") == "main" or "main" in element.get("class", "").lower():
            context["main_content_area"] = "main"
            break
        elif "content" in element.get("class", "").lower():
            context["main_content_area"] = "content"
            break


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
    
    # 로그인 재시도 방지 플래그
    login_skip_detection = False
    
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

            # ---------- user_continue ----------  
            if payload.get("type") == "user_continue":
                logger.info("▶️ 사용자 진행 요청 - 자동화 재개")
                login_skip_detection = True  # 로그인 감지 스킵 플래그 설정
                await websocket.send_text(json.dumps({
                    "type": "automation_resumed", 
                    "message": "자동화가 재개됩니다.",
                    "timestamp": datetime.now().isoformat()
                }))
                # DOM 재요청
                await websocket.send_text(json.dumps({
                    "type": "request_dom",
                    "message": "로그인 완료 후 페이지 정보를 다시 분석합니다."
                }))
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
                    
                    # 로그인 페이지 감지 시 대기 모드 (스킵 플래그 확인)
                    if page_analysis.get("is_login_page") and not login_skip_detection:
                        logger.info("🔐 로그인 페이지 감지 - 사용자 대기 모드 활성화")
                        await websocket.send_text(json.dumps({
                            "type": "login_detected",
                            "message": "로그인이 필요합니다. 로그인을 완료한 후 '진행' 버튼을 눌러주세요.",
                            "show_continue_button": True,
                            "timestamp": datetime.now().isoformat()
                        }))
                        continue  # 자동화 일시 정지
                    elif login_skip_detection:
                        logger.info("🔓 로그인 감지 스킵 - 사용자가 진행 요청했음")
                        login_skip_detection = False  # 플래그 리셋
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
                    
                    if not response:
                        await websocket.send_text(json.dumps({"type": "error", "detail": "LLM 응답 없음"}))
                        continue

                    logger.info(f"🧠 평가 LLM 응답: {response}")
                    jtxt = extract_top_level_json(response)
                    logger.info(f"🔍 추출된 JSON: {jtxt}")
                    if not jtxt:
                        logger.error(f"❌ JSON 추출 실패 - 원본: {response}")
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {response}"}))
                        continue

                    try:
                        result = json.loads(jtxt)
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ 오류: JSON 파싱 실패: {jtxt}")
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {jtxt}"}))
                        continue
                else:
                    # 실행 모드: DOM 크기에 따라 청킹 vs 일반 처리
                    if len(dom_summary) > 1000:
                        logger.info(f"🔄 대용량 DOM 감지 ({len(dom_summary)}개) - 청킹 모드 사용")
                        try:
                            result = await analyze_dom_chunks(goal, dom_summary, image_data, step, plan or [])
                        except Exception as e:
                            logger.error(f"❌ 청킹 분석 실패: {e}")
                            await websocket.send_text(json.dumps({"type": "error", "detail": f"청킹 분석 실패: {e}"}))
                            continue
                    else:
                        logger.info(f"📝 일반 DOM ({len(dom_summary)}개) - 단일 호출 모드")
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
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ 오류: JSON 파싱 실패: {jtxt}")
                            await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {jtxt}"}))
                            continue

                # 공통 처리 로직 (청킹/일반 모드 모두 적용)
                try:
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
