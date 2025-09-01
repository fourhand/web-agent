# 🤖 MCP LLM Browser Automation System

AI 기반의 지능형 브라우저 자동화 시스템으로, Model Context Protocol (MCP)을 기반으로 DOM 처리와 상태 관리를 통해 복잡한 웹 작업을 자동으로 수행합니다.

## 🎯 프로젝트 개요

이 시스템은 Model Context Protocol (MCP)을 기반으로 LLM(Large Language Model)과 Chrome Extension을 결합하여 자연어 명령으로 웹 브라우저를 자동화하는 혁신적인 도구입니다. 표준화된 도구 인터페이스를 통해 DOM Processor를 통한 페이지 구조 분석과 Graph Line 실행을 통한 지능적인 웹 자동화를 제공합니다.

## 🚀 주요 기능

### 🧠 지능형 DOM 처리
- **DOM 텍스처 추출**: HTML 요소를 구조화된 텍스트로 변환
- **임베딩 기반 분석**: `intfloat/multilingual-e5-base` 모델로 768차원 벡터 생성
- **FAISS 유사도 검색**: 벡터 기반 요소 리랭킹 및 검색
- **목적별 프롬프트 생성**: 액션 생성과 페이지 평가를 위한 최적화된 프롬프트

### 🔧 MCP 기반 모듈화
- **표준화된 도구 인터페이스**: DOM 분석, 계획 수립, 액션 실행, 결과 평가
- **확장 가능한 아키텍처**: 새로운 도구 쉽게 추가 가능
- **타입 안전성**: Pydantic 모델 기반 데이터 검증
- **REST API & WebSocket**: 다양한 클라이언트 지원

### 🔄 Graph Line 실행 시스템
- **채팅 분석** → **계획 수립** → **액션 MPC** → **결과 평가** → **계획 조정/진행/종료**
- **상태 기반 실행**: 각 단계별 결과에 따른 동적 워크플로우
- **신뢰도 기반 결정**: LLM의 확신 정도에 따른 자동/수동 실행
- **실시간 피드백**: 각 단계별 결과를 즉시 반영

### 🎨 Chrome Extension UI
- **Side Panel 인터페이스**: 페이지 레이아웃에 영향을 주지 않는 안정적인 UI
- **실시간 로그**: 모든 자동화 과정을 실시간으로 모니터링
- **WebSocket 통신**: 서버와 실시간 양방향 통신
- **상태 표시**: 현재 실행 단계와 진행 상황을 시각적으로 확인

## 🏗️ 시스템 아키텍처

### 📊 전체 워크플로우

```
사용자 입력
    ↓
채팅 분석 (Chat Analysis)
    ↓
DOM 필요성 판단
    ↓
DOM 처리 (DOM Processor)
    ↓
계획 수립 (Planning)
    ↓
액션 MPC (Action MPC)
    ↓
결과 평가 (Evaluation)
    ↓
계획 조정 or 다음 계획 진행 or 종료
```

### 🔧 핵심 컴포넌트

#### 1. **MCP 서버 (MCP Server)**
- **목적**: 표준화된 도구 인터페이스 제공
- **기능**:
  - 도구 등록 및 관리
  - 요청/응답 처리
  - 알림 시스템
- **출력**: `MCPResponse`

#### 2. **DOM 분석 도구 (DOM Analysis Tool)**
- **목적**: 페이지 구조 분석 및 LLM용 데이터 준비
- **기능**:
  - DOM 텍스처 추출 및 임베딩
  - 목적별 프롬프트 생성
  - 유사도 기반 요소 리랭킹
- **출력**: 액션 생성 프롬프트, 페이지 평가 프롬프트

#### 3. **계획 수립 도구 (Planning Tool)**
- **목적**: 목표 달성을 위한 단계별 계획 생성
- **기능**:
  - 목표 기반 계획 수립
  - 단계별 액션 정의
  - 우선순위 설정
- **출력**: `PlanStep[]`

#### 4. **액션 실행 도구 (Action Execution Tool)**
- **목적**: 계획된 액션의 실행 및 모니터링
- **기능**:
  - 액션 타입별 실행
  - 실시간 상태 모니터링
  - 에러 처리 및 재시도
- **출력**: 액션 실행 결과

#### 5. **결과 평가 도구 (Evaluation Tool)**
- **목적**: 액션 실행 결과 분석 및 다음 단계 결정
- **기능**:
  - 목표 달성도 평가
  - 페이지 상태 분석
  - 다음 액션 결정
- **출력**: 평가 결과 및 다음 단계

## 🧩 DOM Processor 상세 구조

### 📋 주요 클래스

```python
class PlanStep(TypedDict):
    """계획 단계를 나타내는 타입"""
    action: str      # 수행할 액션 (click, input, select, navigate, wait, scroll, none)
    target: str      # 대상 요소 또는 텍스트
    reason: str      # 이 액션을 수행하는 이유

class DOMProcessor:
    """DOM 처리 전용 클래스"""
    
    def __init__(self, max_evaluation_elements: int = 200):
        # 임베딩 모델: intfloat/multilingual-e5-base (768차원)
        # FAISS 인덱스: 벡터 유사도 검색
        # 최대 평가 요소: 200개 (설정 가능)
    
    def prepere_dom(self, dom_data: List[Dict]) -> None:
        """DOM 전처리: 필터링 → 텍스처 추출 → 임베딩 생성"""
    
    def get_action_generation_prompt_data(self, goal: str, plan_step: PlanStep) -> str:
        """LLM에게 Goal과 Plan_step을 바탕으로 다음 액션을 생성하도록 시키는 프롬프트"""
    
    def get_page_evaluation_prompt(self, goal: str, plan_step: PlanStep) -> str:
        """LLM에게 goal과 plan_step의 결과로 현재 페이지가 올바른지 판단하도록 시키는 프롬프트"""
```

### 🔄 DOM 처리 파이프라인

1. **DOM 필터링**: `selector`가 있는 요소만 선택
2. **텍스처 추출**: 태그, 텍스트, 클래스, 속성을 구조화된 문자열로 변환
3. **임베딩 생성**: `intfloat/multilingual-e5-base` 모델로 768차원 벡터 생성
4. **유사도 검색**: FAISS를 사용한 벡터 기반 리랭킹
5. **프롬프트 생성**: 목적별 최적화된 LLM 프롬프트 생성

### 📊 임베딩 시스템

- **모델**: `intfloat/multilingual-e5-base`
- **차원**: 768차원
- **언어**: 다국어 지원 (한국어 포함)
- **특징**: 문장 임베딩에 최적화된 모델

## 🎯 Graph Line 실행 상세

### 📈 실행 단계별 상세

#### 1. **채팅 분석 단계**
```python
def analyze_chat(user_input: str) -> ChatAnalysisResult:
    """
    사용자 입력 분석
    - 의도 분류: question vs action
    - 목표 추출
    - DOM 필요성 판단
    """
```

#### 2. **DOM 처리 단계**
```python
def process_dom(dom_data: List[Dict], goal: str, plan_step: PlanStep) -> DOMProcessingResult:
    """
    DOM 처리 및 프롬프트 생성
    - DOM 전처리
    - 액션 생성 프롬프트
    - 페이지 평가 프롬프트
    """
```

#### 3. **계획 수립 단계**
```python
def create_plan(goal: str, dom_context: str) -> List[PlanStep]:
    """
    목표 달성을 위한 계획 수립
    - 단계별 액션 정의
    - 우선순위 설정
    - 예상 결과 정의
    """
```

#### 4. **액션 MPC 단계**
```python
def execute_action(plan_step: PlanStep, dom_context: str) -> ActionResult:
    """
    계획된 액션 실행
    - 액션 타입별 실행
    - 실시간 모니터링
    - 에러 처리
    """
```

#### 5. **결과 평가 단계**
```python
def evaluate_result(goal: str, plan_step: PlanStep, action_result: ActionResult) -> EvaluationResult:
    """
    액션 실행 결과 평가
    - 목표 달성도 평가
    - 페이지 상태 분석
    - 다음 단계 결정
    """
```

### 🔄 상태 전이 로직

```
idle → analyzing → planning → executing → evaluating → (completed | replanning | continuing)
```

- **completed**: 목표 달성 완료
- **replanning**: 계획 재수립 필요
- **continuing**: 다음 계획 단계 진행

## 🎨 액션 타입 시스템

### 📋 기본 액션 타입

| 액션 | 설명 | 예시 |
|------|------|------|
| `click` | 요소 클릭 | 버튼, 링크 클릭 |
| `input` | 텍스트 입력 | 폼 필드 입력 |
| `select` | 드롭다운/선택 | 옵션 선택 |
| `navigate` | 페이지 이동 | URL 이동 |
| `wait` | 대기 | 페이지 로딩 대기 |
| `scroll` | 스크롤 | 페이지 스크롤 |
| `none` | 액션 없음 | 작업 완료 |

### 🎯 액션 실행 예시

```python
# 액션 생성 프롬프트 결과
{
    "action": "click",
    "target": "button[type='submit']",
    "reason": "로그인 폼 제출",
    "confidence": 0.95
}

# 페이지 평가 프롬프트 결과
{
    "judgment": "성공",
    "confidence": 0.9,
    "reason": "로그인 페이지에서 메인 페이지로 이동됨"
}
```

## 🏗️ 시스템 구조

### 📁 프로젝트 구조

```
web-agent/
├── server/
│   ├── mcp_server.py             # MCP 서버 핵심 클래스
│   ├── app_mcp.py                # MCP FastAPI 서버
│   ├── dom_processor.py          # DOM 처리 핵심 클래스
│   ├── graph_line_executor.py    # Graph Line 실행 엔진
│   ├── app_mpc.py                # 액션 MPC 서버 (레거시)
│   ├── requirements.txt          # Python 의존성
│   ├── test_mcp_server.py        # MCP 서버 테스트
│   └── test_dom_processor.py     # DOM Processor 테스트
├── extension/
│   ├── content.js                # DOM 캡처 및 WebSocket 통신
│   ├── sidepanel.js              # 사용자 인터페이스
│   └── manifest.json             # 확장 프로그램 설정
└── README.md                     # 프로젝트 문서
```

### 🔌 API 엔드포인트

#### WebSocket 연결
```javascript
// 클라이언트 연결
const ws = new WebSocket('ws://localhost:8000/ws');
```

#### MCP 메시지 타입
```typescript
interface MCPRequest {
    id: string;
    method: string;
    params: Record<string, any>;
    tool_type: string;
}

interface MCPResponse {
    id: string;
    result: Record<string, any>;
    error?: string;
    timestamp: number;
}

interface MCPNotification {
    method: string;
    params: Record<string, any>;
    tool_type: string;
    timestamp: number;
}

// 도구별 메시지
interface DOMAnalysisRequest {
    operation: 'prepare' | 'get_context' | 'get_action_prompt' | 'get_evaluation_prompt';
    dom_data?: DOMElement[];
    goal?: string;
    plan_step?: PlanStep;
}

interface PlanningRequest {
    user_input: string;
    dom_data?: DOMElement[];
}

interface ActionExecutionRequest {
    operation: 'set_plan' | 'execute_step' | 'get_status';
    plan_steps?: PlanStep[];
    goal?: string;
}
```

## 🚀 성능 최적화

### ⚡ 처리 최적화
- **DOM 청킹**: 대용량 페이지 처리 (200개 요소 제한)
- **조기 종료**: 높은 신뢰도 시 분석 중단
- **캐싱**: 임베딩 결과 캐싱
- **병렬 처리**: 독립적인 DOM 요소 병렬 처리

### 🔒 안정성
- **에러 처리**: JSON 파싱, 네트워크 오류 처리
- **재시도 로직**: 실패한 액션 자동 재시도
- **로그인 감지**: 사용자 개입 필요 시 대기
- **상태 복원**: 페이지 새로고침 시 상태 자동 복원

## 📊 모니터링 및 로깅

### 📈 실시간 모니터링
- **단계별 진행률**: 각 Graph Line 단계별 진행 상황
- **신뢰도 추적**: LLM 판단의 신뢰도 변화 추적
- **성능 메트릭**: 처리 시간, 성공률 등
- **에러 로깅**: 상세한 에러 정보 및 스택 트레이스

### 🔍 디버깅 도구
- **DOM 시각화**: 처리된 DOM 요소 시각적 표시
- **임베딩 검사**: 벡터 유사도 검색 결과 확인
- **프롬프트 검사**: 생성된 LLM 프롬프트 내용 확인
- **실행 히스토리**: 전체 실행 과정 기록

## 🎯 사용 예시

### 📝 기본 사용법

1. **Chrome Extension 설치 및 활성화**
2. **Side Panel에서 목표 입력**: "네이버 메일함에 로그인해서 새 메일 확인해줘"
3. **자동 실행**: 시스템이 자동으로 계획 수립 → 실행 → 평가 → 완료
4. **결과 확인**: Side Panel에서 진행 상황 및 결과 확인

### 🔧 고급 설정

```python
# DOM Processor 설정
processor = DOMProcessor(max_evaluation_elements=300)  # 더 많은 요소 분석

# 신뢰도 임계값 설정
ACTION_CONFIDENCE_THRESHOLD = 0.8  # 높은 신뢰도만 자동 실행
EVALUATION_CONFIDENCE_THRESHOLD = 0.7  # 평가 신뢰도 임계값
```

## 🚀 향후 개발 계획

### 📋 단기 계획
- [ ] 더 많은 액션 타입 지원
- [ ] 다국어 프롬프트 최적화
- [ ] 성능 모니터링 대시보드
- [ ] 사용자 피드백 시스템

### 🎯 중기 계획
- [ ] 머신러닝 기반 액션 예측
- [ ] 복잡한 워크플로우 지원
- [ ] API 기반 확장성
- [ ] 클라우드 배포 지원

### 🌟 장기 계획
- [ ] 멀티 브라우저 지원
- [ ] 모바일 웹 자동화
- [ ] AI 기반 사용자 행동 학습
- [ ] 엔터프라이즈급 보안

## 🤝 기여하기

1. **Fork** 프로젝트
2. **Feature branch** 생성 (`git checkout -b feature/AmazingFeature`)
3. **Commit** 변경사항 (`git commit -m 'Add some AmazingFeature'`)
4. **Push** 브랜치 (`git push origin feature/AmazingFeature`)
5. **Pull Request** 생성

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 📞 문의

- **이슈 리포트**: GitHub Issues
- **기능 요청**: GitHub Discussions
- **문서 개선**: Pull Request

---

**MCP LLM Browser Automation System** - 지능형 웹 자동화의 새로운 패러다임 🚀