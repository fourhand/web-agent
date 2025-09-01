#!/usr/bin/env python3
"""
Graph Line Executor - 웹 자동화의 전체 워크플로우 관리
"""

import json
import logging
import asyncio
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

from dom_processor import DOMProcessor, PlanStep

logger = logging.getLogger("uvicorn.error")


class ExecutionState(Enum):
    """실행 상태"""
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    REPLANNING = "replanning"
    ERROR = "error"


@dataclass
class ChatAnalysisResult:
    """채팅 분석 결과"""
    intent: str  # "question" or "action"
    goal: str
    confidence: float
    needs_dom: bool
    refined_prompt: str


@dataclass
class PlanningResult:
    """계획 수립 결과"""
    plan_steps: List[PlanStep]
    total_steps: int
    confidence: float


@dataclass
class ActionResult:
    """액션 실행 결과"""
    action: str
    target: str
    success: bool
    confidence: float
    result_data: Dict[str, Any]
    error_message: Optional[str] = None


@dataclass
class EvaluationResult:
    """결과 평가"""
    judgment: str  # "success", "failure", "login_required", "uncertain"
    confidence: float
    reason: str
    next_action: str  # "continue", "replan", "complete", "wait"


class GraphLineExecutor:
    """
    Graph Line 실행을 관리하는 클래스
    
    워크플로우:
    채팅 분석 → 계획 수립 → 액션 MPC → 결과 평가 → 계획 조정/진행/종료
    """
    
    def __init__(self, llm_callback, max_evaluation_elements: int = 200):
        """
        초기화
        
        Args:
            llm_callback: LLM 호출 함수
            max_evaluation_elements: DOM 평가용 최대 요소 수
        """
        self.llm_callback = llm_callback
        self.dom_processor = DOMProcessor(max_evaluation_elements=max_evaluation_elements)
        self.current_state = ExecutionState.IDLE
        self.current_plan: List[PlanStep] = []
        self.current_step_index = 0
        self.goal = ""
        self.context: Dict[str, Any] = {}
        
        # 설정값
        self.action_confidence_threshold = 0.8
        self.evaluation_confidence_threshold = 0.7
        
        logger.info("🚀 Graph Line Executor 초기화 완료")
    
    async def execute_graph_line(self, user_input: str, dom_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Graph Line 워크플로우 실행 (계획 수립까지)
        
        Args:
            user_input: 사용자 입력
            dom_data: DOM 데이터 (선택사항)
            
        Returns:
            계획 수립 결과 (액션 MPC로 전달할 데이터)
        """
        try:
            logger.info(f"🔄 Graph Line 실행 시작: {user_input[:50]}...")
            
            # 1. 채팅 분석
            chat_result = await self._analyze_chat(user_input)
            self.goal = chat_result.goal
            
            if chat_result.intent == "question":
                return await self._handle_question(chat_result, dom_data)
            
            # 2. DOM 처리 (필요한 경우)
            if chat_result.needs_dom and dom_data:
                self.dom_processor.prepere_dom(dom_data)
                logger.info(f"📦 DOM 처리 완료: {len(dom_data)}개 요소")
            
            # 3. 계획 수립
            planning_result = await self._create_plan(chat_result)
            self.current_plan = planning_result.plan_steps
            self.current_step_index = 0
            logger.info(f"📋 계획 수립 완료: {len(self.current_plan)}단계")
            
            # 4. 액션 MPC로 전달할 결과 생성
            return self._create_planning_result(planning_result, chat_result)
            
        except Exception as e:
            logger.error(f"❌ Graph Line 실행 중 오류: {e}")
            self.current_state = ExecutionState.ERROR
            return {
                "status": "error",
                "message": f"실행 중 오류 발생: {str(e)}",
                "state": self.current_state.value
            }
    
    async def _analyze_chat(self, user_input: str) -> ChatAnalysisResult:
        """채팅 분석"""
        self.current_state = ExecutionState.ANALYZING
        
        prompt = f"""
사용자의 입력을 분석하여 다음 정보를 제공해주세요:

**사용자 입력**: {user_input}

**분석해야 할 항목**:
1. 의도 분류: "question" (질문) 또는 "action" (액션)
2. 목표 추출: 사용자가 달성하고자 하는 목표
3. 신뢰도: 0.0-1.0 (분석 확신 정도)
4. DOM 필요성: true/false (DOM 정보가 필요한지)
5. 정제된 프롬프트: 더 명확한 형태로 정제된 명령

**답변 형식**:
- 의도: [question/action]
- 목표: [사용자의 목표]
- 신뢰도: [0.0-1.0]
- DOM 필요성: [true/false]
- 정제된 프롬프트: [정제된 명령]
"""
        
        response = await self.llm_callback(prompt)
        
        # 응답 파싱 (간단한 파싱 로직)
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        return ChatAnalysisResult(
            intent=result.get('의도', 'action'),
            goal=result.get('목표', user_input),
            confidence=float(result.get('신뢰도', 0.8)),
            needs_dom=result.get('DOM 필요성', 'true').lower() == 'true',
            refined_prompt=result.get('정제된 프롬프트', user_input)
        )
    
    async def _handle_question(self, chat_result: ChatAnalysisResult, dom_data: Optional[List[Dict]]) -> Dict[str, Any]:
        """질문 처리"""
        if dom_data:
            self.dom_processor.prepere_dom(dom_data)
        
        prompt = f"""
사용자의 질문에 답변해주세요:

**질문**: {chat_result.goal}

**현재 페이지 정보**: 
{self._get_page_context() if dom_data else "페이지 정보 없음"}

**답변 형식**:
- 답변: [질문에 대한 상세한 답변]
- 신뢰도: [0.0-1.0]
"""
        
        response = await self.llm_callback(prompt)
        
        return {
            "status": "question_answered",
            "answer": response,
            "confidence": chat_result.confidence,
            "state": ExecutionState.COMPLETED.value
        }
    
    async def _create_plan(self, chat_result: ChatAnalysisResult) -> PlanningResult:
        """계획 수립"""
        self.current_state = ExecutionState.PLANNING
        
        prompt = f"""
목표 달성을 위한 단계별 계획을 수립해주세요:

**목표**: {chat_result.goal}

**현재 페이지 정보**:
{self._get_page_context()}

**계획 수립 규칙**:
1. 3-8단계로 구성
2. 각 단계는 구체적이고 실행 가능해야 함
3. 우선순위를 고려하여 순서 배치
4. 예상 결과를 명시

**답변 형식**:
- 단계 1: [액션] [대상] ([이유])
- 단계 2: [액션] [대상] ([이유])
- ...
- 총 단계: [숫자]
- 신뢰도: [0.0-1.0]
"""
        
        response = await self.llm_callback(prompt)
        
        # 응답 파싱하여 PlanStep 리스트 생성
        plan_steps = []
        lines = response.strip().split('\n')
        
        for line in lines:
            if line.startswith('단계'):
                # "단계 1: click 로그인 버튼 (로그인 폼 제출)" 형태 파싱
                parts = line.split(':', 1)
                if len(parts) == 2:
                    step_content = parts[1].strip()
                    # 괄호로 이유 분리
                    if '(' in step_content and ')' in step_content:
                        action_part = step_content[:step_content.rfind('(')].strip()
                        reason = step_content[step_content.rfind('(')+1:step_content.rfind(')')]
                        
                        # 액션과 대상 분리
                        words = action_part.split()
                        if len(words) >= 2:
                            action = words[0]
                            target = ' '.join(words[1:])
                            
                            plan_steps.append(PlanStep(
                                action=action,
                                target=target,
                                reason=reason
                            ))
        
        return PlanningResult(
            plan_steps=plan_steps,
            total_steps=len(plan_steps),
            confidence=chat_result.confidence
        )
    
    async def _execute_action(self, plan_step: PlanStep) -> ActionResult:
        """액션 실행"""
        self.current_state = ExecutionState.EXECUTING
        
        # DOM Processor를 사용하여 액션 생성 프롬프트 생성
        action_prompt = self.dom_processor.get_action_generation_prompt_data(
            self.goal, plan_step
        )
        
        # LLM에게 액션 실행 요청
        response = await self.llm_callback(action_prompt)
        
        # 응답 파싱
        lines = response.strip().split('\n')
        result = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        
        return ActionResult(
            action=result.get('액션', plan_step['action']),
            target=result.get('대상', plan_step['target']),
            success=True,  # 실제 실행은 클라이언트에서 처리
            confidence=float(result.get('신뢰도', 0.8)),
            result_data={
                'original_prompt': action_prompt,
                'llm_response': response,
                'parsed_result': result
            }
        )
    
    async def _evaluate_result(self, plan_step: PlanStep, action_result: ActionResult) -> EvaluationResult:
        """결과 평가"""
        self.current_state = ExecutionState.EVALUATING
        
        # DOM Processor를 사용하여 페이지 평가 프롬프트 생성
        evaluation_prompt = self.dom_processor.get_page_evaluation_prompt(
            self.goal, plan_step
        )
        
        # LLM에게 평가 요청
        response = await self.llm_callback(evaluation_prompt)
        
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
        
        return EvaluationResult(
            judgment=judgment,
            confidence=confidence,
            reason=reason,
            next_action=next_action
        )
    
    def _get_page_context(self) -> str:
        """현재 페이지 컨텍스트 반환"""
        if not self.dom_processor.prepered_dom:
            return "DOM 정보 없음"
        
        # 상위 5개 요소 정보 반환
        context_parts = []
        for i, element in enumerate(self.dom_processor.prepered_dom[:5]):
            context_parts.append(f"{i+1}. {element.get('tag', '')} - {element.get('text', '')[:50]}")
        
        return '\n'.join(context_parts)
    
    def _create_planning_result(self, planning_result: PlanningResult, chat_result: ChatAnalysisResult) -> Dict[str, Any]:
        """계획 수립 결과 생성 (액션 MPC로 전달)"""
        self.current_state = ExecutionState.PLANNING
        
        return {
            "status": "planning_completed",
            "message": f"계획 수립 완료: {self.goal}",
            "goal": self.goal,
            "plan_steps": planning_result.plan_steps,
            "total_steps": planning_result.total_steps,
            "confidence": planning_result.confidence,
            "chat_analysis": {
                "intent": chat_result.intent,
                "needs_dom": chat_result.needs_dom,
                "refined_prompt": chat_result.refined_prompt
            },
            "dom_context": self._get_page_context(),
            "state": self.current_state.value,
            "next_action": "execute_plan"  # 액션 MPC로 전달 신호
        }
    
    def _create_completion_result(self) -> Dict[str, Any]:
        """완료 결과 생성"""
        self.current_state = ExecutionState.COMPLETED
        return {
            "status": "completed",
            "message": f"목표 달성 완료: {self.goal}",
            "total_steps": len(self.current_plan),
            "executed_steps": self.current_step_index,
            "state": self.current_state.value
        }
    
    async def _handle_replanning(self) -> Dict[str, Any]:
        """계획 재수립"""
        self.current_state = ExecutionState.REPLANNING
        self.current_plan = []
        self.current_step_index = 0
        
        return {
            "status": "replanning",
            "message": "계획 재수립이 필요합니다",
            "state": self.current_state.value
        }
    
    def _create_wait_result(self, evaluation_result: EvaluationResult) -> Dict[str, Any]:
        """대기 결과 생성"""
        return {
            "status": "waiting",
            "message": evaluation_result.reason,
            "state": ExecutionState.IDLE.value,
            "requires_user_action": True
        }
    
    def get_current_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            "state": self.current_state.value,
            "goal": self.goal,
            "current_step": self.current_step_index,
            "total_steps": len(self.current_plan),
            "progress": (self.current_step_index / len(self.current_plan) * 100) if self.current_plan else 0
        }
    
    def reset(self):
        """상태 초기화"""
        self.current_state = ExecutionState.IDLE
        self.current_plan = []
        self.current_step_index = 0
        self.goal = ""
        self.context = {}
        logger.info("🔄 Graph Line Executor 상태 초기화 완료")
