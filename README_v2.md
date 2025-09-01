# MCP LLM Browser Automation System v2

DOM 처리와 상태 기반 계획 실행을 통해 복잡한 웹 작업을 자동화하는 브라우저 에이전트입니다. Chrome Extension, ActionMCP, DOM Processor, LLM Client, Orchestrator가 서로 연동되어 사용자 목표를 단계적으로 수행합니다.

## 주요 구성 요소

### 1. Chrome Extension (안정)
- 사이드 패널 UI 제공
- DOM 캡쳐와 이벤트 전달
- 페이지 로딩 완료 이벤트 전송

### 2. ActionMCP (진행 중)
- Chrome Extension과 통신하여 DOM 수집 및 브라우저 제어
- 채팅 메시지를 중계하고, DOM 데이터를 Orchestrator로 전달

### 3. DOM Processor (안정)
1. **DOM 전처리**: 필터링 → 텍스트 추출 → 임베딩 생성
2. **DOM 분석**: 유사도 기반 리랭킹 및 요약
3. **페이지 검증**: 로그인 감지 및 페이지 구조 분석
4. **LLM 데이터 준비**: LLM에 전달할 형태로 데이터 변환

### 4. LLM Client (안정)
- 액션 생성 및 페이지 평가 프롬프트 관리
- LLM과의 통신을 담당

### 5. Orchestrator (진행 중)
사용자 채팅을 받아 브라우저 제어가 필요하다고 판단되면 다음 단계를 반복 수행합니다:
1. 목표와 계획 Step을 수립
2. Step별 명령을 ActionMCP로 전달
3. Chrome Extension에서 페이지 로딩 완료 이벤트 발생
4. ActionMCP가 DOM을 캡쳐하여 Orchestrator로 전달
5. DOM Processor를 이용해 현재 단계가 목표 달성에 적합한지 평가
6. LLM에게 로그인 페이지 여부, 목표 달성, 다음 액션 필요 여부를 질의
7. 결과에 따라 다음 Step 진행, 뒤로 가기, 계획 수정 여부 결정

## 기존 기능 요약
- **DOM 텍스처 추출 및 임베딩 기반 분석** (`intfloat/multilingual-e5-base` + FAISS)
- **Graph Line 실행**: 채팅 분석 → 계획 수립 → 액션 실행 → 결과 평가 → 계획 조정
- **Chrome Extension UI**: 사이드 패널, 실시간 로그, WebSocket 통신
- **성능 최적화**: DOM 청킹, 조기 종료, 캐싱, 병렬 처리
- **안정성**: 에러 처리, 재시도 로직, 로그인 감지, 상태 복원

## 진행 상태 및 필요한 작업
- [x] Chrome Extension 기본 기능 구현
- [x] DOM Processor 및 LLM Client 개발 완료
- [ ] ActionMCP ↔ Chrome Extension DOM 캡쳐 및 제어 API 마무리
- [ ] Orchestrator의 목표/계획 수립 로직 정교화
- [ ] 페이지 로딩 완료 이벤트와 DOM 전달 흐름 통합
- [ ] 로그인 페이지 감지 및 뒤로가기 등 내비게이션 처리
- [ ] 추가 액션 타입 및 다국어 프롬프트 최적화

## ActionMCP ↔ Chrome Extension 연동 메시지

- `LOAD_COMPLETE`: Extension → ActionMCP, 페이지 로딩 완료 알림
- `CAPTURE_DOM`: ActionMCP → Extension, DOM 스냅샷 요청
- `DOM_DATA`: Extension → ActionMCP, 캡처된 DOM 전달
- `EXECUTE_ACTION`: ActionMCP → Extension, 클릭/입력 등 브라우저 제어 명령
  - Payload:
    ```json
    {
      "type": "action",
      "step": <int>,
      "action": {
        "action": "click|fill|goto|hover|waitUntil|end",
        "selector": "<css>",
        "text": "<optional>",
        "value": "<optional>",
        "url": "<optional>",
        "timeout": 1000
      }
    }
    ```
- `google_search` 액션은 내부적으로 `goto`로 변환됩니다.
- `ACTION_RESULT`: Extension → ActionMCP, 명령 수행 결과 전달
- `PING`/`PONG`: 양방향, 연결 상태 확인

## 디렉토리 구조
```
web-agent/
├── extension/      # Chrome Extension 소스
├── server/         # DOM Processor와 LLM Client 등이 포함된 서버 모듈
└── README_v2.md
```

## 라이선스
MIT License
