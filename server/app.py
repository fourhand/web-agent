from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AzureOpenAI
from starlette.websockets import WebSocketDisconnect
import os, json, re, logging, base64, random
from datetime import datetime
import asyncio
from urllib.parse import quote
from dom_processor import dom_processor

load_dotenv()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

# 디렉토리 생성
os.makedirs("debug_images", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ============================
# 통합 서버 - 단말 상태 관리 + 청크 기능
# ============================

class GoalLogger:
    def __init__(self):
        self.current_goal = None
        self.log_file_path = None

    def start_new_goal(self, goal: str):
        self.current_goal = goal
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_goal = re.sub(r'[^\w\s-]', '', goal)[:20]
        safe_goal = re.sub(r'[-\s]+', '_', safe_goal)
        filename = f"{timestamp}-{safe_goal}.log"
        self.log_file_path = os.path.join("logs", filename)
        self.log("SERVER", "GOAL_START", f"새로운 목표 시작: {goal}")

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

goal_logger = GoalLogger()

# ============================
# 사이트 매핑
# ============================
SITE_MAPPING = {
    "국가교통정보센터": "https://www.its.go.kr",
    "정부24": "https://www.gov.kr",
    "국세청": "https://www.nts.go.kr",
    "건강보험공단": "https://www.nhis.or.kr",
    "한국은행": "https://www.bok.or.kr",
    "네이버": "https://naver.com",
    "다음": "https://daum.net",
}

def find_site_url(query: str) -> str | None:
    q = (query or '').lower().strip()
    for name, url in SITE_MAPPING.items():
        if name.lower() in q or q in name.lower():
            return url
    return None

# ============================
# FastAPI 앱
# ============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# 프롬프트 분석
# ============================
async def analyze_prompt_needs_dom(user_message: str) -> bool:
    """LLM을 사용하여 프롬프트가 DOM 분석이 필요한지 판단"""
    try:
        prompt = f"""
사용자의 요청을 분석하여 브라우저 자동화에 DOM 분석이 필요한지 판단해주세요.

요청: "{user_message}"

DOM 분석이 필요한 경우:
- 특정 요소를 클릭해야 하는 경우
- 폼에 정보를 입력해야 하는 경우  
- 페이지의 특정 내용을 읽거나 확인해야 하는 경우
- 복잡한 내비게이션이나 상호작용이 필요한 경우

DOM 분석이 불필요한 경우:
- 단순히 특정 URL로 이동하는 경우
- 기본적인 사이트 접속만 필요한 경우

답변은 "DOM_NEEDED" 또는 "DOM_NOT_NEEDED" 중 하나로만 해주세요.
"""
        
        response = await call_llm(prompt, max_tokens=50)
        if response:
            result = response.strip().upper()
            needs_dom = "DOM_NEEDED" in result
            logger.info(f"🔍 LLM 분석 결과: {result} -> DOM 필요: {needs_dom}")
            return needs_dom
        else:
            # LLM 실패 시 기본값 (안전하게 DOM 필요로 설정)
            logger.warning("⚠️ LLM 분석 실패 - 기본값 사용")
            return True
            
    except Exception as e:
        logger.error(f"❌ 프롬프트 분석 실패: {e}")
        return True  # 에러 시 안전하게 DOM 필요로 설정

# ============================
# LLM 호출 (Rate-limit 대응)
# ============================
LLM_SEMAPHORE = asyncio.Semaphore(1)

async def call_llm(prompt: str, max_tokens: int = 400):
    async with LLM_SEMAPHORE:
        for attempt in range(5):
            try:
                client = AzureOpenAI(
                    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                    api_version="2024-02-15-preview",
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                )
                res = client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                return res.choices[0].message.content
            except Exception as e:
                message = str(e)
                if "429" in message or "Too Many Requests" in message:
                    backoff = min(20, (2 ** attempt)) + random.uniform(0, 0.5)
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"LLM 호출 실패: {e}")
                return None
        return None

async def call_llm_with_image(prompt: str, image_data: str, max_tokens: int = 400):
    async with LLM_SEMAPHORE:
        for attempt in range(5):
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
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                return res.choices[0].message.content
            except Exception as e:
                message = str(e)
                if "429" in message or "Too Many Requests" in message:
                    backoff = min(20, (2 ** attempt)) + random.uniform(0, 0.5)
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"Vision API 호출 실패: {e}")
                return None
        return None

# ============================
# 프롬프트 빌더
# ============================
def build_planning_prompt_with_image(goal: str, dom_summary: list, context: dict | None = None) -> str:
    return f"""
You are a browser automation planner with visual understanding.

Goal: "{goal}"
Current step: {context.get('step', 0) if context else 0}

DOM Elements:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Create a detailed plan with 3-8 steps. Return ONLY the JSON array:

[{{"step": <int>, "action": "goto|click|fill|hover|waitUntil|end", 
  "selector": "<css>", "text":"<opt>", "value":"<opt>", "url":"<opt>", "reason":"<analysis>"}}]
"""

def build_execution_prompt_with_image(goal: str, plan: list, current_step: int, dom_summary: list, context: dict | None = None) -> str:
    return f"""
Execute the next action toward the goal using DOM analysis.

Goal: "{goal}"
Current Step: {current_step}

DOM State:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Return ONLY the JSON action:

{{"action":"click|fill|goto|hover|waitUntil|end", "selector":"<css>", 
  "text":"<opt>", "value":"<opt>", "url":"<opt>", "timeout":1000}}
"""

def build_evaluation_prompt_with_image(goal: str, dom_summary: list, context: dict | None = None) -> str:
    return f"""
Evaluate progress using DOM analysis.

Goal: "{goal}"
Step: {context.get('step', 0) if context else 0}
Last action: {json.dumps(context.get('lastAction'), ensure_ascii=False) if context and context.get('lastAction') else 'None'}

DOM State:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Return ONLY ONE JSON object:

For COMPLETED: {{"status":"completed","reason":"<analysis>","evidence":"<dom_evidence>"}}
For REPLAN: {{"status":"replan","reason":"<why_failed>","new_plan_needed":true}}
For CONTINUE: {{"status":"continue","action":"click|fill|goto|hover|waitUntil","selector":"<css>","value":"<opt>","url":"<opt>","reason":"<next_step>"}}
"""

# ============================
# DOM 처리 (dom_processor.py에서 처리)
# ============================

# ============================
# 유틸리티 함수
# ============================


def save_debug_image(image_data: str, step: int, goal: str | None = None) -> str | None:
    try:
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
# WebSocket 엔드포인트
# ============================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket 연결 수락됨 (통합 서버)")
    
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
                login_skip_detection = True
                await websocket.send_text(json.dumps({
                    "type": "automation_resumed", 
                    "message": "자동화가 재개됩니다.",
                    "timestamp": datetime.now().isoformat()
                }))
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

                    needs_dom = await analyze_prompt_needs_dom(user_goal)

                    if needs_dom:
                        await websocket.send_text(json.dumps({
                            "type": "request_dom",
                            "message": "현재 페이지 정보가 필요합니다.",
                        }))
                    else:
                        refined_goal = await refine_prompt_with_llm(user_goal)
                        if "로 이동" in refined_goal:
                            url = refined_goal.split("로 이동")[0]
                            action = {"action": "goto", "url": url}
                            await websocket.send_text(json.dumps({
                                "type": "action", "step": 1, "action": action,
                            }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "request_dom",
                                "message": "현재 페이지 정보가 필요합니다.",
                            }))
                except Exception as e:
                    logger.error(f"❌ init 처리 중 오류: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error", "detail": f"초기화 중 오류: {str(e)}",
                }))
                continue

            # ---------- client_log ----------
            if payload.get("type") == "client_log":
                goal_logger.log("CLIENT", payload.get("event_type", "UNKNOWN"), payload.get("message", ""), payload.get("extra_data", {}))
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
                    dom_summary = dom_processor.compress_dom(payload.get("dom", []))
                    logger.info(f"📊 DOM 압축 완료: {len(dom_summary)} 요소")
                    
                    # 페이지 구조 분석 (플랜 검증용)
                    async def llm_callback_for_structure(prompt, img_data):
                        return await call_llm(prompt, max_tokens=400)
                    
                    # 현재 계획 단계 정보
                    current_plan_step = None
                    if plan and step < len(plan):
                        current_plan_step = plan[step]
                    
                    page_structure = await dom_processor.analyze_page_structure(
                        dom_summary, goal, current_plan_step, llm_callback_for_structure
                    )
                    
                    verification_status = page_structure.get('verification_status', 'unknown')
                    logger.info(f"📋 페이지 검증: {verification_status} - {page_structure.get('verification_reason', 'N/A')}")
                    
                    # 검증 결과에 따른 처리
                    if verification_status == "login_required":
                        logger.info("🔐 로그인 필요 상태 감지 - 사용자 대기 모드 활성화")
                        await websocket.send_text(json.dumps({
                            "type": "login_detected",
                            "message": "로그인이 필요합니다. 로그인을 완료한 후 '진행' 버튼을 눌러주세요.",
                            "show_continue_button": True,
                            "timestamp": datetime.now().isoformat()
                        }))
                        continue
                    elif verification_status == "wrong_page":
                        logger.warning("⚠️ 잘못된 페이지 감지 - 재시도 필요")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "detail": "잘못된 페이지에 도달했습니다. 다시 시도해주세요."
                        }))
                        continue
                    elif verification_status == "error_page":
                        logger.error("❌ 오류 페이지 감지")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "detail": "오류 페이지에 도달했습니다."
                        }))
                        continue
                    
                    # 로그인 스킵 플래그 처리 (사용자가 '진행' 버튼을 눌렀을 때)
                    if login_skip_detection:
                        logger.info("🔓 로그인 감지 스킵 - 사용자가 진행 요청했음")
                        login_skip_detection = False
                        
                except Exception as e:
                    logger.error(f"❌ DOM 압축 실패: {e}")
                    continue
                
                image_data = payload.get("image")
                if image_data:
                    save_debug_image(image_data, step, goal)
                
                # Plan (if empty & step==0)
                if not plan and step == 0:
                    prompt = build_planning_prompt_with_image(goal, dom_summary, context)
                    plan_resp = await (call_llm_with_image(prompt, image_data) if image_data else call_llm(prompt))
                    if plan_resp:
                        jtxt = dom_processor.extract_top_level_json(plan_resp)
                        if jtxt:
                            try:
                                parsed = json.loads(jtxt)
                                await websocket.send_text(json.dumps({"type": "plan", "plan": parsed}))
                                continue
                            except json.JSONDecodeError as e:
                                logger.error(f"Planning JSON 파싱 실패: {e}")

                # Execute or Evaluate
                if is_eval:
                    prompt = build_evaluation_prompt_with_image(goal, dom_summary, context)
                    response = await (call_llm_with_image(prompt, image_data) if image_data else call_llm(prompt))
                    
                    if not response:
                        await websocket.send_text(json.dumps({"type": "error", "detail": "LLM 응답 없음"}))
                        continue

                    jtxt = dom_processor.extract_top_level_json(response)
                    if not jtxt:
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {response}"}))
                        continue

                    try:
                        result = json.loads(jtxt)
                    except json.JSONDecodeError as e:
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {jtxt}"}))
                        continue
                else:
                    # 실행 모드: 단일 LLM 호출
                    logger.info(f"📝 DOM 분석 ({len(dom_summary)}개 요소)")
                    if image_data:
                        prompt = build_execution_prompt_with_image(goal, plan, step, dom_summary, context) if plan else build_planning_prompt_with_image(goal, dom_summary, context)
                        response = await call_llm_with_image(prompt, image_data)
                    else:
                        prompt = f"Goal: {goal}\nStep: {step}\nDOM: {json.dumps(dom_summary, ensure_ascii=False, indent=2)}\nReturn next action as JSON."
                        response = await call_llm(prompt)

                    if not response:
                        await websocket.send_text(json.dumps({"type": "error", "detail": "LLM 응답 없음"}))
                        continue

                    jtxt = dom_processor.extract_top_level_json(response)
                    if not jtxt:
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {response}"}))
                        continue
                    
                    try:
                        result = json.loads(jtxt)
                    except json.JSONDecodeError as e:
                        await websocket.send_text(json.dumps({"type": "error", "detail": f"JSON 파싱 실패: {jtxt}"}))
                        continue

                # 공통 처리 로직
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
