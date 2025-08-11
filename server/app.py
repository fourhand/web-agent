from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AzureOpenAI
from starlette.websockets import WebSocketDisconnect
import os, json, re, logging, base64
from datetime import datetime
import asyncio
import requests
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup

load_dotenv()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

# 이미지 저장 디렉토리 생성
os.makedirs("debug_images", exist_ok=True)

# === 사이트명 매핑 ===
SITE_MAPPING = {
    # 한국 주요 사이트
    "네이버": "https://naver.com",
    "다음": "https://daum.net",
    "카카오": "https://kakao.com",
    "네이트": "https://nate.com",
    "줌": "https://zum.com",
    
    # 글로벌 사이트
    "구글": "https://google.com",
    "유튜브": "https://youtube.com",
    "페이스북": "https://facebook.com",
    "인스타그램": "https://instagram.com",
    "트위터": "https://twitter.com",
    "링크드인": "https://linkedin.com",
    "아마존": "https://amazon.com",
    "ebay": "https://ebay.com",
    "위키피디아": "https://wikipedia.org",
    
    # 한국 정부/공공기관
    "국가교통정보센터": "https://www.its.go.kr",
    "정부24": "https://www.gov.kr",
    "국세청": "https://www.nts.go.kr",
    "건강보험공단": "https://www.nhis.or.kr",
    "한국은행": "https://www.bok.or.kr",
    
    # 개발/기술
    "깃허브": "https://github.com",
    "스택오버플로우": "https://stackoverflow.com",
    "노션": "https://notion.so",
    "슬랙": "https://slack.com",
    "디스코드": "https://discord.com",
    
    # 이커머스
    "쿠팡": "https://coupang.com",
    "11번가": "https://11st.co.kr",
    "gmarket": "https://gmarket.co.kr",
    "옥션": "https://auction.co.kr",
    "알리익스프레스": "https://aliexpress.com",
    
    # 교육
    "코세라": "https://coursera.org",
    "유데미": "https://udemy.com",
    "칸아카데미": "https://khanacademy.org",
    
    # 뉴스/미디어
    "조선일보": "https://chosun.com",
    "중앙일보": "https://joongang.co.kr",
    "동아일보": "https://donga.com",
    "한겨레": "https://hani.co.kr",
    "경향신문": "https://khan.co.kr",
    "bbc": "https://bbc.com",
    "cnn": "https://cnn.com",
    "넷플릭스": "https://netflix.com"
}

async def google_search_multiple_results(query: str, max_results: int = 7) -> list:
    """Google 검색에서 여러 결과의 URL과 제목을 반환"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Google 검색 URL 생성
        search_url = f"https://www.google.com/search?q={quote(query)}"
        
        # Google 검색 결과 페이지 가져오기
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # BeautifulSoup으로 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        # 검색 결과 컨테이너 찾기
        search_results = soup.find_all('div', class_='g')
        
        for result in search_results[:max_results]:
            try:
                # 제목 링크 찾기
                title_link = result.find('h3')
                if not title_link:
                    continue
                    
                # 부모 a 태그에서 URL 가져오기
                link_element = title_link.find_parent('a')
                if not link_element:
                    continue
                    
                href = link_element.get('href')
                if href and href.startswith('/url?q='):
                    # Google의 리다이렉트 URL에서 실제 URL 추출
                    actual_url = href.split('/url?q=')[1].split('&')[0]
                    
                    # URL 유효성 검사
                    parsed = urlparse(actual_url)
                    if parsed.scheme in ['http', 'https'] and parsed.netloc:
                        # 제목 텍스트 추출
                        title = title_link.get_text().strip()
                        
                        # 설명 텍스트 찾기
                        description_element = result.find('span', class_='VuuXrf') or result.find('div', class_='VwiC3b')
                        description = description_element.get_text().strip() if description_element else ""
                        
                        results.append({
                            'url': actual_url,
                            'title': title,
                            'description': description[:200] + "..." if len(description) > 200 else description
                        })
                        
            except Exception as e:
                logger.warning(f"개별 검색 결과 파싱 실패: {e}")
                continue
        
        logger.info(f"Google 검색 결과 {len(results)}개 발견: {query}")
        return results
        
    except Exception as e:
        logger.error(f"Google 검색 실패: {query}, 오류: {e}")
        return []

async def select_best_search_result(query: str, search_results: list) -> str:
    """LLM을 사용해서 검색 결과 중 가장 적합한 사이트를 선택"""
    if not search_results:
        return f"https://www.google.com/search?q={quote(query)}"
    
    if len(search_results) == 1:
        return search_results[0]['url']
    
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        # 검색 결과 목록을 텍스트로 변환
        results_text = ""
        for i, result in enumerate(search_results, 1):
            results_text += f"{i}. {result['title']}\n"
            results_text += f"   URL: {result['url']}\n"
            results_text += f"   설명: {result['description']}\n\n"
        
        selection_prompt = f'''
사용자가 "{query}"로 검색했습니다. 
아래 검색 결과 중에서 사용자의 의도에 가장 적합한 사이트를 선택해주세요.

검색 결과:
{results_text}

선택 기준:
1. 공식 홈페이지 우선 (공식 사이트 > 서브 도메인 > 제3자 사이트)
2. 한국어 사이트 우선 (한국 사용자 대상)
3. 신뢰할 수 있는 도메인 우선
4. 사용자 검색 의도와 가장 일치하는 사이트

가장 적합한 결과의 번호만 답해주세요 (1, 2, 3, 4, 5, 6, 7 중 하나):
'''
        
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            messages=[{"role": "user", "content": selection_prompt}],
            max_tokens=10,
            temperature=0.1
        )
        
        # LLM 응답에서 숫자 추출
        llm_choice = response.choices[0].message.content.strip()
        try:
            selected_index = int(llm_choice) - 1
            if 0 <= selected_index < len(search_results):
                selected_url = search_results[selected_index]['url']
                logger.info(f"LLM이 선택한 결과: {selected_index + 1}번 - {selected_url}")
                return selected_url
        except ValueError:
            logger.warning(f"LLM 응답 파싱 실패: {llm_choice}")
        
        # LLM 응답 파싱 실패 시 첫 번째 결과 반환
        return search_results[0]['url']
        
    except Exception as e:
        logger.error(f"LLM 선택 실패: {e}")
        # LLM 실패 시 첫 번째 결과 반환
        return search_results[0]['url']

async def google_search_best_result(query: str) -> str:
    """Google 검색 후 LLM이 가장 적합한 결과를 선택해서 반환"""
    search_results = await google_search_multiple_results(query)
    if not search_results:
        logger.warning(f"Google 검색 결과 없음: {query}")
        return f"https://www.google.com/search?q={quote(query)}"
    
    best_url = await select_best_search_result(query, search_results)
    logger.info(f"최종 선택된 URL: {query} -> {best_url}")
    return best_url

def find_site_url(query: str) -> str:
    """사이트명으로 URL을 찾기 (매핑 우선, 없으면 Google 검색)"""
    # 소문자로 변환하여 검색
    query_lower = query.lower().strip()
    
    # 매핑에서 직접 찾기
    for site_name, url in SITE_MAPPING.items():
        if site_name.lower() in query_lower or query_lower in site_name.lower():
            logger.info(f"사이트 매핑 발견: {query} -> {url}")
            return url
    
    # 매핑에 없으면 Google 검색으로 찾기 (7개 결과 중 최적 선택)
    logger.info(f"매핑에 없는 사이트, Google 검색 사용: {query}")
    return None  # 비동기 함수이므로 나중에 처리

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

    # 먼저 사이트명이 포함되어 있는지 확인
    detected_url = find_site_url(user_message)
    
    if detected_url:
        # 매핑에서 발견된 경우 직접 URL로 이동 명령 생성
        return f"{detected_url}로 이동"
    
    # 매핑에 없는 사이트명인지 확인 (Google 검색 필요)
    site_keywords = ["사이트", "홈페이지", "웹사이트", "페이지", "들어가", "접속", "이동"]
    has_site_keyword = any(keyword in user_message for keyword in site_keywords)
    
    if has_site_keyword:
        # 사이트 관련 키워드가 있지만 매핑에 없는 경우 Google 검색 사용
        try:
            search_result_url = await google_search_best_result(user_message)
            return f"{search_result_url}로 이동"
        except Exception as e:
            logger.error(f"Google 검색 실패: {e}")
            # 검색 실패 시 일반 명령어 처리로 넘어감

    refine_prompt = f'''
아래 사용자의 입력을 브라우저 자동화 명령문(한 문장, 명확하고 간결하게)으로 변환해 주세요.
명령문은 반드시 직접적이고 구체적으로 작성하세요.

특별 규칙:
1. 특정 사이트명이 감지되면 해당 사이트로 직접 이동하는 명령으로 변환하세요.
2. "가다", "이동", "접속", "들어가다" 등의 동사가 포함되면 goto 액션으로 변환하세요.

사이트명 매핑 예시:
- "유튜브", "YouTube" → "https://youtube.com으로 이동"
- "네이버" → "https://naver.com으로 이동" 
- "구글" → "https://google.com으로 이동"
- "국가교통정보센터" → "https://www.its.go.kr로 이동"
- "깃허브" → "https://github.com으로 이동"
- "넷플릭스" → "https://netflix.com으로 이동"

입력: "{user_message}"

출력 예시:
- "메일함으로 가서 첫 번째 메일을 읽어줘" → "메일함으로 이동 후 첫 번째 메일 클릭"
- "로그인 버튼이 있으면 눌러줘" → "로그인 버튼 클릭"
- "검색창에 'AI' 입력하고 검색 버튼 클릭" → "검색창에 'AI' 입력 후 검색 버튼 클릭"
- "유튜브로 이동해줘" → "https://youtube.com으로 이동"
- "네이버 들어가서 뉴스 확인" → "https://naver.com으로 이동 후 뉴스 클릭"

명령문:
'''
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        messages=[{"role": "user", "content": refine_prompt}],
        max_tokens=150,
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
- For searching unknown websites, use "google_search" action with query parameter (LLM analyzes 7 results to select best match)

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
  {{"step": 1, "action": "google_search", "target": "search for unknown site", "reason": "Find best matching website from 7 Google search results", "query": "company name official website"}},
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
- For searching unknown websites, use "google_search" action with query parameter (LLM analyzes 7 results to select best match)
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
  "action": "click" | "fill" | "goto" | "google_search" | "hover" | "waitUntil" | "end",
  "selector": "<CSS selector>",
  "text": "optional text for matching",
  "value": "optional value",
  "url": "full URL for goto action",
  "query": "search query for google_search action",
  "condition": "optional condition selector",
  "timeout": 1000
}}
"""

def build_evaluation_prompt_with_image(goal: str, dom_summary: list, context: dict = None) -> str:
    context_info = ""
    if context:
        context_info = f"""
CONTEXT INFORMATION:
- Session ID: {context.get('sessionId', 'unknown')}
- Current Step: {context.get('step', 0)}
- Total Actions: {context.get('totalActions', 0)}
- Plan: {len(context.get('plan', []))} steps
- Last Action: {json.dumps(context.get('lastAction'), ensure_ascii=False) if context.get('lastAction') else 'None'}
"""

    return f"""
You are a browser automation evaluator with visual understanding. Analyze the current page state and determine the next course of action.

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

Goal: "{goal}"
{context_info}

Current DOM Summary:
{json.dumps(dom_summary, ensure_ascii=False, indent=2)}

EVALUATION TASKS:
1. **Goal Completion Check**: Is the goal "{goal}" already achieved on this page?
2. **Current Plan Validity**: Are the existing planned steps still relevant for this page?
3. **Next Action Decision**: What should be the next action?

RESPONSE FORMAT - Return ONLY ONE of these JSON formats:

**If goal is COMPLETED:**
{{
  "status": "completed",
  "reason": "Goal has been achieved because [specific reason]",
  "evidence": "Specific elements or content that prove completion"
}}

**If goal is NOT completed but need to REPLAN:**
{{
  "status": "replan",
  "reason": "Current plan is no longer valid because [specific reason]",
  "new_plan_needed": true
}}

**If goal is NOT completed and should CONTINUE with current plan:**
{{
  "status": "continue",
  "action": "click" | "fill" | "goto" | "hover" | "waitUntil",
  "selector": "<CSS selector>",
  "text": "optional text for matching",
  "value": "optional value",
  "url": "full URL for goto action",
  "reason": "Why this action is needed"
}}

Focus on accuracy and be conservative in completion assessment.
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
  "action": "click" | "fill" | "goto" | "google_search" | "hover" | "waitUntil" | "end",
  "selector": "<CSS selector>",
  "text": "optional text for matching",
  "value": "optional value",
  "url": "full URL for goto action",
  "query": "search query for google_search action",
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

            if payload.get("type") in ["dom_with_image", "dom_with_image_evaluation"]:
                is_evaluation_mode = payload.get("type") == "dom_with_image_evaluation" or payload.get("evaluationMode", False)
                
                if is_evaluation_mode:
                    logger.info("📊 DOM + 이미지 처리 시작 (평가 모드)")
                else:
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
                
                # 평가 모드 vs 실행 모드
                if is_evaluation_mode:
                    logger.info("📊 평가 모드: 목표 달성 여부 및 계획 유효성 검사")
                    
                    if image_data:
                        prompt = build_evaluation_prompt_with_image(goal, dom_summary, context)
                        response = await call_llm_with_image(prompt, image_data)
                    else:
                        prompt = f"Goal: {goal}\nEvaluate if goal is completed on current page.\nDOM: {json.dumps(dom_summary, ensure_ascii=False, indent=2)}"
                        response = await call_llm(prompt)
                else:
                    # 기존 실행 단계
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
                    result = json.loads(json_match.group())
                    
                    if is_evaluation_mode:
                        # 평가 결과 처리
                        status = result.get("status")
                        logger.info(f"📊 평가 결과: {status}")
                        
                        if status == "completed":
                            logger.info("🎯 목표 달성 완료!")
                            await websocket.send_text(json.dumps({
                                "type": "completed",
                                "reason": result.get("reason", "목표가 달성되었습니다."),
                                "evidence": result.get("evidence", "")
                            }))
                        elif status == "replan":
                            logger.info("🔄 계획 재수립 필요")
                            await websocket.send_text(json.dumps({
                                "type": "replan",
                                "reason": result.get("reason", "계획을 다시 수립해야 합니다."),
                                "new_plan_needed": True
                            }))
                        elif status == "continue":
                            logger.info("▶️ 계속 진행 - 다음 액션 실행")
                            action = clean_action(result)
                            logger.info(f"🚀 액션 전송: {action}")
                            await websocket.send_text(json.dumps({
                                "type": "action",
                                "step": step,
                                "action": action
                            }))
                    else:
                        # 기존 액션 처리
                        action = clean_action(result)
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