#!/usr/bin/env python3
"""
DOM Processor 테스트 코드
"""

import asyncio
import json
import logging
from dom_processor import DOMProcessor, PlanStep

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

async def mock_llm_callback(prompt: str, image_data: str = "") -> str:
    """테스트용 LLM 콜백 함수"""
    logger.info(f"🤖 Mock LLM 호출: {prompt[:100]}...")
    
    # 간단한 응답 시뮬레이션
    if "검증" in prompt:
        return '''
        {
            "verification_status": "success",
            "page_type": "login",
            "main_content": true,
            "navigation": false,
            "key_features": ["로그인 폼", "이메일 입력", "비밀번호 입력"],
            "primary_action": "로그인",
            "user_intent": "사용자 인증",
            "verification_reason": "로그인 페이지에 성공적으로 도달함",
            "next_action": "로그인 정보 입력",
            "confidence": 0.9
        }
        '''
    elif "설명" in prompt:
        return '''
        {
            "page_purpose": "사용자 로그인",
            "main_function": "인증",
            "sub_functions": ["이메일 입력", "비밀번호 입력", "로그인 제출"],
            "user_workflow": "이메일 입력 → 비밀번호 입력 → 로그인 버튼 클릭",
            "key_elements": ["로그인 폼", "이메일 필드", "비밀번호 필드"],
            "page_type": "로그인 페이지",
            "confidence": 0.9
        }
        '''
    else:
        return '{"action": "click", "selector": "button[type=\\"submit\\"]", "confidence": 0.8}'

async def test_dom_processor():
    """DOM Processor 전체 기능 테스트"""
    logger.info("🧪 DOM Processor 테스트 시작")
    
    # DOM Processor 초기화
    processor = DOMProcessor(max_evaluation_elements=200)
    
    # 1. DOM 준비 테스트
    logger.info("\n1️⃣ DOM 준비 테스트")
    processor.prepere_dom(TEST_DOM)
    logger.info(f"   준비된 DOM: {len(processor.prepered_dom)}개 요소")
    logger.info(f"   텍스처: {len(processor.dom_textures)}개")
    
    # 2. DOM 필터링 테스트
    logger.info("\n2️⃣ DOM 필터링 테스트")
    filtered = processor.filter_dom(TEST_DOM)
    logger.info(f"   필터링 결과: {len(filtered)}개 요소")
    
    # 3. DOM 텍스처 추출 테스트
    logger.info("\n3️⃣ DOM 텍스처 추출 테스트")
    textures = processor.extract_dom_texture(TEST_DOM)
    logger.info(f"   텍스처 추출 결과: {len(textures)}개")
    for i, texture in enumerate(textures[:3]):
        logger.info(f"   텍스처 {i+1}: {texture.get('texture', 'N/A')[:100]}...")
    
    # 4. DOM 임베딩 테스트
    logger.info("\n4️⃣ DOM 임베딩 테스트")
    embedded = processor.embed_dom(textures)
    logger.info(f"   임베딩 결과: {len(embedded)}개")
    embedding_count = sum(1 for el in embedded if el.get("embedding"))
    logger.info(f"   임베딩 생성된 요소: {embedding_count}개")
    
    # 5. DOM 리랭킹 테스트
    logger.info("\n5️⃣ DOM 리랭킹 테스트")
    query = "로그인 버튼 클릭"
    reranked = processor.rerank_dom(embedded, query)
    logger.info(f"   리랭킹 결과: {len(reranked)}개")
    if reranked:
        top_element = reranked[0]
        logger.info(f"   최고 유사도 요소: {top_element.get('tag', 'N/A')} - {top_element.get('text', 'N/A')}")
        logger.info(f"   유사도 점수: {top_element.get('similarity_score', 'N/A')}")
    
    # 6. 액션 생성 프롬프트 테스트
    logger.info("\n6️⃣ 액션 생성 프롬프트 테스트")
    goal = "네이버 메일함에 로그인하기"
    plan_step: PlanStep = {"action": "click", "target": "로그인 버튼", "reason": "로그인 폼 제출"}
    action_prompt = processor.get_action_generation_prompt_data(goal, plan_step)
    logger.info(f"   프롬프트 생성 완료: {len(action_prompt)}자")
    logger.info(f"   프롬프트 미리보기: {action_prompt[:200]}...")
    
    # 7. 페이지 평가 프롬프트 테스트
    logger.info("\n7️⃣ 페이지 평가 프롬프트 테스트")
    evaluation_prompt = processor.get_page_evaluation_prompt(goal, plan_step)
    logger.info(f"   프롬프트 생성 완료: {len(evaluation_prompt)}자")
    logger.info(f"   프롬프트 미리보기: {evaluation_prompt[:200]}...")
    
    # 8. 페이지 분석 테스트 (제거됨)
    logger.info("\n8️⃣ 페이지 분석 테스트")
    logger.info("   analyze_page() 함수는 제거됨")
    
    # 9. 페이지 텍스처 설명 데이터 준비 테스트 (제거됨)
    logger.info("\n9️⃣ 페이지 텍스처 설명 데이터 준비 테스트")
    logger.info("   explain_page_texture() 함수는 제거됨")
    
    # 10. 기타 유틸리티 테스트
    logger.info("\n🔟 기타 유틸리티 테스트")
    
    # 기타 유틸리티 테스트 (제거됨)
    logger.info("   detect_login_page() 함수는 제거됨")
    logger.info("   find_interactive_elements() 함수는 제거됨")
    logger.info("   extract_key_information() 함수는 제거됨")
    logger.info("   get_dom_statistics() 함수는 제거됨")
    
    logger.info("\n✅ 모든 테스트 완료!")

def test_individual_functions():
    """개별 함수 테스트"""
    logger.info("🧪 개별 함수 테스트 시작")
    
    processor = DOMProcessor(max_evaluation_elements=200)
    
    # JSON 추출 테스트 (제거됨)
    logger.info("JSON 추출 테스트: extract_top_level_json() 함수는 제거됨")
    
    # DOM 압축 테스트 (제거됨)
    logger.info("DOM 압축 테스트: compress_dom() 함수는 제거됨")
    
    # DOM 청킹 테스트 (제거됨)
    logger.info("DOM 청킹 테스트: chunk_dom() 함수는 제거됨")
    
    logger.info("✅ 개별 함수 테스트 완료!")

if __name__ == "__main__":
    # 개별 함수 테스트
    test_individual_functions()
    
    # 전체 기능 테스트
    asyncio.run(test_dom_processor())
