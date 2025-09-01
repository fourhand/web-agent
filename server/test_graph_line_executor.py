#!/usr/bin/env python3
"""
Graph Line Executor 테스트 코드
"""

import asyncio
import json
import logging
from typing import Dict, Any

from graph_line_executor import GraphLineExecutor, ExecutionState

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 테스트용 DOM 데이터
TEST_DOM = [
    {
        "tag": "button",
        "selector": "button[type='submit']",
        "text": "로그인",
        "class": "login-btn primary",
        "type": "submit",
        "id": "login-button"
    },
    {
        "tag": "input",
        "selector": "input[name='email']",
        "type": "email",
        "placeholder": "이메일을 입력하세요",
        "name": "email",
        "id": "email-input"
    },
    {
        "tag": "input",
        "selector": "input[name='password']",
        "type": "password",
        "placeholder": "비밀번호를 입력하세요",
        "name": "password",
        "id": "password-input"
    },
    {
        "tag": "a",
        "selector": "a[href='/signup']",
        "text": "회원가입",
        "href": "/signup",
        "class": "signup-link"
    },
    {
        "tag": "div",
        "selector": "div.error-message",
        "text": "이메일 또는 비밀번호가 올바르지 않습니다.",
        "class": "error-message"
    },
    {
        "tag": "h1",
        "selector": "h1.title",
        "text": "로그인",
        "class": "title"
    },
    {
        "tag": "form",
        "selector": "form[action='/login']",
        "class": "login-form",
        "action": "/login"
    }
]


async def mock_llm_callback(prompt: str) -> str:
    """테스트용 Mock LLM 콜백 함수"""
    logger.info(f"🤖 Mock LLM 호출: {prompt[:100]}...")
    
    # 프롬프트 내용에 따라 다른 응답 생성
    if "의도 분류" in prompt or "분석해야 할 항목" in prompt:
        # 채팅 분석 응답
        return """
- 의도: action
- 목표: 네이버 메일함에 로그인하기
- 신뢰도: 0.9
- DOM 필요성: true
- 정제된 프롬프트: 네이버 메일함에 로그인하여 메일을 확인하세요
"""
    
    elif "질문에 대한 답변" in prompt:
        # 질문 처리 응답
        return """
- 답변: 현재 페이지는 로그인 페이지입니다. 이메일과 비밀번호를 입력하여 로그인할 수 있습니다.
- 신뢰도: 0.95
"""
    
    elif "단계별 계획을 수립" in prompt:
        # 계획 수립 응답
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
        # 액션 생성 응답
        return """
- 액션: input
- 대상: input[name='email']
- 이유: 로그인을 위해 이메일 주소를 입력해야 함
- 신뢰도: 0.95
"""
    
    elif "현재 페이지가 올바른지 판단" in prompt:
        # 페이지 평가 응답
        return """
- 판단: 성공
- 신뢰도: 0.9
- 이유: 로그인 페이지에서 메인 페이지로 성공적으로 이동됨
"""
    
    else:
        # 기본 응답
        return """
- 상태: unknown
- 신뢰도: 0.5
- 이유: 알 수 없는 요청
"""


async def test_graph_line_executor():
    """Graph Line Executor 전체 테스트"""
    logger.info("🧪 Graph Line Executor 테스트 시작")
    
    # Graph Line Executor 초기화
    executor = GraphLineExecutor(mock_llm_callback, max_evaluation_elements=200)
    
    # 1. 기본 상태 테스트
    logger.info("\n1️⃣ 기본 상태 테스트")
    status = executor.get_current_status()
    logger.info(f"   초기 상태: {status}")
    
    # 2. 질문 처리 테스트
    logger.info("\n2️⃣ 질문 처리 테스트")
    question_result = await executor.execute_graph_line(
        "이 페이지는 무엇인가요?", 
        TEST_DOM
    )
    logger.info(f"   질문 결과: {question_result['status']}")
    logger.info(f"   답변: {question_result.get('answer', 'N/A')[:100]}...")
    
    # 3. 계획 수립 테스트
    logger.info("\n3️⃣ 계획 수립 테스트")
    planning_result = await executor.execute_graph_line(
        "네이버 메일함에 로그인해서 새 메일 확인해줘", 
        TEST_DOM
    )
    logger.info(f"   계획 결과: {planning_result['status']}")
    logger.info(f"   메시지: {planning_result.get('message', 'N/A')}")
    logger.info(f"   총 단계: {planning_result.get('total_steps', 0)}")
    logger.info(f"   다음 액션: {planning_result.get('next_action', 'N/A')}")
    
    # 4. 상태 확인 테스트
    logger.info("\n4️⃣ 상태 확인 테스트")
    final_status = executor.get_current_status()
    logger.info(f"   최종 상태: {final_status}")
    
    # 5. 리셋 테스트
    logger.info("\n5️⃣ 리셋 테스트")
    executor.reset()
    reset_status = executor.get_current_status()
    logger.info(f"   리셋 후 상태: {reset_status}")
    
    logger.info("\n✅ Graph Line Executor 테스트 완료!")


async def test_individual_components():
    """개별 컴포넌트 테스트"""
    logger.info("🧪 개별 컴포넌트 테스트 시작")
    
    executor = GraphLineExecutor(mock_llm_callback)
    
    # 1. 채팅 분석 테스트
    logger.info("\n1️⃣ 채팅 분석 테스트")
    chat_result = await executor._analyze_chat("네이버 메일함에 로그인하기")
    logger.info(f"   의도: {chat_result.intent}")
    logger.info(f"   목표: {chat_result.goal}")
    logger.info(f"   신뢰도: {chat_result.confidence}")
    logger.info(f"   DOM 필요성: {chat_result.needs_dom}")
    
    # 2. 계획 수립 테스트
    logger.info("\n2️⃣ 계획 수립 테스트")
    planning_result = await executor._create_plan(chat_result)
    logger.info(f"   총 단계: {planning_result.total_steps}")
    logger.info(f"   신뢰도: {planning_result.confidence}")
    for i, step in enumerate(planning_result.plan_steps):
        logger.info(f"   단계 {i+1}: {step['action']} {step['target']} ({step['reason']})")
    
    # 3. 액션 실행 테스트
    logger.info("\n3️⃣ 액션 실행 테스트")
    if planning_result.plan_steps:
        executor.dom_processor.prepere_dom(TEST_DOM)
        action_result = await executor._execute_action(planning_result.plan_steps[0])
        logger.info(f"   액션: {action_result.action}")
        logger.info(f"   대상: {action_result.target}")
        logger.info(f"   성공: {action_result.success}")
        logger.info(f"   신뢰도: {action_result.confidence}")
    
    # 4. 결과 평가 테스트
    logger.info("\n4️⃣ 결과 평가 테스트")
    if planning_result.plan_steps:
        evaluation_result = await executor._evaluate_result(
            planning_result.plan_steps[0], 
            action_result
        )
        logger.info(f"   판단: {evaluation_result.judgment}")
        logger.info(f"   신뢰도: {evaluation_result.confidence}")
        logger.info(f"   이유: {evaluation_result.reason}")
        logger.info(f"   다음 액션: {evaluation_result.next_action}")
    
    logger.info("\n✅ 개별 컴포넌트 테스트 완료!")


async def test_error_handling():
    """에러 처리 테스트"""
    logger.info("🧪 에러 처리 테스트 시작")
    
    # 에러를 발생시키는 Mock LLM 콜백
    async def error_llm_callback(prompt: str) -> str:
        raise Exception("LLM 호출 실패")
    
    executor = GraphLineExecutor(error_llm_callback)
    
    try:
        result = await executor.execute_graph_line("테스트", TEST_DOM)
        logger.info(f"   에러 처리 결과: {result['status']}")
        logger.info(f"   에러 메시지: {result.get('message', 'N/A')}")
    except Exception as e:
        logger.error(f"   예상치 못한 에러: {e}")
    
    logger.info("\n✅ 에러 처리 테스트 완료!")


if __name__ == "__main__":
    # 전체 테스트 실행
    asyncio.run(test_graph_line_executor())
    asyncio.run(test_individual_components())
    asyncio.run(test_error_handling())
