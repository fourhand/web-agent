#!/usr/bin/env python3
"""
Model Context Protocol (MCP) Server
AI 에이전트와 웹 자동화 도구 간의 표준화된 통신
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import uuid

from dom_processor import DOMProcessor, PlanStep
from graph_line_executor import GraphLineExecutor

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

class MCPMessageType(Enum):
    """MCP 메시지 타입"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"

class MCPToolType(Enum):
    """MCP 도구 타입"""
    DOM_ANALYSIS = "dom_analysis"
    ACTION_EXECUTION = "action_execution"
    PLANNING = "planning"
    EVALUATION = "evaluation"
    NAVIGATION = "navigation"

@dataclass
class MCPRequest:
    """MCP 요청"""
    id: str
    method: str
    params: Dict[str, Any]
    tool_type: MCPToolType
    timestamp: float

@dataclass
class MCPResponse:
    """MCP 응답"""
    id: str
    result: Dict[str, Any]
    error: Optional[str] = None
    timestamp: float = None

@dataclass
class MCPNotification:
    """MCP 알림"""
    method: str
    params: Dict[str, Any]
    tool_type: MCPToolType
    timestamp: float

class MCPTool:
    """MCP 도구 기본 클래스"""
    
    def __init__(self, tool_type: MCPToolType):
        self.tool_type = tool_type
        self.name = tool_type.value
        self.description = f"{tool_type.value} 도구"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """도구 실행 (하위 클래스에서 구현)"""
        raise NotImplementedError

class DOMAnalysisTool(MCPTool):
    """DOM 분석 도구"""
    
    def __init__(self, dom_processor: DOMProcessor):
        super().__init__(MCPToolType.DOM_ANALYSIS)
        self.dom_processor = dom_processor
        self.description = "DOM 구조 분석 및 텍스처 추출"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """DOM 분석 실행"""
        try:
            dom_data = params.get("dom_data", [])
            operation = params.get("operation", "prepare")
            
            if operation == "prepare":
                self.dom_processor.prepere_dom(dom_data)
                return {
                    "status": "success",
                    "message": f"DOM 준비 완료: {len(dom_data)}개 요소",
                    "processed_elements": len(dom_data),
                    "textures_count": len(self.dom_processor.dom_textures)
                }
            
            elif operation == "get_context":
                context = self.dom_processor._get_page_context()
                return {
                    "status": "success",
                    "context": context,
                    "context_length": len(context)
                }
            
            elif operation == "get_action_prompt":
                goal = params.get("goal", "")
                plan_step = params.get("plan_step", {})
                max_elements = params.get("max_elements", 20)
                
                prompt = self.dom_processor.get_action_generation_prompt_data(
                    goal, plan_step, max_elements
                )
                
                return {
                    "status": "success",
                    "prompt": prompt,
                    "prompt_length": len(prompt)
                }
            
            elif operation == "get_evaluation_prompt":
                goal = params.get("goal", "")
                plan_step = params.get("plan_step", {})
                
                prompt = self.dom_processor.get_page_evaluation_prompt(goal, plan_step)
                
                return {
                    "status": "success",
                    "prompt": prompt,
                    "prompt_length": len(prompt)
                }
            
            else:
                return {
                    "status": "error",
                    "message": f"알 수 없는 작업: {operation}"
                }
                
        except Exception as e:
            logger.error(f"❌ DOM 분석 오류: {e}")
            return {
                "status": "error",
                "message": f"DOM 분석 중 오류 발생: {str(e)}"
            }

class PlanningTool(MCPTool):
    """계획 수립 도구"""
    
    def __init__(self, graph_line_executor: GraphLineExecutor):
        super().__init__(MCPToolType.PLANNING)
        self.graph_line_executor = graph_line_executor
        self.description = "목표 기반 계획 수립"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """계획 수립 실행"""
        try:
            user_input = params.get("user_input", "")
            dom_data = params.get("dom_data")
            
            # Graph Line Executor로 계획 수립
            result = await self.graph_line_executor.execute_graph_line(user_input, dom_data)
            
            return {
                "status": "success",
                "planning_result": result,
                "goal": result.get("goal", ""),
                "total_steps": result.get("total_steps", 0),
                "next_action": result.get("next_action", "")
            }
            
        except Exception as e:
            logger.error(f"❌ 계획 수립 오류: {e}")
            return {
                "status": "error",
                "message": f"계획 수립 중 오류 발생: {str(e)}"
            }

class ActionExecutionTool(MCPTool):
    """액션 실행 도구"""
    
    def __init__(self, dom_processor: DOMProcessor):
        super().__init__(MCPToolType.ACTION_EXECUTION)
        self.dom_processor = dom_processor
        self.description = "웹 액션 실행 및 제어"
        self.current_plan: List[PlanStep] = []
        self.current_step_index = 0
        self.goal = ""
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """액션 실행"""
        try:
            operation = params.get("operation", "execute")
            
            if operation == "set_plan":
                # 계획 설정
                self.current_plan = params.get("plan_steps", [])
                self.current_step_index = 0
                self.goal = params.get("goal", "")
                
                return {
                    "status": "success",
                    "message": f"계획 설정 완료: {len(self.current_plan)}단계",
                    "total_steps": len(self.current_plan)
                }
            
            elif operation == "execute_step":
                # 단계 실행
                if self.current_step_index >= len(self.current_plan):
                    return {
                        "status": "completed",
                        "message": "모든 단계 완료"
                    }
                
                current_step = self.current_plan[self.current_step_index]
                
                # 액션 생성
                action_prompt = self.dom_processor.get_action_generation_prompt_data(
                    self.goal, current_step
                )
                
                # 실제로는 LLM 호출
                action_result = {
                    "action": current_step["action"],
                    "target": current_step["target"],
                    "reason": current_step["reason"],
                    "step_number": self.current_step_index + 1,
                    "total_steps": len(self.current_plan)
                }
                
                self.current_step_index += 1
                
                return {
                    "status": "success",
                    "action": action_result,
                    "current_step": self.current_step_index,
                    "remaining_steps": len(self.current_plan) - self.current_step_index
                }
            
            elif operation == "get_status":
                return {
                    "status": "success",
                    "current_step": self.current_step_index,
                    "total_steps": len(self.current_plan),
                    "goal": self.goal,
                    "progress": (self.current_step_index / len(self.current_plan)) * 100 if self.current_plan else 0
                }
            
            else:
                return {
                    "status": "error",
                    "message": f"알 수 없는 작업: {operation}"
                }
                
        except Exception as e:
            logger.error(f"❌ 액션 실행 오류: {e}")
            return {
                "status": "error",
                "message": f"액션 실행 중 오류 발생: {str(e)}"
            }

class EvaluationTool(MCPTool):
    """결과 평가 도구"""
    
    def __init__(self, dom_processor: DOMProcessor):
        super().__init__(MCPToolType.EVALUATION)
        self.dom_processor = dom_processor
        self.description = "액션 결과 및 페이지 상태 평가"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """결과 평가 실행"""
        try:
            operation = params.get("operation", "evaluate")
            
            if operation == "evaluate_action":
                goal = params.get("goal", "")
                plan_step = params.get("plan_step", {})
                action_result = params.get("action_result", {})
                
                # 페이지 평가 프롬프트 생성
                evaluation_prompt = self.dom_processor.get_page_evaluation_prompt(goal, plan_step)
                
                # 실제로는 LLM 호출
                evaluation_result = {
                    "judgment": "success",
                    "confidence": 0.85,
                    "reason": "액션이 성공적으로 실행됨",
                    "next_action": "continue"
                }
                
                return {
                    "status": "success",
                    "evaluation": evaluation_result,
                    "prompt_used": evaluation_prompt[:200] + "..." if len(evaluation_prompt) > 200 else evaluation_prompt
                }
            
            elif operation == "check_goal":
                goal = params.get("goal", "")
                current_state = params.get("current_state", {})
                
                # 목표 달성 확인
                goal_achieved = "로그인" in goal and "메인" in current_state.get("page_title", "")
                
                return {
                    "status": "success",
                    "goal_achieved": goal_achieved,
                    "confidence": 0.9 if goal_achieved else 0.3,
                    "reason": "목표 달성 확인 완료"
                }
            
            else:
                return {
                    "status": "error",
                    "message": f"알 수 없는 작업: {operation}"
                }
                
        except Exception as e:
            logger.error(f"❌ 결과 평가 오류: {e}")
            return {
                "status": "error",
                "message": f"결과 평가 중 오류 발생: {str(e)}"
            }

class MCPServer:
    """MCP 서버"""
    
    def __init__(self, llm_callback: Callable):
        self.llm_callback = llm_callback
        self.dom_processor = DOMProcessor()
        self.graph_line_executor = GraphLineExecutor(llm_callback)
        
        # 도구 등록
        self.tools: Dict[str, MCPTool] = {
            "dom_analysis": DOMAnalysisTool(self.dom_processor),
            "planning": PlanningTool(self.graph_line_executor),
            "action_execution": ActionExecutionTool(self.dom_processor),
            "evaluation": EvaluationTool(self.dom_processor)
        }
        
        logger.info("🚀 MCP 서버 초기화 완료")
    
    async def handle_request(self, request_data: Dict[str, Any]) -> MCPResponse:
        """MCP 요청 처리"""
        try:
            request_id = request_data.get("id", str(uuid.uuid4()))
            method = request_data.get("method", "")
            params = request_data.get("params", {})
            tool_type = request_data.get("tool_type", "")
            
            logger.info(f"📨 MCP 요청: {method} ({tool_type})")
            
            # 도구 찾기
            tool = self.tools.get(tool_type)
            if not tool:
                return MCPResponse(
                    id=request_id,
                    result={},
                    error=f"알 수 없는 도구: {tool_type}",
                    timestamp=asyncio.get_event_loop().time()
                )
            
            # 도구 실행
            result = await tool.execute(params)
            
            return MCPResponse(
                id=request_id,
                result=result,
                timestamp=asyncio.get_event_loop().time()
            )
            
        except Exception as e:
            logger.error(f"❌ MCP 요청 처리 오류: {e}")
            return MCPResponse(
                id=request_data.get("id", str(uuid.uuid4())),
                result={},
                error=f"요청 처리 중 오류 발생: {str(e)}",
                timestamp=asyncio.get_event_loop().time()
            )
    
    async def send_notification(self, method: str, params: Dict[str, Any], tool_type: str) -> MCPNotification:
        """MCP 알림 전송"""
        notification = MCPNotification(
            method=method,
            params=params,
            tool_type=MCPToolType(tool_type),
            timestamp=asyncio.get_event_loop().time()
        )
        
        logger.info(f"📢 MCP 알림: {method} ({tool_type})")
        return notification
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """사용 가능한 도구 목록 반환"""
        return [
            {
                "name": tool.name,
                "type": tool.tool_type.value,
                "description": tool.description
            }
            for tool in self.tools.values()
        ]

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
    else:
        return """
- 상태: success
- 신뢰도: 0.8
- 이유: 작업이 성공적으로 완료됨
"""

# 테스트 함수
async def test_mcp_server():
    """MCP 서버 테스트"""
    logger.info("🧪 MCP 서버 테스트 시작")
    
    # MCP 서버 초기화
    mcp_server = MCPServer(mock_llm_callback)
    
    # 1. 사용 가능한 도구 확인
    tools = mcp_server.get_available_tools()
    logger.info(f"📋 사용 가능한 도구: {len(tools)}개")
    for tool in tools:
        logger.info(f"   - {tool['name']}: {tool['description']}")
    
    # 2. DOM 분석 테스트
    test_dom = [
        {"tag": "button", "text": "로그인", "class": "login-btn"},
        {"tag": "input", "text": "", "class": "email-input"},
        {"tag": "input", "text": "", "class": "password-input"}
    ]
    
    dom_request = {
        "id": "test-1",
        "method": "prepare",
        "params": {"dom_data": test_dom, "operation": "prepare"},
        "tool_type": "dom_analysis"
    }
    
    dom_response = await mcp_server.handle_request(dom_request)
    logger.info(f"📦 DOM 분석 결과: {dom_response.result['status']}")
    
    # 3. 계획 수립 테스트
    planning_request = {
        "id": "test-2",
        "method": "create_plan",
        "params": {
            "user_input": "네이버 메일함에 로그인해서 새 메일 확인해줘",
            "dom_data": test_dom
        },
        "tool_type": "planning"
    }
    
    planning_response = await mcp_server.handle_request(planning_request)
    logger.info(f"📋 계획 수립 결과: {planning_response.result['status']}")
    
    # 4. 액션 실행 테스트
    if planning_response.result['status'] == 'success':
        plan_steps = planning_response.result['planning_result'].get('plan_steps', [])
        
        action_request = {
            "id": "test-3",
            "method": "set_plan",
            "params": {
                "plan_steps": plan_steps,
                "goal": planning_response.result['goal']
            },
            "tool_type": "action_execution"
        }
        
        action_response = await mcp_server.handle_request(action_request)
        logger.info(f"🚀 액션 실행 설정: {action_response.result['status']}")
    
    logger.info("✅ MCP 서버 테스트 완료!")

if __name__ == "__main__":
    asyncio.run(test_mcp_server())
