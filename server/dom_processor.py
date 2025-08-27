import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple, TypedDict
import asyncio
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

logger = logging.getLogger("uvicorn.error")


class PlanStep(TypedDict):
    """계획 단계를 나타내는 타입"""
    action: str  # 수행할 액션 (click, input, select, navigate, wait, scroll, none)
    target: str  # 대상 요소 또는 텍스트
    reason: str  # 이 액션을 수행하는 이유


class DOMProcessor:
    """
    DOM 처리 전용 클래스
    
    주요 기능:
    1. DOM 전처리: 필터링 → 텍스처 추출 → 임베딩 생성
    2. DOM 분석: 유사도 기반 리랭킹 및 요약
    3. 페이지 검증: 로그인 감지 및 페이지 구조 분석
    4. LLM 데이터 준비: LLM에 전달할 형태로 데이터 변환
    
    사용 패턴:
    1. prepere_dom(dom_data) - DOM 전처리
    2. get_action_generation_prompt_data(goal, plan_step) - LLM에게 Goal과 Plan_step을 바탕으로 다음 액션을 생성하도록 시키는 프롬프트
    3. get_page_evaluation_prompt(goal, plan_step) - LLM에게 goal과 plan_step의 결과로 현재 페이지가 올바른지 판단하도록 시키는 프롬프트
    4. explain_page_texture(goal, plan_step) - LLM에게 페이지 설명을 시키기 위한 프롬프트 데이터
    """
    
    def __init__(self, max_evaluation_elements: int = 200):
        self.max_elements = 50  # 압축 후 최대 요소 수
        self.max_evaluation_elements = max_evaluation_elements  # 페이지 평가용 최대 요소 수
        self.prepered_dom = None
        self.original_dom = None
        
        # 임베딩 모델 초기화
        try:
            self.embedding_model = SentenceTransformer('intfloat/multilingual-e5-base')
            logger.info("✅ 임베딩 모델 로드 완료: intfloat/multilingual-e5-base")
        except Exception as e:
            logger.error(f"❌ 임베딩 모델 로드 실패: {e}")
            self.embedding_model = None
        
        # FAISS 인덱스 초기화
        self.faiss_index = None
        self.dom_textures = []  # DOM 텍스처 리스트

    def filter_dom(self, dom: List[Dict]) -> List[Dict]:
        """selector가 있는 DOM 요소만 필터링"""
        filtered = []
        for el in dom:
            if not el.get("selector"):
                continue
            filtered.append(el)
        return filtered

    def extract_dom_texture(self, dom: List[Dict]) -> List[Dict]:
        """DOM 요소를 텍스트로 직렬화 (태그, 텍스트, 클래스, 속성 등)"""
        textures = []
        for el in dom:
            if not el.get("selector"):
                continue
            
            # 텍스처 구성 요소들
            texture_parts = []
            
            # 태그 이름
            if el.get("tag"):
                texture_parts.append(f"tag:{el['tag']}")
            
            # 텍스트 요소
            if el.get("text"):
                texture_parts.append(f"text:{el['text'][:50]}")  # 50자로 제한
            
            # 클래스 이름
            if el.get("class"):
                texture_parts.append(f"class:{el['class']}")
            
            # 속성들
            for attr_name, attr_value in el.items():
                if attr_name in ["tag", "selector", "text", "class"]:
                    continue  # 이미 처리된 속성들
                if attr_value and attr_name not in ["id", "name", "type", "href", "value", "placeholder", "title"]:
                    texture_parts.append(f"{attr_name}:{attr_value}")
            
            # 텍스처 문자열 생성
            texture_text = " | ".join(texture_parts)
            
            # 원본 요소에 텍스처 추가
            el_with_texture = el.copy()
            el_with_texture["texture"] = texture_text
            textures.append(el_with_texture)
        
        logger.info(f"🎨 DOM 텍스처 추출: {len(dom)}개 → {len(textures)}개")
        return textures

    def embed_dom(self, dom: List[Dict]) -> List[Dict]:
        """DOM 텍스처를 벡터로 임베딩 (intfloat/multilingual-e5-base 모델 사용)"""
        if not self.embedding_model:
            logger.warning("⚠️ 임베딩 모델이 없어서 원본 반환")
            return dom
        
        embedded = []
        embedding_dimension = None
        
        for el in dom:
            if not el.get("selector"):
                continue
            
            # 텍스처가 있으면 임베딩 생성
            if el.get("texture"):
                try:
                    # 텍스처를 벡터로 변환
                    texture_embedding = self.embedding_model.encode([el["texture"]])[0]
                    
                    # 임베딩 차원 기록 (첫 번째 요소에서만)
                    if embedding_dimension is None:
                        embedding_dimension = len(texture_embedding)
                    
                    # 원본 요소에 임베딩 추가
                    el_with_embedding = el.copy()
                    el_with_embedding["embedding"] = texture_embedding.tolist()
                    embedded.append(el_with_embedding)
                except Exception as e:
                    logger.error(f"❌ 임베딩 생성 실패: {e}")
                    embedded.append(el)
            else:
                embedded.append(el)
        
        logger.info(f"🔢 DOM 임베딩: {len(dom)}개 → {len(embedded)}개 (차원: {embedding_dimension})")
        return embedded

    def rerank_dom(self, dom: List[Dict], query: str = "") -> List[Dict]:
        """FAISS를 사용한 벡터 유사도 기반 DOM 리랭킹"""
        if not dom or not self.embedding_model:
            return dom
        
        # 임베딩이 있는 요소들만 필터링
        elements_with_embeddings = [el for el in dom if el.get("embedding")]
        if not elements_with_embeddings:
            return dom
        
        try:
            # 임베딩 벡터들을 numpy 배열로 변환
            embeddings = np.array([el["embedding"] for el in elements_with_embeddings])
            
            # FAISS 인덱스 생성 (L2 거리 사용)
            dimension = embeddings.shape[1]
            self.faiss_index = faiss.IndexFlatL2(dimension)
            self.faiss_index.add(embeddings.astype('float32'))
            
            # 쿼리 임베딩 생성 (쿼리가 있는 경우)
            if query:
                query_embedding = self.embedding_model.encode([query])[0]
                query_vector = query_embedding.reshape(1, -1).astype('float32')
                
                # 유사도 검색
                distances, indices = self.faiss_index.search(query_vector, len(elements_with_embeddings))
                
                # 거리 기반으로 재정렬 (거리가 작을수록 유사)
                reranked_elements = []
                for idx in indices[0]:
                    if idx < len(elements_with_embeddings):
                        element = elements_with_embeddings[idx].copy()
                        element["similarity_score"] = 1.0 / (1.0 + distances[0][list(indices[0]).index(idx)])
                        reranked_elements.append(element)
                
                # 임베딩이 없는 요소들은 뒤에 추가
                elements_without_embeddings = [el for el in dom if not el.get("embedding")]
                reranked_elements.extend(elements_without_embeddings)
                
                logger.info(f"🔄 DOM 리랭킹: 쿼리='{query}', {len(dom)}개 → {len(reranked_elements)}개")
                return reranked_elements
            else:
                # 쿼리가 없으면 원본 순서 유지
                return dom
                
        except Exception as e:
            logger.error(f"❌ DOM 리랭킹 실패: {e}")
            return dom
    
    def prepere_dom(self, dom: List[Dict]):
        """DOM 전처리: 필터링 → 텍스처 추출 → 임베딩 생성"""
        self.original_dom = dom
        dom = self.filter_dom(dom)
        dom = self.extract_dom_texture(dom)
        dom = self.embed_dom(dom)
        self.prepered_dom = dom
        
        # DOM 텍스처 저장
        self.dom_textures = [el.get("texture", "") for el in dom if el.get("texture")]
        
        logger.info(f"📦 DOM 준비 완료: {len(dom)}개 요소, {len(self.dom_textures)}개 텍스처")

    


    def get_action_generation_prompt_data(self, goal: str, plan_step: PlanStep, max_elements: int = 20) -> str:
        """LLM에게 Goal과 Plan_step을 바탕으로 다음 액션을 생성하도록 시키는 프롬프트 생성 (prepere_dom() 이후 호출)"""
        if not self.prepered_dom:
            logger.warning("⚠️ prepere_dom()을 먼저 호출해주세요")
            return "DOM이 준비되지 않았습니다."
        
        try:
            # 액션 실행용 쿼리 (클릭, 입력, 내비게이션 중심)
            action_query = f"액션 실행 {goal} {plan_step.get('target', '')} {plan_step.get('reason', '')} 클릭 입력 내비게이션"
            reranked_dom = self.rerank_dom(self.prepered_dom, action_query)
            
            # 상위 유사도 요소들만 선택
            top_elements = reranked_dom[:max_elements]
            
            # LLM에게 액션 생성을 요청하는 프롬프트 생성
            prompt = f"""
현재 페이지의 DOM 요소들을 분석하여 다음 목표를 달성하기 위한 다음 액션을 생성해주세요:

**목표**: {goal}
**현재 계획 단계**: {plan_step.get('action', '')} {plan_step.get('target', '')} ({plan_step.get('reason', '')})

**현재 페이지의 상호작용 가능한 요소들**:
"""
            
            for i, element in enumerate(top_elements, 1):
                prompt += f"""
{i}. 태그: {element.get('tag', '')}
   텍스트: {element.get('text', '')}
   선택자: {element.get('selector', '')}
   텍스처: {element.get('texture', '')}
   관련도 점수: {element.get('similarity_score', 0.0):.3f}
"""
                
                # 액션 실행에 중요한 속성들 추가
                important_attrs = []
                for attr in ["id", "name", "type", "class", "href", "value", "placeholder", "onclick", "data-action"]:
                    if element.get(attr):
                        important_attrs.append(f"{attr}={element[attr]}")
                
                if important_attrs:
                    prompt += f"   속성: {', '.join(important_attrs)}\n"
            
            prompt += f"""

**질문**: 위의 목표와 현재 계획 단계를 고려할 때, 다음에 수행해야 할 액션은 무엇인가요?

**액션 타입**:
1. "click" - 요소 클릭
2. "input" - 텍스트 입력
3. "select" - 드롭다운/선택
4. "navigate" - 페이지 이동
5. "wait" - 대기
6. "scroll" - 스크롤
7. "none" - 더 이상 할 액션이 없음

**답변 형식**: 
- 액션: [액션 타입]
- 대상: [선택자 또는 텍스트]
- 이유: [이 액션을 선택한 이유]
- 신뢰도: [0.0-1.0] (0.0=매우 불확실, 1.0=매우 확실)
"""
            
            logger.info(f"📝 액션 생성 프롬프트 생성: {len(top_elements)}개 요소")
            return prompt
            
        except Exception as e:
            logger.error(f"❌ 액션 생성 프롬프트 생성 실패: {e}")
            return f"프롬프트 생성 중 오류 발생: {str(e)}"
    
    def get_page_evaluation_prompt(self, goal: str, plan_step: PlanStep) -> str:
        """LLM에게 goal과 plan_step의 결과로 현재 페이지가 올바른지 판단하도록 시키는 프롬프트 생성 (prepere_dom() 이후 호출)"""
        if not self.prepered_dom:
            logger.warning("⚠️ prepere_dom()을 먼저 호출해주세요")
            return "DOM이 준비되지 않았습니다."
        
        try:
            # goal과 plan_step을 기반으로 쿼리 생성
            evaluation_query = f"페이지 평가 {goal} {plan_step.get('action', '')} {plan_step.get('target', '')} {plan_step.get('reason', '')}"
            reranked_dom = self.rerank_dom(self.prepered_dom, evaluation_query)
            
            # 상위 max_evaluation_elements개 요소의 texture 데이터 추출
            top_elements = []
            for el in reranked_dom[:self.max_evaluation_elements]:
                element_info = {
                    "tag": el.get("tag", ""),
                    "text": el.get("text", ""),
                    "texture": el.get("texture", ""),
                    "similarity_score": el.get("similarity_score", 0.0)
                }
                top_elements.append(element_info)
            
            # LLM에게 판단을 요청하는 프롬프트 생성
            prompt = f"""
현재 페이지의 DOM 요소들을 분석하여 다음 질문에 답해주세요:

**목표**: {goal}
**실행한 액션**: {plan_step.get('action', '')}
**대상**: {plan_step.get('target', '')}
**이유**: {plan_step.get('reason', '')}

**현재 페이지의 주요 요소들**:
"""
            
            for i, element in enumerate(top_elements, 1):
                prompt += f"""
{i}. 태그: {element['tag']}
   텍스트: {element['text']}
   텍스처: {element['texture']}
   관련도 점수: {element['similarity_score']:.3f}
"""
            
            prompt += f"""

**질문**: 위의 목표와 실행한 액션을 고려할 때, 현재 페이지가 올바른 결과 페이지인가요?

다음 중 하나로 답변해주세요:
1. "성공" - 목표가 달성되었거나 올바른 페이지에 도달함
2. "실패" - 목표가 달성되지 않았거나 잘못된 페이지에 도달함  
3. "로그인 필요" - 로그인이 필요한 상태
4. "확인 불가" - 현재 정보로는 판단하기 어려움

**답변 형식**: 
- 판단: [성공/실패/로그인 필요/확인 불가]
- 신뢰도: [0.0-1.0] (0.0=매우 불확실, 1.0=매우 확실)
- 이유: [판단 근거를 간단히 설명]
"""
            
            logger.info(f"🔍 페이지 평가 프롬프트 생성: {len(top_elements)}개 요소 (최대 {self.max_evaluation_elements}개)")
            return prompt
            
        except Exception as e:
            logger.error(f"❌ 페이지 평가 프롬프트 생성 실패: {e}")
            return f"프롬프트 생성 중 오류 발생: {str(e)}"

    


    

    
