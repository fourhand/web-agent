from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AzureOpenAI
from starlette.websockets import WebSocketDisconnect
import os, json, re, logging, base64, random
from datetime import datetime
import asyncio
from urllib.parse import quote
from typing import Dict, List, Any, Optional, TypedDict

# LangGraph imports
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.schema import Document
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

# ============================
# State Management
# ============================
class AgentState(TypedDict):
    """LangGraph 상태 관리"""
    goal: str
    current_step: int
    total_steps: int
    plan: List[Dict[str, Any]]
    dom_elements: List[Dict[str, Any]]
    dom_vectorstore: Optional[Chroma]
    last_action: Optional[Dict[str, Any]]
    action_history: List[Dict[str, Any]]
    messages: List[Any]
    current_page_url: str
    status: str  # 'planning', 'executing', 'evaluating', 'completed', 'error'
    error_message: Optional[str]

# ============================
# LLM Setup
# ============================
def create_llm():
    """Azure OpenAI LLM 생성"""
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        openai_api_version="2024-02-15-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        temperature=0.1,
        max_tokens=1000
    )

def create_vision_llm():
    """Azure OpenAI Vision LLM 생성"""
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        openai_api_version="2024-02-15-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        temperature=0.1,
        max_tokens=1000
    )

# ============================
# DOM Vector Store Management
# ============================
def create_dom_vectorstore(dom_elements: List[Dict[str, Any]]) -> Chroma:
    """DOM 요소들을 VectorStore로 변환"""
    try:
        # DOM 요소를 텍스트로 변환
        documents = []
        for i, element in enumerate(dom_elements):
            text = f"Element {i}: {element.get('tag', '')} - {element.get('text', '')} - {element.get('class', '')} - {element.get('id', '')}"
            metadata = {
                "index": i,
                "tag": element.get("tag", ""),
                "text": element.get("text", ""),
                "class": element.get("class", ""),
                "id": element.get("id", ""),
                "selector": element.get("selector", ""),
                "is_clickable": element.get("is_clickable", False),
                "is_input": element.get("is_input", False)
            }
            documents.append(Document(page_content=text, metadata=metadata))
        
        # 텍스트 분할
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        split_docs = text_splitter.split_documents(documents)
        
        # VectorStore 생성
        embeddings = OpenAIEmbeddings(
            azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-ada-002"),
            openai_api_version="2024-02-15-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY")
        )
        
        vectorstore = Chroma.from_documents(
            documents=split_docs,
            embedding=embeddings,
            collection_name=f"dom_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        logger.info(f"✅ DOM VectorStore 생성 완료: {len(split_docs)}개 청크")
        return vectorstore
        
    except Exception as e:
        logger.error(f"❌ DOM VectorStore 생성 실패: {e}")
        return None

def search_dom_elements(vectorstore: Chroma, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """DOM 요소 검색"""
    try:
        results = vectorstore.similarity_search(query, k=k)
        elements = []
        for doc in results:
            elements.append(doc.metadata)
        return elements
    except Exception as e:
        logger.error(f"❌ DOM 검색 실패: {e}")
        return []

# ============================
# LangGraph Nodes
# ============================
def analyze_goal(state: AgentState) -> AgentState:
    """목표 분석 및 초기 계획 수립"""
    try:
        llm = create_llm()
        
        prompt = ChatPromptTemplate.from_template("""
당신은 웹 서핑 전문가입니다. 사용자의 목표를 분석하여 단계별 계획을 수립하세요.

목표: {goal}

다음 형식으로 JSON 배열을 반환하세요:
[
  {{
    "step": 1,
    "action": "goto|click|fill|wait|extract",
    "description": "이 단계에서 수행할 작업 설명",
    "expected_outcome": "예상 결과",
    "requirements": ["필요한 요소들"]
  }}
]

계획은 3-8단계로 구성하고, 각 단계는 구체적이고 실행 가능해야 합니다.
""")
        
        chain = prompt | llm | JsonOutputParser()
        plan = chain.invoke({"goal": state["goal"]})
        
        state["plan"] = plan
        state["total_steps"] = len(plan)
        state["status"] = "planning"
        state["current_step"] = 0
        
        logger.info(f"✅ 목표 분석 완료: {len(plan)}단계 계획 수립")
        return state
        
    except Exception as e:
        logger.error(f"❌ 목표 분석 실패: {e}")
        state["status"] = "error"
        state["error_message"] = f"목표 분석 실패: {str(e)}"
        return state

def create_dom_vectorstore_node(state: AgentState) -> AgentState:
    """DOM VectorStore 생성"""
    try:
        if not state["dom_elements"]:
            logger.warning("⚠️ DOM 요소가 없습니다")
            return state
        
        vectorstore = create_dom_vectorstore(state["dom_elements"])
        state["dom_vectorstore"] = vectorstore
        state["status"] = "executing"
        
        logger.info(f"✅ DOM VectorStore 생성 완료: {len(state['dom_elements'])}개 요소")
        return state
        
    except Exception as e:
        logger.error(f"❌ DOM VectorStore 생성 실패: {e}")
        state["status"] = "error"
        state["error_message"] = f"DOM VectorStore 생성 실패: {str(e)}"
        return state

def execute_action(state: AgentState) -> AgentState:
    """현재 단계 액션 실행"""
    try:
        if state["current_step"] >= len(state["plan"]):
            state["status"] = "completed"
            return state
        
        current_plan = state["plan"][state["current_step"]]
        action_type = current_plan["action"]
        
        # DOM 검색을 통한 요소 찾기
        if state["dom_vectorstore"] and action_type in ["click", "fill"]:
            query = current_plan["description"]
            elements = search_dom_elements(state["dom_vectorstore"], query)
            
            if elements:
                # 가장 적합한 요소 선택
                best_element = elements[0]
                action = {
                    "action": action_type,
                    "selector": best_element.get("selector", ""),
                    "text": best_element.get("text", ""),
                    "description": current_plan["description"],
                    "step": state["current_step"] + 1
                }
                
                state["last_action"] = action
                state["action_history"].append(action)
                state["current_step"] += 1
                
                logger.info(f"✅ 액션 실행: {action_type} - {current_plan['description']}")
            else:
                logger.warning(f"⚠️ 적합한 요소를 찾을 수 없음: {query}")
                state["status"] = "error"
                state["error_message"] = f"요소를 찾을 수 없음: {query}"
        else:
            # goto, wait 등의 액션
            action = {
                "action": action_type,
                "description": current_plan["description"],
                "step": state["current_step"] + 1
            }
            
            state["last_action"] = action
            state["action_history"].append(action)
            state["current_step"] += 1
        
        return state
        
    except Exception as e:
        logger.error(f"❌ 액션 실행 실패: {e}")
        state["status"] = "error"
        state["error_message"] = f"액션 실행 실패: {str(e)}"
        return state

def evaluate_progress(state: AgentState) -> AgentState:
    """진행 상황 평가"""
    try:
        llm = create_llm()
        
        progress_percentage = (state["current_step"] / state["total_steps"]) * 100 if state["total_steps"] > 0 else 0
        
        prompt = ChatPromptTemplate.from_template("""
현재 웹 자동화 진행 상황을 평가하세요.

목표: {goal}
현재 단계: {current_step}/{total_steps}
진행률: {progress_percentage:.1f}%
마지막 액션: {last_action}

평가 결과를 JSON으로 반환하세요:
{{
    "status": "continue|completed|error|replan",
    "reason": "평가 이유",
    "next_action": "다음에 할 일",
    "confidence": 0.0-1.0
}}
""")
        
        chain = prompt | llm | JsonOutputParser()
        evaluation = chain.invoke({
            "goal": state["goal"],
            "current_step": state["current_step"],
            "total_steps": state["total_steps"],
            "progress_percentage": progress_percentage,
            "last_action": json.dumps(state["last_action"], ensure_ascii=False) if state["last_action"] else "None"
        })
        
        if evaluation["status"] == "completed":
            state["status"] = "completed"
        elif evaluation["status"] == "replan":
            state["status"] = "planning"
            state["plan"] = []  # 재계획을 위해 초기화
        
        logger.info(f"✅ 진행 상황 평가: {evaluation['status']} - {evaluation['reason']}")
        return state
        
    except Exception as e:
        logger.error(f"❌ 진행 상황 평가 실패: {e}")
        state["status"] = "error"
        state["error_message"] = f"진행 상황 평가 실패: {str(e)}"
        return state

# ============================
# LangGraph Workflow
# ============================
def create_workflow() -> StateGraph:
    """LangGraph 워크플로우 생성"""
    
    # 상태 그래프 생성
    workflow = StateGraph(AgentState)
    
    # 노드 추가
    workflow.add_node("analyze_goal", analyze_goal)
    workflow.add_node("create_dom_vectorstore", create_dom_vectorstore_node)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("evaluate_progress", evaluate_progress)
    
    # 엣지 정의
    workflow.set_entry_point("analyze_goal")
    
    # 조건부 라우팅
    def route_after_analysis(state: AgentState) -> str:
        # DOM 요소가 없으면 대기
        if not state.get("dom_elements") or len(state["dom_elements"]) == 0:
            return END
        if state["status"] == "error":
            return END
        elif state["dom_elements"]:
            return "create_dom_vectorstore"
        else:
            return "execute_action"
    
    def route_after_vectorstore(state: AgentState) -> str:
        if state["status"] == "error":
            return END
        return "execute_action"
    
    def route_after_action(state: AgentState) -> str:
        if state["status"] == "error":
            return END
        elif state["status"] == "completed":
            return END
        elif state["current_step"] >= state["total_steps"]:
            return "evaluate_progress"
        else:
            return "execute_action"
    
    def route_after_evaluation(state: AgentState) -> str:
        if state["status"] == "error":
            return END
        elif state["status"] == "completed":
            return END
        elif state["status"] == "planning":
            return "analyze_goal"
        else:
            return "execute_action"
    
    # 엣지 연결
    workflow.add_conditional_edges("analyze_goal", route_after_analysis)
    workflow.add_conditional_edges("create_dom_vectorstore", route_after_vectorstore)
    workflow.add_conditional_edges("execute_action", route_after_action)
    workflow.add_conditional_edges("evaluate_progress", route_after_evaluation)
    
    return workflow

# ============================
# FastAPI App
# ============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 워크플로우 생성
workflow = create_workflow()
memory = MemorySaver()
app_graph = workflow.compile()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 LangGraph WebSocket 연결 수락됨")
    
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                logger.info(f"📨 메시지 수신: {payload.get('type')}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 파싱 실패: {e}")
                continue
            
            if payload.get("type") == "init":
                # 새로운 작업 시작
                user_goal = payload["message"]
                logger.info(f"🆕 새 목표: {user_goal}")
                
                # 초기 상태 설정
                initial_state = AgentState(
                    goal=user_goal,
                    current_step=0,
                    total_steps=0,
                    plan=[],
                    dom_elements=[],
                    dom_vectorstore=None,
                    last_action=None,
                    action_history=[],
                    messages=[],
                    current_page_url="",
                    status="planning",
                    error_message=None
                )
                
                # 워크플로우 실행
                try:
                    result = await app_graph.ainvoke(initial_state, config={"configurable": {"thread_id": "default"}})
                    
                    # 결과 전송
                    await websocket.send_text(json.dumps({
                        "type": "workflow_result",
                        "status": result["status"],
                        "plan": result["plan"],
                        "action_history": result["action_history"],
                        "current_step": result["current_step"],
                        "total_steps": result["total_steps"],
                        "error_message": result.get("error_message")
                    }, ensure_ascii=False))
                    
                except Exception as e:
                    logger.error(f"❌ 워크플로우 실행 실패: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": f"워크플로우 실행 실패: {str(e)}"
                    }))
            
            elif payload.get("type") == "dom_with_image":
                # DOM 정보 업데이트
                dom_elements = payload.get("dom", [])
                logger.info(f"📊 DOM 업데이트: {len(dom_elements)}개 요소")
                
                # 현재 상태에 DOM 추가
                # 실제로는 체크포인트에서 상태를 복원해야 함
                await websocket.send_text(json.dumps({
                    "type": "dom_updated",
                    "message": f"DOM {len(dom_elements)}개 요소 업데이트됨"
                }))
            
            elif payload.get("type") == "execute_action":
                # 특정 액션 실행
                action = payload.get("action")
                if action:
                    # 체크포인트에서 상태 복원 후 액션 실행
                    await websocket.send_text(json.dumps({
                        "type": "action_executed",
                        "action": action
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
    uvicorn.run(app, host="0.0.0.0", port=8001)
