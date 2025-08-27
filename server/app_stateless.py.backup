from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AzureOpenAI
from starlette.websockets import WebSocketDisconnect
import os, json, re, logging, base64
from datetime import datetime
import asyncio

load_dotenv()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

# 이미지 저장 디렉토리 생성
os.makedirs("debug_images", exist_ok=True)

# === Stateless 서버 - 컨텍스트는 Extension에서 관리 ===
# ConversationContext 클래스와 세션 관리 제거됨
# 모든 컨텍스트는 클라이언트에서 전송됨

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

async def refine_prompt_with_llm(user_message: str) -> str:
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-15-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    refine_prompt = f'''
아래 사용자의 입력을 브라우저 자동화 명령문(한 문장, 명확하고 간결하게)으로 변환해 주세요.
명령문은 반드시 직접적이고 구체적으로 작성하세요.

입력: "{user_message}"

출력 예시:
- "메일함으로 가서 첫 번째 메일을 읽어줘" → "메일함으로 이동 후 첫 번째 메일 클릭"
- "로그인 버튼이 있으면 눌러줘" → "로그인 버튼 클릭"
- "검색창에 'AI' 입력하고 검색 버튼 클릭" → "검색창에 'AI' 입력 후 검색 버튼 클릭"

명령문:
'''
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        messages=[{"role": "user", "content": refine_prompt}],
        max_tokens=100,
        temperature=0.1
    )
    return response.choices[0].message.content.strip().replace('\n', ' ')

def compress_dom(dom: list) -> list:
    compressed = []
    for el in dom:
        if not el.get("selector"):
            continue
        
        # 더 정확한 선택자 생성
        selector = el.get("selector")
        tag = el.get("tag")
        
        # 우선순위: id > name > class > tag
        if el.get("id"):
            selector = f"#{el['id']}"
        elif el.get("name"):
            selector = f"{tag}[name='{el['name']}']"
        elif el.get("type"):
            selector = f"{tag}[type='{el['type']}']"
        elif selector and not selector.startswith("#") and not selector.startswith("."):
            # 기존 선택자가 단순한 경우 유지
            pass
        else:
            # 기본 태그 선택자
            selector = tag
        
        entry = {
            "tag": tag,
            "selector": selector
        }
        
        # 추가 속성들
        if el.get("type"):
            entry["type"] = el["type"]
        if el.get("id"):
            entry["id"] = el["id"]
        if el.get("name"):
            entry["name"] = el["name"]
        if el.get("class"):
            entry["class"] = el["class"]
            
        if txt := el.get("text"):
            txt = txt.strip()
            if txt:
                entry["text"] = txt[:50]  # 텍스트 길이 증가
                
        compressed.append(entry)
    return compressed[:50]  # 더 많은 요소 포함

def build_planning_prompt_with_image(goal: str, dom_summary: list, context: dict = None) -> str:
    context_info = ""
    if context:
        context_info = f"""
CONTEXT INFORMATION:
- Current Step: {context.get('step', 0)}
- Previous Actions: {len(context.get('conversationHistory', []))} messages
- Last Action: {json.dumps(context.get('lastAction'), ensure_ascii=False) if context.get('lastAction') else 'None'}
"""

    return f"""
You are a browser automation planner with visual understanding. Analyze the goal and current DOM to create a detailed step-by-step plan.

🎨 VISUAL WIREFRAME GUIDE:
The attached image is a structured wireframe representation of the webpage with color-coded elements:
- 🔵 BLUE background + thick border = BUTTONS (clickable actions)
- ⚪ LIGHT GRAY background = INPUT FIELDS/TEXTAREAS (fillable)
- 🟡 YELLOW background = SELECT DROPDOWNS (selectable options)
- 🔗 BLUE dotted border = LINKS (navigation)
- 🟠 ORANGE background + thick border = HEADINGS (H1-H6, important text)
- 🟢 GREEN background + [IMG] = IMAGES (visual content)
- 🟣 PURPLE dotted border = LISTS (UL/OL/LI items)
- 🔷 LIGHT BLUE background + dotted border = FORMS (form containers)
- Gray thin border = Other elements (DIV, SPAN, etc.)

This wireframe shows the exact layout, element positions, and text content clearly for precise automation.

Goal: "{goal}"
{context_info}
Current DOM Summary:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

Create a detailed plan with 3-8 steps. Each step should be specific and actionable.
Use both the visual wireframe and DOM summary to understand the page structure.

⚠️ BROWSER SECURITY LIMITATIONS:
- CANNOT control browser UI elements (address bar, back/forward buttons, tabs)
- CANNOT use "focus", "fill", or "press" actions on browser UI
- CAN ONLY control DOM elements within the current webpage
- For navigation, use "goto" action with full URL instead of typing in address bar

IMPORTANT SELECTOR GUIDELINES:
1. Use EXACT selectors from the DOM summary above when available
2. Prefer simple, reliable selectors: id > name > type > class > tag
3. Avoid complex CSS selectors like "ul.mail_list > li:first-child"
4. If exact selector not available, use text-based matching
5. For lists, prefer "li" with text content rather than complex selectors
6. For buttons/links, prefer "a" or "button" with text content
7. Use the visual wireframe to understand element relationships and positioning

Return ONLY a JSON array like:
[
  {{"step": 1, "action": "goto", "target": "navigate to website", "reason": "Navigate to target site", "url": "https://example.com"}},
  {{"step": 2, "action": "click", "target": "login button", "reason": "Start login process", "selector": "button[type='submit']"}},
  {{"step": 3, "action": "fill", "target": "username field", "reason": "Enter credentials", "selector": "input[name='username']", "value": "username"}}
]

Guidelines:
- Each step should be atomic and specific
- Use selectors from the DOM summary when possible
- Prefer id, name, or specific attributes over complex CSS selectors
- If exact selector not available, use text-based matching
- Plan should be logical and efficient
- Leverage the visual wireframe to understand layout and element relationships
- Consider element colors in the wireframe to identify element types quickly
"""

def build_execution_prompt_with_image(goal: str, plan: list, current_step: int, dom_summary: list, context: dict = None) -> str:
    context_info = ""
    if context:
        context_info = f"""
CONTEXT INFORMATION:
- Session ID: {context.get('sessionId', 'unknown')}
- Current Step: {context.get('step', current_step)}
- Total Actions: {context.get('totalActions', 0)}
- Last Action: {json.dumps(context.get('lastAction'), ensure_ascii=False) if context.get('lastAction') else 'None'}
"""

    rules = f"""
⚠️ Guidelines:
- If a dropdown or submenu is involved: hover the parent, waitUntil it appears, then click.
- Do NOT repeat the same action if DOM did not change.
- Each step must return only one atomic action.
- Return {{"action": "end"}} if the goal is completed.
- Use the visual wireframe to understand layout and identify elements precisely.

🎨 VISUAL WIREFRAME LEGEND:
- 🔵 BLUE background = BUTTONS (clickable)
- ⚪ LIGHT GRAY background = INPUT FIELDS (fillable)
- 🟡 YELLOW background = SELECT DROPDOWNS
- 🔗 BLUE dotted border = LINKS
- 🟠 ORANGE background = HEADINGS (H1-H6)
- 🟢 GREEN background + [IMG] = IMAGES
- 🟣 PURPLE dotted border = LISTS
- 🔷 LIGHT BLUE background = FORMS
- Gray thin border = Other elements

🚫 BROWSER SECURITY LIMITATIONS:
- CANNOT control browser UI elements (address bar, back/forward buttons, tabs)
- CANNOT use "focus", "fill", or "press" actions on browser UI
- CAN ONLY control DOM elements within the current webpage
- For navigation, use "goto" action with full URL instead of typing in address bar
"""

    return f"""
You are executing step {current_step} of a browser automation plan with visual understanding.

The attached image is a color-coded wireframe showing the exact page structure. Use both the visual wireframe and DOM data to identify elements accurately.

Goal: "{goal}"
Current Step: {current_step}
Plan: {json.dumps(plan, ensure_ascii=False, indent=2)}
{context_info}

DOM Summary:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

{rules}

Execute ONLY the current step. Return JSON:
{{
  "action": "click" | "fill" | "goto" | "hover" | "waitUntil" | "end",
  "selector": "<CSS selector>",
  "text": "optional text for matching",
  "value": "optional value",
  "url": "full URL for goto action",
  "condition": "optional condition selector",
  "timeout": 1000
}}
"""

def build_prompt_with_image(goal: str, dom_summary: list, step: int, context: dict = None) -> str:
    context_info = ""
    if context:
        context_info = f"""
CONTEXT INFORMATION:
- Session ID: {context.get('sessionId', 'unknown')}
- Current Step: {context.get('step', step)}
- Total Actions: {context.get('totalActions', 0)}
- Last Action: {json.dumps(context.get('lastAction'), ensure_ascii=False) if context.get('lastAction') else 'None'}
"""

    rules = """
⚠️ Guidelines:
- If a dropdown or submenu is involved: hover the parent, waitUntil it appears, then click.
- Do NOT repeat the same action if DOM did not change.
- Each step must return only one atomic action.
- Return {"action": "end"} if the goal is completed.
- Use the visual wireframe to understand layout and identify elements precisely.

🎨 VISUAL WIREFRAME LEGEND:
The attached image uses color-coding to identify different element types:
- 🔵 BLUE background = BUTTONS (clickable actions)
- ⚪ LIGHT GRAY background = INPUT FIELDS/TEXTAREAS (fillable)
- 🟡 YELLOW background = SELECT DROPDOWNS (selectable)
- 🔗 BLUE dotted border = LINKS (navigation)
- 🟠 ORANGE background = HEADINGS (H1-H6, important text)
- 🟢 GREEN background + [IMG] = IMAGES (visual content)
- 🟣 PURPLE dotted border = LISTS (UL/OL/LI items)
- 🔷 LIGHT BLUE background = FORMS (form containers)
- Gray thin border = Other elements (DIV, SPAN, etc.)
"""

    return f"""
You are a browser control agent (MCP) with visual understanding.

The attached image is a structured wireframe showing the webpage layout with color-coded elements for easy identification.

Goal: "{goal}"
Step: {step}
{context_info}

DOM Summary:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

{rules}

Respond ONLY with one JSON object like:
{{
  "action": "click" | "fill" | "goto" | "hover" | "waitUntil" | "end",
  "selector": "<CSS selector>",
  "text": "optional text for matching",
  "value": "optional value",
  "url": "full URL for goto action",
  "condition": "optional condition selector",
  "timeout": 1000
}}
"""

def clean_action(action: dict) -> dict:
    if action.get("action") in ["click", "hover"]:
        action.pop("value", None)
    if action.get("action") != "extract":
        action.pop("extract", None)
        action.pop("attribute", None)
    return action

def save_debug_image(image_data: str, step: int, goal: str = None) -> str:
    """받은 이미지를 PNG로 저장하고 파일 경로 반환"""
    try:
        logger.info(f"💾 이미지 저장 시작 (스텝: {step}, 목표: {goal})")
        
        # base64 데이터 URL에서 실제 base64 데이터 추출
        original_data = image_data
        if image_data.startswith('data:image'):
            # "data:image/png;base64," 부분 제거
            image_data = image_data.split(',')[1]
            logger.info("✅ base64 데이터 URL 형식 확인됨")
        else:
            logger.warning("⚠️ base64 데이터 URL 형식이 아님, 원본 데이터 사용")
        
        # base64 디코딩
        image_bytes = base64.b64decode(image_data)
        logger.info(f"✅ base64 디코딩 완료: {len(image_bytes)} bytes")
        
        # 파일명 생성 (목표 + 스텝 + 타임스탬프)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 목표를 파일명에 포함 (간단하게)
        goal_safe = ""
        if goal:
            # 목표에서 안전한 문자만 추출
            goal_words = goal.split()[:3]  # 처음 3개 단어만
            goal_safe = "_" + "_".join(goal_words).replace(" ", "_")[:20]
            goal_safe = goal_safe.replace("/", "_").replace("\\", "_")  # 안전하지 않은 문자 제거
        
        filename = f"debug_images/step_{step}{goal_safe}_{timestamp}.png"
        logger.info(f"📝 파일명: {filename}")
        
        # PNG로 저장 (원본 형식 유지)
        with open(filename, 'wb') as f:
            f.write(image_bytes)
        
        # 파일 크기 확인
        file_size = len(image_bytes)
        file_size_kb = file_size / 1024
        
        logger.info(f"💾 이미지 저장 완료: {filename}")
        logger.info(f"   📊 파일 크기: {file_size_kb:.1f} KB ({file_size} bytes)")
        logger.info(f"   📐 이미지 정보: PNG 형식, base64 디코딩 완료")
        
        return filename
    except Exception as e:
        logger.error(f"❌ 이미지 저장 실패: {e}")
        logger.error(f"   🔍 원본 데이터 길이: {len(original_data) if original_data else 0}")
        logger.error(f"   🔍 처리된 데이터 길이: {len(image_data) if image_data else 0}")
        logger.error(f"   🔍 데이터 타입: {type(image_data)}")
        logger.error(f"   🔍 데이터 접두사: {image_data[:50] if image_data else 'None'}...")
        return None

async def call_llm_with_image(prompt: str, image_data: str):
    """이미지와 함께 LLM 호출"""
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        # base64 데이터 URL에서 실제 base64 데이터 추출
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision API 호출 실패: {e}")
        return None

async def call_llm(prompt: str):
    """텍스트 전용 LLM 호출 (stateless)"""
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        messages = [{"role": "user", "content": prompt}]
        
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            messages=messages,
            max_tokens=500,
            temperature=0.1
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM 호출 실패: {e}")
        return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket 연결 수락됨 (Stateless 서버)")

    try:
        while True:
            logger.info("⏳ 메시지 대기 중...")
            raw = await websocket.receive_text()
            logger.info(f"📨 메시지 수신: {len(raw)} characters")
            
            try:
                payload = json.loads(raw)
                logger.info(f"📋 메시지 타입: {payload.get('type')}")
                logger.info(f"📋 메시지 키들: {list(payload.keys())}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 파싱 실패: {e}")
                logger.error(f"❌ 원본 데이터: {raw[:200]}...")
                continue

            if payload.get("type") == "init":
                # 단순한 초기화 확인
                user_goal = payload["message"]
                logger.info(f"🆕 새 목표: {user_goal}")
                
                await websocket.send_text(json.dumps({
                    "type": "init_confirmed",
                    "message": "목표가 설정되었습니다. DOM을 전송해주세요."
                }))
                continue

            if payload.get("type") == "dom_with_image":
                logger.info("🔄 DOM + 이미지 처리 시작")
                
                # 컨텍스트 정보 추출
                context = payload.get("context", {})
                goal = context.get("goal", payload.get("message", ""))
                step = context.get("step", 0)
                plan = context.get("plan", [])
                
                logger.info(f"📋 컨텍스트 정보:")
                logger.info(f"   - 목표: {goal}")
                logger.info(f"   - 단계: {step}")
                logger.info(f"   - 계획: {len(plan)}개 단계")
                logger.info(f"   - 총 액션: {context.get('totalActions', 0)}개")
                
                if not goal:
                    logger.warning("⚠️ 목표가 없습니다.")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": "목표가 설정되지 않았습니다."
                    }))
                    continue
                
                # DOM 처리
                try:
                    dom_summary = compress_dom(payload["dom"])
                    logger.info(f"📊 DOM 압축 완료: {len(dom_summary)} 요소")
                except Exception as e:
                    logger.error(f"❌ DOM 압축 실패: {e}")
                    continue
                
                image_data = payload.get("image")
                
                # 이미지 저장
                if image_data:
                    saved_path = save_debug_image(image_data, step, goal)
                    if saved_path:
                        logger.info(f"✅ 이미지 저장 완료: {saved_path}")
                
                # Planning 단계 (계획이 없는 경우)
                if not plan and step == 0:
                    logger.info("🧠 Planning 단계 시작...")
                    
                    if image_data:
                        plan_response = await call_llm_with_image(
                            build_planning_prompt_with_image(goal, dom_summary, context), 
                            image_data
                        )
                    else:
                        plan_response = await call_llm(
                            build_planning_prompt_with_image(goal, dom_summary, context)
                        )
                    
                    if plan_response:
                        plan_match = re.search(r'\[.*\]', plan_response, re.DOTALL)
                        if plan_match:
                            try:
                                parsed_plan = json.loads(plan_match.group())
                                logger.info(f"✅ Planning 완료: {len(parsed_plan)} 스텝 계획")
                                
                                await websocket.send_text(json.dumps({
                                    "type": "plan",
                                    "plan": parsed_plan
                                }))
                                continue  # Planning만 하고 끝
                            except json.JSONDecodeError as e:
                                logger.error(f"❌ Planning JSON 파싱 실패: {e}")
                
                # Execution 단계
                logger.info(f"🚀 Execution 단계: Step {step}")
                
                if image_data:
                    if plan:
                        prompt = build_execution_prompt_with_image(goal, plan, step, dom_summary, context)
                    else:
                        prompt = build_prompt_with_image(goal, dom_summary, step, context)
                    response = await call_llm_with_image(prompt, image_data)
                else:
                    # 텍스트 전용은 간단하게 처리
                    prompt = f"Goal: {goal}\nStep: {step}\nDOM: {json.dumps(dom_summary, ensure_ascii=False, indent=2)}\nReturn next action as JSON."
                    response = await call_llm(prompt)

                if not response:
                    logger.error("❌ LLM 응답 없음")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": "LLM 호출 실패"
                    }))
                    continue

                logger.info(f"🧠 LLM 응답: {response[:200]}...")

                # JSON 추출
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    logger.error(f"❌ JSON 파싱 실패: {response}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": f"JSON 파싱 실패: {response}"
                    }))
                    continue

                try:
                    action = json.loads(json_match.group())
                    action = clean_action(action)
                    logger.info(f"✅ 액션 파싱 성공: {action}")
                    
                    if action.get("action") == "end":
                        logger.info("🎯 작업 완료")
                        await websocket.send_text(json.dumps({"type": "end"}))
                    else:
                        logger.info(f"🚀 액션 전송: {action}")
                        await websocket.send_text(json.dumps({
                            "type": "action",
                            "step": step,
                            "action": action
                        }))
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 디코딩 오류: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": f"JSON 파싱 오류: {e}"
                    }))

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket 연결 해제됨")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "detail": str(e)
            }))
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)