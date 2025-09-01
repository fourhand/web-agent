#!/usr/bin/env python3
"""
임베딩 차원 확인 테스트
"""

import logging
from sentence_transformers import SentenceTransformer

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_embedding_dimension():
    """임베딩 모델의 차원을 확인하는 테스트"""
    try:
        logger.info("🔍 임베딩 모델 차원 확인 시작")
        
        # 모델 로드
        model = SentenceTransformer('intfloat/multilingual-e5-base')
        logger.info("✅ 모델 로드 완료")
        
        # 테스트 텍스트
        test_text = "tag:button | text:로그인 | class:login-btn primary"
        
        # 임베딩 생성
        embedding = model.encode([test_text])[0]
        dimension = len(embedding)
        
        logger.info(f"📊 임베딩 차원: {dimension}")
        logger.info(f"📝 테스트 텍스트: {test_text}")
        logger.info(f"🔢 임베딩 벡터 크기: {embedding.shape}")
        
        return dimension
        
    except Exception as e:
        logger.error(f"❌ 임베딩 차원 확인 실패: {e}")
        return None

if __name__ == "__main__":
    dimension = test_embedding_dimension()
    if dimension:
        print(f"\n🎯 결과: intfloat/multilingual-e5-base 모델의 임베딩 차원은 {dimension}차원입니다.")
    else:
        print("\n❌ 임베딩 차원 확인에 실패했습니다.")
