#!/usr/bin/env python3
"""
MCP FastAPI Server - Model Context Protocol 기반 웹 자동화 서버
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from mcp_server import MCPServer, MCPRequest, MCPResponse, MCPNotification
from dom_processor import DOMProcessor, PlanStep

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_fastapi")

app = FastAPI(title="MCP Web Automation Server", version="1.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 변수
connected_clients: List[WebSocket] = []
mcp_server: Optional[MCPServer] = None

# Pydantic 모델
class MCPRequestModel(BaseModel):
    id: str
    method: str
    params: Dict[str, Any]
    tool_type: str

class MCPResponseModel(BaseModel):
    id: str
    result: Dict[str, Any]
    error: Optional[str] = None
    timestamp: float

# Mock LLM 콜백
async def mock_llm_callback(prompt: str) -> str:
    """Mock LLM 콜백"""
    logger.info(f"🤖 Mock LLM 호출: {prompt[:100]}...")
    
    if "의도 분류" in prompt:
        return """
- 의도: action
- 목표: 네이버 메일함에 로그인하기
- 신뢰도: 0.9
- DOM 필요성: true
- 정제된 프롬프트: 네이버 메일함에 로그인하여 메일을 확인하세요
"""
    elif "단계별 계획을 수립" in prompt:
        return """
- 단계 1: input 이메일 입력 (로그인 정보 입력)
- 단계 2: input 비밀번호 입력 (로그인 정보 입력)
- 단계 3: click 로그인 버튼 (로그인 폼 제출)
- 단계 4: wait 페이지 로딩 (로그인 처리 대기)
- 단계 5: click 메일함 링크 (메일함으로 이동)
- 총 단계: 5
- 신뢰도: 0.85
"""
    elif "다음 액션을 생성" in prompt:
        return """
- 액션: input
- 대상: input[name='email']
- 이유: 로그인을 위해 이메일 주소를 입력해야 함
- 신뢰도: 0.95
"""
    elif "현재 페이지가 올바른지 판단" in prompt:
        return """
- 판단: 성공
- 신뢰도: 0.9
- 이유: 로그인 페이지에서 메인 페이지로 성공적으로 이동됨
"""
    else:
        return """
- 상태: success
- 신뢰도: 0.8
- 이유: 작업이 성공적으로 완료됨
"""

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    global mcp_server
    mcp_server = MCPServer(mock_llm_callback)
    logger.info("🚀 MCP FastAPI 서버 시작")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트"""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info(f"🔌 클라이언트 연결: {len(connected_clients)}개")
    
    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # MCP 요청 처리
            await handle_mcp_request(websocket, message)
            
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info(f"🔌 클라이언트 연결 해제: {len(connected_clients)}개 남음")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)

async def handle_mcp_request(websocket: WebSocket, message: Dict[str, Any]):
    """MCP 요청 처리"""
    try:
        message_type = message.get("type")
        
        if message_type == "mcp_request":
            # MCP 요청 처리
            await handle_mcp_tool_request(websocket, message)
        
        elif message_type == "dom_data":
            # DOM 데이터 수신
            await handle_dom_data(websocket, message)
        
        elif message_type == "action_complete":
            # 액션 실행 완료 신호
            await handle_action_complete(websocket, message)
        
        else:
            logger.warning(f"⚠️ 알 수 없는 메시지 타입: {message_type}")
            
    except Exception as e:
        logger.error(f"❌ MCP 요청 처리 오류: {e}")
        error_response = {
            "type": "mcp_error",
            "error": f"요청 처리 중 오류 발생: {str(e)}"
        }
        await websocket.send_text(json.dumps(error_response))

async def handle_mcp_tool_request(websocket: WebSocket, message: Dict[str, Any]):
    """MCP 도구 요청 처리"""
    try:
        request_data = message.get("request", {})
        
        # MCP 서버로 요청 전달
        response = await mcp_server.handle_request(request_data)
        
        # 응답을 클라이언트에게 전송
        response_message = {
            "type": "mcp_response",
            "response": {
                "id": response.id,
                "result": response.result,
                "error": response.error,
                "timestamp": response.timestamp
            }
        }
        
        await websocket.send_text(json.dumps(response_message))
        logger.info(f"📤 MCP 응답 전송: {request_data.get('method', 'unknown')}")
        
        # 특별한 요청에 대한 추가 처리
        if request_data.get("method") == "execute_step" and response.result.get("status") == "success":
            # 액션 실행 요청인 경우 Extension으로 전달
            action_data = response.result.get("action", {})
            if action_data:
                await send_action_to_extension(action_data)
        
    except Exception as e:
        logger.error(f"❌ MCP 도구 요청 처리 오류: {e}")
        error_response = {
            "type": "mcp_error",
            "error": f"도구 요청 처리 중 오류 발생: {str(e)}"
        }
        await websocket.send_text(json.dumps(error_response))

async def handle_dom_data(websocket: WebSocket, message: Dict[str, Any]):
    """DOM 데이터 처리"""
    dom_data = message.get("dom_data", [])
    logger.info(f"📦 DOM 데이터 수신: {len(dom_data)}개 요소")
    
    # DOM 데이터를 MCP 서버에 전달
    if mcp_server:
        dom_request = {
            "id": "dom_update",
            "method": "prepare",
            "params": {"dom_data": dom_data, "operation": "prepare"},
            "tool_type": "dom_analysis"
        }
        
        response = await mcp_server.handle_request(dom_request)
        logger.info(f"📦 DOM 처리 결과: {response.result.get('status', 'unknown')}")

async def handle_action_complete(websocket: WebSocket, message: Dict[str, Any]):
    """액션 실행 완료 처리"""
    action_result = message.get("action_result", {})
    logger.info(f"✅ 액션 실행 완료: {action_result.get('action', 'unknown')}")
    
    # 결과 평가
    if mcp_server:
        evaluation_request = {
            "id": "action_evaluation",
            "method": "evaluate_action",
            "params": {
                "goal": "네이버 메일함에 로그인해서 새 메일 확인해줘",
                "plan_step": {"action": "unknown", "target": "unknown", "reason": "unknown"},
                "action_result": action_result
            },
            "tool_type": "evaluation"
        }
        
        response = await mcp_server.handle_request(evaluation_request)
        logger.info(f"🔍 평가 결과: {response.result.get('status', 'unknown')}")

async def send_action_to_extension(action_data: Dict[str, Any]):
    """Extension으로 액션 전송"""
    message = {
        "type": "action_execution",
        "action": action_data,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    # 연결된 모든 클라이언트에게 전송
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(message))
            logger.info(f"📤 액션 전송: {action_data.get('action', 'unknown')} {action_data.get('target', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ 액션 전송 실패: {e}")

# REST API 엔드포인트
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "MCP Web Automation Server",
        "version": "1.0.0",
        "status": "running",
        "connected_clients": len(connected_clients)
    }

@app.get("/tools")
async def get_available_tools():
    """사용 가능한 도구 목록 반환"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP 서버가 초기화되지 않았습니다")
    
    tools = mcp_server.get_available_tools()
    return {
        "tools": tools,
        "count": len(tools)
    }

@app.post("/mcp/request")
async def mcp_request(request: MCPRequestModel):
    """MCP 요청 처리 (REST API)"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP 서버가 초기화되지 않았습니다")
    
    try:
        request_data = {
            "id": request.id,
            "method": request.method,
            "params": request.params,
            "tool_type": request.tool_type
        }
        
        response = await mcp_server.handle_request(request_data)
        
        return MCPResponseModel(
            id=response.id,
            result=response.result,
            error=response.error,
            timestamp=response.timestamp
        )
        
    except Exception as e:
        logger.error(f"❌ MCP REST 요청 처리 오류: {e}")
        raise HTTPException(status_code=500, detail=f"요청 처리 중 오류 발생: {str(e)}")

@app.get("/status")
async def get_status():
    """서버 상태 확인"""
    return {
        "server_status": "running",
        "connected_clients": len(connected_clients),
        "mcp_server_initialized": mcp_server is not None,
        "available_tools": len(mcp_server.get_available_tools()) if mcp_server else 0
    }

# 웹 자동화 워크플로우 엔드포인트
@app.post("/automation/start")
async def start_automation(request: Dict[str, Any]):
    """자동화 워크플로우 시작"""
    try:
        user_input = request.get("user_input", "")
        dom_data = request.get("dom_data", [])
        
        logger.info(f"🚀 자동화 시작: {user_input[:50]}...")
        
        # 1. DOM 분석
        dom_request = {
            "id": "automation_dom",
            "method": "prepare",
            "params": {"dom_data": dom_data, "operation": "prepare"},
            "tool_type": "dom_analysis"
        }
        
        dom_response = await mcp_server.handle_request(dom_request)
        
        # 2. 계획 수립
        planning_request = {
            "id": "automation_planning",
            "method": "create_plan",
            "params": {"user_input": user_input, "dom_data": dom_data},
            "tool_type": "planning"
        }
        
        planning_response = await mcp_server.handle_request(planning_request)
        
        # 3. 액션 실행 설정
        if planning_response.result['status'] == 'success':
            plan_steps = planning_response.result['planning_result'].get('plan_steps', [])
            
            action_request = {
                "id": "automation_action",
                "method": "set_plan",
                "params": {
                    "plan_steps": plan_steps,
                    "goal": planning_response.result['goal']
                },
                "tool_type": "action_execution"
            }
            
            action_response = await mcp_server.handle_request(action_request)
            
            return {
                "status": "automation_started",
                "dom_analysis": dom_response.result,
                "planning": planning_response.result,
                "action_setup": action_response.result,
                "next_action": "execute_step"
            }
        
        else:
            return {
                "status": "planning_failed",
                "error": planning_response.result.get("message", "계획 수립 실패")
            }
            
    except Exception as e:
        logger.error(f"❌ 자동화 시작 오류: {e}")
        raise HTTPException(status_code=500, detail=f"자동화 시작 중 오류 발생: {str(e)}")

@app.post("/automation/execute_step")
async def execute_automation_step():
    """자동화 단계 실행"""
    try:
        if not mcp_server:
            raise HTTPException(status_code=503, detail="MCP 서버가 초기화되지 않았습니다")
        
        # 다음 단계 실행
        step_request = {
            "id": "step_execution",
            "method": "execute_step",
            "params": {},
            "tool_type": "action_execution"
        }
        
        response = await mcp_server.handle_request(step_request)
        
        return {
            "status": "step_executed",
            "result": response.result,
            "next_action": "evaluate" if response.result.get("status") == "success" else "error"
        }
        
    except Exception as e:
        logger.error(f"❌ 단계 실행 오류: {e}")
        raise HTTPException(status_code=500, detail=f"단계 실행 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
