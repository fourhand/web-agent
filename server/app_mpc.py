#!/usr/bin/env python3
"""
Action MPC Server - 액션 실행 및 Extension 통신 담당
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from dom_processor import DOMProcessor, PlanStep
from graph_line_executor import GraphLineExecutor

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Action MPC Server", version="1.0.0")

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
graph_line_executor: Optional[GraphLineExecutor] = None
dom_processor: Optional[DOMProcessor] = None

# Mock LLM 콜백 (실제로는 Azure OpenAI 연결)
async def mock_llm_callback(prompt: str) -> str:
    """Mock LLM 콜백 함수"""
    logger.info(f"🤖 Mock LLM 호출: {prompt[:100]}...")
    
    # 프롬프트 내용에 따라 다른 응답 생성
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
- 상태: unknown
- 신뢰도: 0.5
- 이유: 알 수 없는 요청
"""


class ActionMPC:
    """액션 MPC 클래스"""
    
    def __init__(self):
        self.current_plan: List[PlanStep] = []
        self.current_step_index = 0
        self.goal = ""
        self.dom_processor = DOMProcessor()
        self.execution_state = "idle"
        
    async def execute_plan(self, planning_result: Dict[str, Any], dom_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """MPC 기반 계획 실행"""
        try:
            logger.info("🚀 액션 MPC 실행 시작")
            
            # 계획 데이터 설정
            self.current_plan = planning_result.get("plan_steps", [])
            self.current_step_index = 0
            self.goal = planning_result.get("goal", "")
            
            if not self.current_plan:
                return {
                    "status": "error",
                    "message": "실행할 계획이 없습니다"
                }
            
            # DOM 처리
            if dom_data:
                self.dom_processor.prepere_dom(dom_data)
                logger.info(f"📦 DOM 처리 완료: {len(dom_data)}개 요소")
            
            # MPC 실행 루프
            max_iterations = 50  # 무한 루프 방지
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"🔄 MPC 반복 {iteration}")
                
                # 1. 현재 상태 분석
                current_state = await self._analyze_current_state()
                
                # 2. 목표 달성 여부 확인
                if await self._check_goal_achievement():
                    return self._create_completion_result()
                
                # 3. MPC 예측 및 최적 액션 선택
                optimal_action = await self._mpc_predict_and_select_action(current_state)
                
                if not optimal_action:
                    logger.warning("⚠️ 최적 액션을 찾을 수 없음")
                    return self._create_replan_result()
                
                # 4. 액션 실행
                execution_result = await self._execute_optimal_action(optimal_action)
                
                # 5. 결과 평가 및 피드백
                feedback = await self._evaluate_and_feedback(optimal_action, execution_result)
                
                # 6. MPC 상태 업데이트
                await self._update_mpc_state(feedback)
                
                # 7. 종료 조건 확인
                if feedback["should_terminate"]:
                    if feedback["reason"] == "success":
                        return self._create_completion_result()
                    elif feedback["reason"] == "replan":
                        return self._create_replan_result()
                    elif feedback["reason"] == "wait":
                        return self._create_wait_result(feedback)
            
            logger.warning("⚠️ 최대 반복 횟수 도달")
            return self._create_replan_result()
            
        except Exception as e:
            logger.error(f"❌ 액션 MPC 실행 중 오류: {e}")
            return {
                "status": "error",
                "message": f"실행 중 오류 발생: {str(e)}"
            }
    
    async def _generate_action(self, plan_step: PlanStep) -> Dict[str, Any]:
        """액션 생성"""
        logger.info(f"🎯 액션 생성: {plan_step['action']} {plan_step['target']}")
        
        # DOM Processor를 사용하여 액션 생성 프롬프트 생성
        action_prompt = self.dom_processor.get_action_generation_prompt_data(
            self.goal, plan_step
        )
        
        # LLM에게 액션 실행 요청
        response = await mock_llm_callback(action_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        return {
            "action": result.get('액션', plan_step['action']),
            "target": result.get('대상', plan_step['target']),
            "reason": result.get('이유', plan_step['reason']),
            "confidence": float(result.get('신뢰도', 0.8)),
            "step_number": self.current_step_index + 1,
            "total_steps": len(self.current_plan)
        }
    
    async def _send_action_to_extension(self, action_result: Dict[str, Any]):
        """Extension으로 액션 전송"""
        message = {
            "type": "action_execution",
            "action": action_result,
            "goal": self.goal,
            "progress": {
                "current_step": action_result["step_number"],
                "total_steps": action_result["total_steps"],
                "percentage": (action_result["step_number"] / action_result["total_steps"]) * 100
            }
        }
        
        # 연결된 모든 클라이언트에게 전송
        for client in connected_clients:
            try:
                await client.send_text(json.dumps(message))
                logger.info(f"📤 액션 전송: {action_result['action']} {action_result['target']}")
            except Exception as e:
                logger.error(f"❌ 액션 전송 실패: {e}")
    
    async def _wait_for_execution(self) -> Dict[str, Any]:
        """Extension에서 실행 완료 대기"""
        # 실제로는 WebSocket을 통해 Extension에서 실행 완료 신호를 받아야 함
        # 여기서는 Mock으로 처리
        await asyncio.sleep(2)  # 2초 대기
        
        return {
            "success": True,
            "message": "액션 실행 완료",
            "timestamp": asyncio.get_event_loop().time()
        }
    
    async def _evaluate_result(self, plan_step: PlanStep, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """결과 평가"""
        logger.info(f"🔍 결과 평가: {plan_step['action']} {plan_step['target']}")
        
        # DOM Processor를 사용하여 페이지 평가 프롬프트 생성
        evaluation_prompt = self.dom_processor.get_page_evaluation_prompt(
            self.goal, plan_step
        )
        
        # LLM에게 평가 요청
        response = await mock_llm_callback(evaluation_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        judgment = result.get('판단', '확인 불가')
        confidence = float(result.get('신뢰도', 0.5))
        reason = result.get('이유', '평가 근거 없음')
        
        # 다음 액션 결정
        if judgment == '성공':
            next_action = 'continue'
        elif judgment == '실패':
            next_action = 'replan'
        elif judgment == '로그인 필요':
            next_action = 'wait'
        else:
            next_action = 'replan'
        
        return {
            "judgment": judgment,
            "confidence": confidence,
            "reason": reason,
            "next_action": next_action
        }
    
    def _create_completion_result(self) -> Dict[str, Any]:
        """완료 결과 생성"""
        return {
            "status": "completed",
            "message": f"목표 달성 완료: {self.goal}",
            "total_steps": len(self.current_plan),
            "executed_steps": self.current_step_index,
            "progress": 100.0
        }
    
    def _create_replan_result(self) -> Dict[str, Any]:
        """재계획 결과 생성"""
        return {
            "status": "replanning",
            "message": "계획 재수립이 필요합니다",
            "current_step": self.current_step_index,
            "total_steps": len(self.current_plan)
        }
    
    async def _analyze_current_state(self) -> Dict[str, Any]:
        """현재 상태 분석"""
        logger.info("🔍 현재 상태 분석")
        
        # DOM 컨텍스트 가져오기
        dom_context = self.dom_processor._get_page_context()
        
        return {
            "dom_context": dom_context,
            "current_step": self.current_step_index,
            "total_steps": len(self.current_plan),
            "goal": self.goal,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    async def _check_goal_achievement(self) -> bool:
        """목표 달성 여부 확인"""
        logger.info("🎯 목표 달성 확인")
        
        # DOM Processor를 사용하여 목표 달성 평가
        evaluation_prompt = self.dom_processor.get_page_evaluation_prompt(
            self.goal, 
            {"action": "goal_check", "target": "goal_achievement", "reason": "목표 달성 확인"}
        )
        
        response = await mock_llm_callback(evaluation_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        for line in lines:
            if '판단:' in line:
                judgment = line.split(':', 1)[1].strip()
                return judgment == '성공'
        
        return False
    
    async def _mpc_predict_and_select_action(self, current_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """MPC 예측 및 최적 액션 선택"""
        logger.info("🧠 MPC 예측 및 액션 선택")
        
        # 1. 가능한 액션 후보들 생성
        action_candidates = await self._generate_action_candidates(current_state)
        
        if not action_candidates:
            return None
        
        # 2. 각 액션의 예상 결과 시뮬레이션
        predictions = []
        for candidate in action_candidates:
            prediction = await self._simulate_action_result(candidate, current_state)
            predictions.append({
                "action": candidate,
                "prediction": prediction,
                "expected_reward": prediction["expected_reward"],
                "confidence": prediction["confidence"]
            })
        
        # 3. 최적 액션 선택 (예상 보상 최대화)
        if predictions:
            optimal_prediction = max(predictions, key=lambda x: x["expected_reward"])
            logger.info(f"🎯 최적 액션 선택: {optimal_prediction['action']['action']} (보상: {optimal_prediction['expected_reward']:.2f})")
            return optimal_prediction["action"]
        
        return None
    
    async def _generate_action_candidates(self, current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """액션 후보 생성"""
        candidates = []
        
        # 1. 원래 계획에서 다음 액션
        if self.current_step_index < len(self.current_plan):
            plan_action = self.current_plan[self.current_step_index]
            candidates.append({
                "action": plan_action["action"],
                "target": plan_action["target"],
                "reason": plan_action["reason"],
                "source": "original_plan",
                "priority": 1.0
            })
        
        # 2. DOM 기반 대안 액션들
        dom_actions = await self._generate_dom_based_actions(current_state)
        candidates.extend(dom_actions)
        
        # 3. 목표 기반 대안 액션들
        goal_actions = await self._generate_goal_based_actions(current_state)
        candidates.extend(goal_actions)
        
        return candidates
    
    async def _generate_dom_based_actions(self, current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """DOM 기반 액션 생성"""
        actions = []
        
        # DOM Processor를 사용하여 DOM 기반 액션 생성
        action_prompt = self.dom_processor.get_action_generation_prompt_data(
            self.goal,
            {"action": "explore", "target": "dom_elements", "reason": "DOM 탐색"}
        )
        
        response = await mock_llm_callback(action_prompt)
        
        # 응답에서 액션 추출 (실제로는 더 정교한 파싱 필요)
        actions.append({
            "action": "click",
            "target": "가장 관련성 높은 요소",
            "reason": "DOM 기반 탐색",
            "source": "dom_analysis",
            "priority": 0.8
        })
        
        return actions
    
    async def _generate_goal_based_actions(self, current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """목표 기반 액션 생성"""
        actions = []
        
        # 목표에 따라 일반적인 액션 패턴 생성
        if "로그인" in self.goal:
            actions.extend([
                {
                    "action": "input",
                    "target": "이메일/아이디 입력",
                    "reason": "로그인 정보 입력",
                    "source": "goal_pattern",
                    "priority": 0.9
                },
                {
                    "action": "input", 
                    "target": "비밀번호 입력",
                    "reason": "로그인 정보 입력",
                    "source": "goal_pattern",
                    "priority": 0.9
                },
                {
                    "action": "click",
                    "target": "로그인 버튼",
                    "reason": "로그인 제출",
                    "source": "goal_pattern",
                    "priority": 0.95
                }
            ])
        
        return actions
    
    async def _simulate_action_result(self, action: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
        """액션 결과 시뮬레이션"""
        logger.info(f"🎮 액션 시뮬레이션: {action['action']} {action['target']}")
        
        # LLM을 사용하여 액션 결과 예측
        simulation_prompt = f"""
다음 액션의 예상 결과를 시뮬레이션해주세요:

**현재 상태**: {current_state['dom_context'][:200]}...
**목표**: {self.goal}
**실행할 액션**: {action['action']} {action['target']}
**액션 이유**: {action['reason']}

**예측해야 할 항목**:
1. 예상 성공 확률 (0.0-1.0)
2. 예상 보상 (목표 달성에 기여하는 정도, 0.0-1.0)
3. 예상 위험도 (0.0-1.0)
4. 예상 소요 시간 (초)
5. 예상 다음 상태 설명

**응답 형식**:
- 성공 확률: 0.85
- 예상 보상: 0.7
- 위험도: 0.1
- 소요 시간: 2
- 다음 상태: 로그인 페이지에서 메인 페이지로 이동
"""
        
        response = await mock_llm_callback(simulation_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        # 예상 보상 계산
        success_prob = float(result.get('성공 확률', 0.5))
        expected_reward = float(result.get('예상 보상', 0.5))
        risk = float(result.get('위험도', 0.5))
        
        # 최종 예상 보상 = 성공확률 * 보상 - 위험도
        final_reward = success_prob * expected_reward - risk
        
        return {
            "success_probability": success_prob,
            "expected_reward": final_reward,
            "risk": risk,
            "estimated_time": float(result.get('소요 시간', 2)),
            "next_state": result.get('다음 상태', '알 수 없음'),
            "confidence": success_prob * 0.8 + (1 - risk) * 0.2  # 신뢰도 계산
        }
    
    async def _execute_optimal_action(self, optimal_action: Dict[str, Any]) -> Dict[str, Any]:
        """최적 액션 실행"""
        logger.info(f"🚀 최적 액션 실행: {optimal_action['action']} {optimal_action['target']}")
        
        # Extension으로 액션 전송
        action_message = {
            "action": optimal_action["action"],
            "target": optimal_action["target"],
            "reason": optimal_action["reason"],
            "confidence": optimal_action.get("confidence", 0.8),
            "step_number": self.current_step_index + 1,
            "total_steps": len(self.current_plan),
            "source": optimal_action.get("source", "mpc")
        }
        
        await self._send_action_to_extension(action_message)
        
        # Extension에서 실행 완료 대기
        execution_result = await self._wait_for_execution()
        
        return execution_result
    
    async def _evaluate_and_feedback(self, action: Dict[str, Any], execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """결과 평가 및 피드백"""
        logger.info(f"🔍 결과 평가: {action['action']} {action['target']}")
        
        # DOM Processor를 사용하여 페이지 평가
        evaluation_prompt = self.dom_processor.get_page_evaluation_prompt(
            self.goal, 
            {"action": action["action"], "target": action["target"], "reason": action["reason"]}
        )
        
        response = await mock_llm_callback(evaluation_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        judgment = result.get('판단', '확인 불가')
        confidence = float(result.get('신뢰도', 0.5))
        reason = result.get('이유', '평가 근거 없음')
        
        # 피드백 결정
        if judgment == '성공':
            should_terminate = False
            termination_reason = None
            self.current_step_index += 1
        elif judgment == '실패':
            should_terminate = True
            termination_reason = 'replan'
        elif judgment == '로그인 필요':
            should_terminate = True
            termination_reason = 'wait'
        else:
            should_terminate = True
            termination_reason = 'replan'
        
        return {
            "judgment": judgment,
            "confidence": confidence,
            "reason": reason,
            "should_terminate": should_terminate,
            "reason": termination_reason,
            "action": action,
            "execution_result": execution_result
        }
    
    async def _update_mpc_state(self, feedback: Dict[str, Any]):
        """MPC 상태 업데이트"""
        logger.info(f"🔄 MPC 상태 업데이트: {feedback['judgment']}")
        
        # 피드백을 바탕으로 MPC 상태 업데이트
        # 실제로는 더 정교한 상태 추적이 필요
        self.execution_state = "executing"
        
        # 성공한 액션은 계획에서 제거하거나 마킹
        if feedback["judgment"] == "성공":
            logger.info("✅ 액션 성공 - 다음 단계로 진행")
    
    def _create_wait_result(self, evaluation_result: Dict[str, Any]) -> Dict[str, Any]:
        """대기 결과 생성"""
        return {
            "status": "waiting",
            "message": evaluation_result["reason"],
            "requires_user_action": True
        }


# 전역 Action MPC 인스턴스
action_mpc = ActionMPC()


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    global graph_line_executor, dom_processor
    graph_line_executor = GraphLineExecutor(mock_llm_callback)
    dom_processor = DOMProcessor()
    logger.info("🚀 Action MPC Server 시작")


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
            
            # 메시지 타입에 따른 처리
            await handle_message(websocket, message)
            
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info(f"🔌 클라이언트 연결 해제: {len(connected_clients)}개 남음")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)


async def handle_message(websocket: WebSocket, message: Dict[str, Any]):
    """메시지 처리"""
    message_type = message.get("type")
    
    if message_type == "graph_line_request":
        # Graph Line Executor로 계획 수립 요청
        await handle_graph_line_request(websocket, message)
    
    elif message_type == "action_execution_complete":
        # Extension에서 액션 실행 완료 신호
        await handle_action_complete(websocket, message)
    
    elif message_type == "dom_data":
        # DOM 데이터 수신
        await handle_dom_data(websocket, message)
    
    else:
        logger.warning(f"⚠️ 알 수 없는 메시지 타입: {message_type}")


async def handle_graph_line_request(websocket: WebSocket, message: Dict[str, Any]):
    """Graph Line 요청 처리"""
    try:
        user_input = message.get("user_input", "")
        dom_data = message.get("dom_data")
        
        logger.info(f"🔄 Graph Line 요청: {user_input[:50]}...")
        
        # Graph Line Executor로 계획 수립
        planning_result = await graph_line_executor.execute_graph_line(user_input, dom_data)
        
        if planning_result["status"] == "planning_completed":
            # 액션 MPC로 계획 전달
            execution_result = await action_mpc.execute_plan(planning_result, dom_data)
            
            # 결과를 클라이언트에게 전송
            response = {
                "type": "execution_result",
                "planning_result": planning_result,
                "execution_result": execution_result
            }
            
            await websocket.send_text(json.dumps(response))
            logger.info(f"✅ 실행 완료: {execution_result['status']}")
        
        else:
            # 에러 또는 질문 응답
            await websocket.send_text(json.dumps(planning_result))
            
    except Exception as e:
        logger.error(f"❌ Graph Line 요청 처리 오류: {e}")
        error_response = {
            "type": "error",
            "message": f"처리 중 오류 발생: {str(e)}"
        }
        await websocket.send_text(json.dumps(error_response))


async def handle_action_complete(websocket: WebSocket, message: Dict[str, Any]):
    """액션 실행 완료 처리"""
    logger.info("✅ 액션 실행 완료 신호 수신")
    # 실제로는 ActionMPC 클래스에서 처리


async def handle_dom_data(websocket: WebSocket, message: Dict[str, Any]):
    """DOM 데이터 처리"""
    dom_data = message.get("dom_data", [])
    logger.info(f"📦 DOM 데이터 수신: {len(dom_data)}개 요소")


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Action MPC Server",
        "version": "1.0.0",
        "status": "running",
        "connected_clients": len(connected_clients)
    }


@app.get("/status")
async def get_status():
    """상태 확인 엔드포인트"""
    return {
        "server_status": "running",
        "connected_clients": len(connected_clients),
        "action_mpc_state": action_mpc.execution_state,
        "current_plan": len(action_mpc.current_plan),
        "current_step": action_mpc.current_step_index
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
