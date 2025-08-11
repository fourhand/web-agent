if (!window.mcpAgentInjected) {
  window.mcpAgentInjected = true;

  const EXTENSION_UI_ID = "mcp-ui";
  const MAX_STEPS = 10;
  
  // 통합된 Extension 컨텍스트 관리
  class ExtensionContext {
    constructor() {
      this.sessionId = this.generateUUID();
      this.currentGoal = "";
      this.currentPlan = [];
      this.actionHistory = [];
      this.conversationHistory = [];
      this.step = 0;
      this.lastDomSnapshot = "";
      this.createdAt = Date.now();
      
      // 진행 상태 관리
      this.status = "idle"; // idle, planning, executing, waiting_for_page, evaluating, completed
      this.lastActionType = null; // goto, click, fill 등
      this.expectedPageChange = false; // 페이지 변경이 예상되는지
      this.waitingForEvaluation = false; // 평가 대기 중인지
      
      this.restore();
    }
    
    generateUUID() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    }
    
    restore() {
      const saved = localStorage.getItem("mcp-context");
      if (saved) {
        try {
          const data = JSON.parse(saved);
          this.sessionId = data.sessionId || this.sessionId;
          this.currentGoal = data.currentGoal || "";
          this.currentPlan = data.currentPlan || [];
          this.actionHistory = data.actionHistory || [];
          this.conversationHistory = data.conversationHistory || [];
          this.step = data.step || 0;
          this.lastDomSnapshot = data.lastDomSnapshot || "";
          this.createdAt = data.createdAt || Date.now();
          
          // 진행 상태 복원
          this.status = data.status || "idle";
          this.lastActionType = data.lastActionType || null;
          this.expectedPageChange = data.expectedPageChange || false;
          this.waitingForEvaluation = data.waitingForEvaluation || false;
          
          console.log("🔄 컨텍스트 복원:", {
            goal: this.currentGoal,
            step: this.step,
            actionsCount: this.actionHistory.length,
            planCount: this.currentPlan.length,
            conversationsCount: this.conversationHistory.length,
            status: this.status,
            lastActionType: this.lastActionType,
            expectedPageChange: this.expectedPageChange,
            waitingForEvaluation: this.waitingForEvaluation
          });
        } catch (e) {
          console.error("❌ 컨텍스트 복원 실패:", e);
        }
      }
    }
    
    save() {
      const data = {
        sessionId: this.sessionId,
        currentGoal: this.currentGoal,
        currentPlan: this.currentPlan,
        actionHistory: this.actionHistory,
        conversationHistory: this.conversationHistory,
        step: this.step,
        lastDomSnapshot: this.lastDomSnapshot,
        createdAt: this.createdAt,
        updatedAt: Date.now(),
        
        // 진행 상태 저장
        status: this.status,
        lastActionType: this.lastActionType,
        expectedPageChange: this.expectedPageChange,
        waitingForEvaluation: this.waitingForEvaluation
      };
      
      localStorage.setItem("mcp-context", JSON.stringify(data));
      
      // 하위 호환성을 위해 기존 키들도 유지
      localStorage.setItem("mcp-goal", this.currentGoal);
      localStorage.setItem("mcp-actionHistory", JSON.stringify(this.actionHistory));
      localStorage.setItem("mcp-currentPlan", JSON.stringify(this.currentPlan));
    }
    
    // 상태 관리 메서드들
    setStatus(status, details = {}) {
      console.log(`🔄 상태 변경: ${this.status} → ${status}`, details);
      this.status = status;
      this.lastActionType = details.actionType || this.lastActionType;
      this.expectedPageChange = details.expectedPageChange || false;
      this.waitingForEvaluation = details.waitingForEvaluation || false;
      this.save();
    }
    
    shouldSendDomOnPageLoad() {
      console.log("🤔 페이지 로드 시 DOM 전송 여부 판단:");
      console.log(`   - 상태: ${this.status}`);
      console.log(`   - 목표: ${this.currentGoal}`);
      console.log(`   - 페이지 변경 예상: ${this.expectedPageChange}`);
      console.log(`   - 평가 대기: ${this.waitingForEvaluation}`);
      console.log(`   - 마지막 액션: ${this.lastActionType}`);
      console.log(`   - 액션 히스토리: ${this.actionHistory.length}개`);
      console.log(`   - 계획: ${this.currentPlan.length}개`);
      
      // 목표가 없으면 전송하지 않음
      if (!this.currentGoal) {
        console.log("❌ 목표가 없어서 DOM 전송하지 않음");
        return false;
      }
      
      // 완료된 상태면 전송하지 않음
      if (this.status === "completed") {
        console.log("❌ 작업이 완료되어 DOM 전송하지 않음");
        return false;
      }
      
      // goto 액션 후 페이지 변경이 예상되는 경우
      if (this.expectedPageChange && this.lastActionType === "goto") {
        console.log("✅ goto 액션 후 페이지 변경 - 평가 모드로 DOM 전송");
        return "evaluation";
      }
      
      // 평가 대기 중인 경우
      if (this.waitingForEvaluation) {
        console.log("✅ 평가 대기 중 - 평가 모드로 DOM 전송");
        return "evaluation";
      }
      
      // 실행 중이거나 계획이 있는 경우
      if (this.status === "executing" && (this.actionHistory.length > 0 || this.currentPlan.length > 0)) {
        console.log("✅ 실행 중 - 일반 모드로 DOM 전송");
        return "normal";
      }
      
      // 기본적으로 목표가 있으면 전송
      if (this.currentGoal) {
        console.log("✅ 목표가 있어서 일반 모드로 DOM 전송");
        return "normal";
      }
      
      console.log("❌ 조건에 맞지 않아 DOM 전송하지 않음");
      return false;
    }
    
    addAction(action) {
      this.actionHistory.push({
        ...action,
        timestamp: Date.now(),
        step: this.step
      });
      this.step++;
      this.save();
    }
    
    addConversation(role, content) {
      this.conversationHistory.push({
        role,
        content,
        timestamp: Date.now()
      });
      
      // 최근 20개만 유지
      if (this.conversationHistory.length > 20) {
        this.conversationHistory = this.conversationHistory.slice(-20);
      }
      
      this.save();
    }
    
    setGoal(goal) {
      console.log("🎯 setGoal() 호출:", goal);
      this.currentGoal = goal;
      this.step = 0;
      this.actionHistory = [];
      this.currentPlan = [];
      this.conversationHistory = [];
      this.addConversation('user', goal);
      
      // 새 목표 시작 시 상태 설정
      this.setStatus("planning", { actionType: null, expectedPageChange: false });
      
      console.log("✅ setGoal() 완료:", this.currentGoal);
    }
    
    setPlan(plan) {
      this.currentPlan = plan;
      this.save();
    }
    
    clear() {
      this.sessionId = this.generateUUID();
      this.currentGoal = "";
      this.currentPlan = [];
      this.actionHistory = [];
      this.conversationHistory = [];
      this.step = 0;
      this.lastDomSnapshot = "";
      this.createdAt = Date.now();
      
      localStorage.removeItem("mcp-context");
      localStorage.removeItem("mcp-goal");
      localStorage.removeItem("mcp-actionHistory");
      localStorage.removeItem("mcp-currentPlan");
      localStorage.removeItem("mcp-lastDomSnapshot");
      
      this.save();
    }
    
    getContextForServer() {
      return {
        sessionId: this.sessionId,
        goal: this.currentGoal,
        step: this.step,
        plan: this.currentPlan,
        lastAction: this.actionHistory[this.actionHistory.length - 1] || null,
        conversationHistory: this.conversationHistory.slice(-5), // 최근 5개만
        totalActions: this.actionHistory.length
      };
    }
  }
  
  // 전역 컨텍스트 인스턴스
  const context = new ExtensionContext();
  
  // 하위 호환성을 위한 변수들 (기존 코드에서 사용)
  let actionHistory = context.actionHistory;
  let currentPlan = context.currentPlan;
  let lastDomSnapshot = context.lastDomSnapshot;
  
  // 페이지 로드 완료 로그
  console.log("📄 페이지 로드 완료 - 상태 확인");
  
  // 하위 호환성 함수들
  function saveContext() {
    context.save();
  }
  
  function restoreContext() {
    context.restore();
    // 변수 동기화
    actionHistory = context.actionHistory;
    currentPlan = context.currentPlan;
    lastDomSnapshot = context.lastDomSnapshot;
  }

  const ws = new WebSocket("ws://localhost:8000/ws");
  console.log("🔌 WebSocket connecting...");
  
  // 페이지 로드 시 컨텍스트 복원
  restoreContext();

  // === UI 생성 ===
  const ui = document.createElement("div");
  ui.id = EXTENSION_UI_ID;
  ui.style = "position:fixed;bottom:20px;right:20px;width:340px;padding:10px;background:rgba(255,255,255,0.95);border:1px solid #ccc;border-radius:10px;z-index:999999;font-family:sans-serif;";
  ui.tabIndex = -1;

  const log = document.createElement("div");
  log.style = "max-height:200px;overflow-y:auto;margin-bottom:10px;font-size:13px;color:#000;";
  ui.appendChild(log);

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "명령어 입력...";
  input.style = "width:calc(100% - 60px);padding:8px;border:1px solid #aaa;border-radius:6px;box-sizing:border-box;background:#fff;color:#000;caret-color:#000;";
  ui.appendChild(input);

  // 전송 버튼 추가
  const sendButton = document.createElement("button");
  sendButton.textContent = "전송";
  sendButton.style = "width:50px;margin-left:8px;padding:8px;border:1px solid #aaa;border-radius:6px;background:#007bff;color:#fff;cursor:pointer;font-size:13px;";
  sendButton.addEventListener("click", async (e) => {
    e.stopPropagation();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    
    // 컨텍스트에 새로운 목표 설정
    console.log("🎯 목표 설정 시도:", message);
    context.setGoal(message);
    console.log("✅ 목표 설정 완료:", context.currentGoal);
    console.log("📊 컨텍스트 상태:", {
      goal: context.currentGoal,
      step: context.step,
      actionCount: context.actionHistory.length
    });
    
    // 하위 호환성을 위해 변수 동기화
    actionHistory = context.actionHistory;
    currentPlan = context.currentPlan;
    
    logMessage(`👉 ${message}`);

    console.log("⏳ WebSocket 준비 대기 중...");
    await waitUntilReady();
    console.log("✅ WebSocket 준비 완료");
    // 서버에는 단순한 init 메시지만 전송 (컨텍스트는 DOM과 함께 전송)
    console.log("📤 init 메시지 전송:", { type: "init", message });
    ws.send(JSON.stringify({ type: "init", message }));
    console.log("🚀 sendDom() 호출 예정");
    
    // 잠시 대기 후 DOM 전송
    setTimeout(() => {
      console.log("⏰ setTimeout으로 sendDom() 재호출");
      sendDom();
    }, 1000);
    
    sendDom();
  });
  ui.appendChild(sendButton);

  const clearButton = document.createElement("button");
  clearButton.textContent = "Clear";
  clearButton.style = "width:100%;margin-top:8px;padding:8px;border:1px solid #aaa;border-radius:6px;background:#f0f0f0;color:#333;cursor:pointer;font-size:13px;";
  clearButton.addEventListener("click", async (e) => {
    e.stopPropagation();
    
    // 컨텍스트 완전 초기화
    context.clear();
    
    // 하위 호환성을 위해 변수 동기화
    actionHistory = context.actionHistory;
    currentPlan = context.currentPlan;
    lastDomSnapshot = context.lastDomSnapshot;
    
    // UI 초기화
    log.innerHTML = "";
    input.value = "";
    
    logMessage("🧹 모든 컨텍스트가 초기화되었습니다.");
  });
  ui.appendChild(clearButton);

  // === 포커스 추적 ===
  let isInputFocused = false;
  input.addEventListener("focus", () => isInputFocused = true);
  input.addEventListener("blur", () => isInputFocused = false);

  // === 키보드 이벤트 차단 로직 (채팅 입력 허용 + 사이트 전달 차단) ===
  ['keydown', 'keyup', 'keypress'].forEach(eventType => {
    document.addEventListener(eventType, (e) => {
      // 입력창에서만 입력 허용 (입력은 되지만 전파는 막음)
      if (isInputFocused) {
        // Enter 키는 예외 처리 (전송 기능을 위해)
        if (e.key === "Enter") {
          return;
        }
        e.stopPropagation();
        return;
      }

      // UI 내부인 경우 전체 차단
      if (ui.contains(e.target)) {
        e.stopPropagation();
        e.preventDefault();
      }
    }, true);
  });

  // === 한글 입력 처리 ===
  let isComposing = false;
  input.addEventListener("compositionstart", () => isComposing = true);
  input.addEventListener("compositionend", () => isComposing = false);

  // === Enter 입력 처리 ===
  input.addEventListener("keydown", async (e) => {
    if (e.key === "Enter" && !isComposing) {
      e.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      input.value = '';
      
      // 컨텍스트에 새로운 목표 설정
      console.log("🎯 [Enter] 목표 설정 시도:", message);
      context.setGoal(message);
      console.log("✅ [Enter] 목표 설정 완료:", context.currentGoal);
      console.log("📊 [Enter] 컨텍스트 상태:", {
        goal: context.currentGoal,
        step: context.step,
        actionCount: context.actionHistory.length
      });
      
      // 하위 호환성을 위해 변수 동기화
      actionHistory = context.actionHistory;
      currentPlan = context.currentPlan;
      
      logMessage(`👉 ${message}`);

      console.log("⏳ [Enter] WebSocket 준비 대기 중...");
      await waitUntilReady();
      console.log("✅ [Enter] WebSocket 준비 완료");
      console.log("📤 [Enter] init 메시지 전송:", { type: "init", message });
      ws.send(JSON.stringify({ type: "init", message }));
      console.log("🚀 [Enter] sendDom() 호출 예정");
      sendDom();
    }
  });

  // === WebSocket 연결 ===
  const waitUntilReady = () =>
    new Promise(resolve => {
      console.log("🔍 WebSocket readyState:", ws.readyState);
      if (ws.readyState === 1) {
        console.log("✅ WebSocket 이미 연결됨");
        return resolve();
      }
      console.log("⏳ WebSocket 연결 대기 중...");
      ws.addEventListener("open", () => {
        console.log("✅ WebSocket connected.");
        
        // 페이지 로드 후 진행 중인 작업이 있으면 자동 재개
        setTimeout(async () => {
          // 컨텍스트 복원 및 동기화
          context.restore();
          actionHistory = context.actionHistory;
          currentPlan = context.currentPlan;
          lastDomSnapshot = context.lastDomSnapshot;
          
          console.log("🔍 재개 검사:", {
            goal: context.currentGoal,
            step: context.step,
            actionHistoryLength: context.actionHistory.length,
            hasGoal: !!context.currentGoal,
            hasActions: context.actionHistory.length > 0
          });
          
          // 현재 상태를 채팅으로 표시 (UI가 생성된 후)
          setTimeout(() => {
            showCurrentStatus();
          }, 500);
          
          // 상태 기반 DOM 전송 판단
          const shouldSend = context.shouldSendDomOnPageLoad();
          
          if (shouldSend === "evaluation") {
            console.log("📊 평가 모드로 DOM 전송");
            logMessage(`📊 상황 평가: ${context.currentGoal} (단계: ${context.step})`);
            
            setTimeout(() => {
              sendDomForEvaluation();
            }, 1000);
            
          } else if (shouldSend === "normal") {
            console.log("🔄 일반 모드로 DOM 전송");
            logMessage(`🔄 작업 재개: ${context.currentGoal} (단계: ${context.step})`);
            
            setTimeout(() => {
              sendDom();
            }, 1000);
            
          } else if (shouldSend === false) {
            console.log("⏸️ DOM 전송하지 않음 - 대기 상태");
            if (context.currentGoal) {
              logMessage(`⏸️ 대기 중: ${context.currentGoal}`);
            }
          }
        }, 2000); // 페이지 로딩 완료를 위해 2초 대기
        
        resolve();
      });
    });

  ws.onmessage = async (event) => {
    console.log("📩 WebSocket 원본 데이터:", event.data);
    const data = JSON.parse(event.data);
    console.log("📩 WebSocket 파싱된 데이터:", data);

    if (data.type === "intent_analysis") {
      // 의도 분석 결과 처리
      logMessage(`🧠 ${data.message} (신뢰도: ${Math.round(data.confidence * 100)}%)`);
      
      if (data.intent === "question") {
        // 질문인 경우 DOM 정보와 함께 질문 전송
        setTimeout(() => {
          sendQuestion();
        }, 1000);
      }
    } else if (data.type === "plan") {
      // Planning 결과 수신
      context.setPlan(data.plan);
      
      // 계획 수립 완료 상태로 변경
      context.setStatus("executing", { actionType: null, expectedPageChange: false });
      
      // 하위 호환성을 위해 변수 동기화
      currentPlan = context.currentPlan;
      
      logMessage(`🧠 계획 수립 완료: ${currentPlan.length}단계`);
      currentPlan.forEach((step, index) => {
        logMessage(`  ${index + 1}. ${step.action} - ${step.target} (${step.reason})`);
      });
      
      // 계획 수립 완료 후 첫 번째 액션 실행을 위해 DOM 재전송
      console.log("🚀 계획 완료, 첫 번째 액션 실행을 위해 DOM 재전송");
      setTimeout(() => {
        sendDom();
      }, 1000);
    } else if (data.type === "action") {
      // 액션 실행 전 상태 업데이트
      const actionType = data.action.action;
      const expectedPageChange = (actionType === "goto");
      
      context.setStatus("executing", { 
        actionType: actionType, 
        expectedPageChange: expectedPageChange,
        waitingForEvaluation: expectedPageChange // goto의 경우 평가 대기
      });
      
      // 컨텍스트에 액션 추가
      context.addAction(data.action);
      
      // 하위 호환성을 위해 변수 동기화
      actionHistory = context.actionHistory;
      saveContext(); // 컨텍스트 저장
      logMessage(`🤖 액션(${actionHistory.length}): ${JSON.stringify(data.action)}`);
      console.log("🔍 액션 상세 정보:", data.action);
      console.log("🔍 action.url 존재 여부:", !!data.action.url);
      console.log("🔍 action.value 존재 여부:", !!data.action.value);

      if (actionHistory.length > MAX_STEPS) {
        const cont = confirm("10단계 이상 수행 중입니다. 계속 진행할까요?");
        if (!cont) {
          logMessage("⛔ 사용자 중단");
          localStorage.removeItem("mcp-goal");
          actionHistory = [];
          currentPlan = null;
          return;
        }
        actionHistory = [];
      }

      console.log("🔍 executeMcp 호출 전 액션:", data.action);
      console.log("🔍 action.url 값:", data.action.url);
      console.log("🔍 action.value 값:", data.action.value);
      await executeMcp([data.action]);

      // goto 액션의 경우 페이지 이동으로 인해 이 코드가 실행되지 않음
      if (data.action.action === 'goto') {
        logMessage("🌐 페이지 이동 중... 새 페이지에서 자동 재개됨");
        return;
      }

      setTimeout(() => {
        const current = snapshotDom();
        if (current !== lastDomSnapshot) {
          logMessage("🔄 DOM 변화 감지 → 재전송");
          sendDom();
        } else {
          logMessage("⏳ DOM 변화 없음 → 대기");
        }
      }, 3000);

    } else if (data.type === "end") {
      logMessage("🎯 완료됨");
      localStorage.removeItem("mcp-goal");
      actionHistory = [];
      currentPlan = null;
    } else if (data.type === "answer") {
      // 질문 답변 처리
      logMessage(`❓ 질문: ${data.question}`);
      logMessage(`💡 답변: ${data.answer}`);
      localStorage.removeItem("mcp-goal"); // 질문 완료 후 목표 제거
    } else if (data.type === "clear_confirmed") {
      // 서버 컨텍스트 초기화 확인
      logMessage(`✅ ${data.message}`);
    } else if (data.type === "resume_confirmed") {
      // 작업 재개 확인
      logMessage(`🔄 ${data.message}`);
      logMessage(`🎯 목표: ${data.goal} (단계: ${data.step})`);
    } else if (data.type === "error") {
      logMessage(`❌ 오류: ${data.detail}`);
    }
  };

  // === 화면 캡처 기능 ===
  async function captureScreen() {
    try {
      console.log('📸 화면 캡처 시작...');
      
      // Canvas API를 사용한 화면 캡처 시도
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      
      // 뷰포트 크기로 캔버스 설정
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      
      console.log(`📐 캔버스 크기: ${canvas.width}x${canvas.height}`);
      
      // 배경을 흰색으로 설정
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // DOM 요소들을 캔버스에 그리기 (개선된 시각적 와이어프레임)
      const elements = document.querySelectorAll('button, input, a, div, span, img, h1, h2, h3, h4, h5, h6, p, ul, ol, li, form, table, select, textarea');
      console.log(`🎯 캡처할 요소 수: ${elements.length}`);
      
      let drawnElements = 0;
      elements.forEach(el => {
        if (el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 5 && rect.height > 5) { // 최소 크기 필터
            
            // 요소 타입별로 다른 스타일 적용
            const tagName = el.tagName.toLowerCase();
            
            // 기본값 설정
            ctx.lineWidth = 1;
            ctx.setLineDash([]);
            
            // 요소 타입별 스타일 적용
            if (tagName === 'button') {
              // 버튼: 파란색 배경 + 굵은 테두리
              ctx.fillStyle = '#e3f2fd';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#1976d2';
              ctx.lineWidth = 2;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#1976d2';
              ctx.font = 'bold 12px Arial';
              
            } else if (tagName === 'input' || tagName === 'textarea') {
              // 입력창: 연한 회색 배경 + 실선 테두리
              ctx.fillStyle = '#f8f9fa';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#6c757d';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#495057';
              ctx.font = '11px Arial';
              
            } else if (tagName === 'select') {
              // 드롭다운: 노란색 배경
              ctx.fillStyle = '#fff3cd';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#856404';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#856404';
              ctx.font = '11px Arial';
              
            } else if (tagName === 'a') {
              // 링크: 파란색 점선 테두리
              ctx.strokeStyle = '#0d6efd';
              ctx.lineWidth = 1;
              ctx.setLineDash([3, 3]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#0d6efd';
              ctx.font = '11px Arial';
              
            } else if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName)) {
              // 제목: 주황색 배경 + 굵은 테두리
              ctx.fillStyle = '#fff3e0';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#f57c00';
              ctx.lineWidth = 2;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#f57c00';
              const fontSize = tagName === 'h1' ? 16 : tagName === 'h2' ? 14 : 13;
              ctx.font = `bold ${fontSize}px Arial`;
              
            } else if (tagName === 'img') {
              // 이미지: 초록색 배경 + 이미지 표시
              ctx.fillStyle = '#e8f5e8';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#4caf50';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#4caf50';
              ctx.font = '12px Arial';
              const centerX = rect.left + rect.width / 2 - 15;
              const centerY = rect.top + rect.height / 2 + 4;
              ctx.fillText('[IMG]', centerX, centerY);
              ctx.fillStyle = '#2e7d32';
              ctx.font = '10px Arial';
              
            } else if (['ul', 'ol', 'li'].includes(tagName)) {
              // 리스트: 연한 보라색
              ctx.strokeStyle = '#9c27b0';
              ctx.lineWidth = 1;
              ctx.setLineDash([2, 2]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#9c27b0';
              ctx.font = '11px Arial';
              
            } else if (tagName === 'form') {
              // 폼: 연한 파란색 배경
              ctx.fillStyle = '#f0f8ff';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#4682b4';
              ctx.lineWidth = 1;
              ctx.setLineDash([5, 3]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#4682b4';
              ctx.font = '11px Arial';
              
            } else {
              // 기타 요소: 연한 회색
              ctx.strokeStyle = '#dee2e6';
              ctx.lineWidth = 0.5;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#6c757d';
              ctx.font = '10px Arial';
            }
            
            // 텍스트 추가
            const text = el.innerText || el.placeholder || el.value || el.alt || el.title || '';
            if (text.trim() && rect.width > 20 && rect.height > 10) {
              const maxWidth = rect.width - 6;
              const maxChars = Math.floor(maxWidth / 6);
              const truncatedText = text.trim().substring(0, maxChars);
              
              if (truncatedText) {
                const textX = rect.left + 3;
                const textY = rect.top + (rect.height > 20 ? 16 : rect.height - 2);
                ctx.fillText(truncatedText, textX, textY);
              }
            }
            
            drawnElements++;
          }
        }
      });
      
      console.log(`✅ 그려진 요소 수: ${drawnElements}`);
      
      // Canvas를 base64로 변환
      const dataURL = canvas.toDataURL('image/png');
      console.log('✅ 화면 캡처 성공');
      console.log(`📊 데이터 URL 길이: ${dataURL.length} characters`);
      console.log(`📊 데이터 URL 접두사: ${dataURL.substring(0, 50)}...`);
      
      return dataURL;
      
    } catch (error) {
      console.log('❌ 화면 캡처 실패:', error);
      return null;
    }
  }

  // === 질문 전송 ===
  async function sendQuestion() {
    const goal = localStorage.getItem("mcp-goal");
    if (!goal) {
      logMessage("⚠️ 질문 없음: 전송 안 함");
      return;
    }
    
    const dom = summarizeDom();
    const image = await captureScreen();
    
    const payload = {
      type: "question",
      message: goal,
      dom,
      image: image
    };
    
    logMessage("📤 질문 전송");
    ws.send(JSON.stringify(payload));
  }

  // === DOM 전송 (상황 평가용) ===
  async function sendDomForEvaluation() {
    console.log("📊 sendDomForEvaluation() 호출됨 - 상황 평가 모드");
    console.log("🔍 context 상태:", {
      goal: context.currentGoal,
      step: context.step,
      actionCount: context.actionHistory.length,
      planCount: context.currentPlan.length
    });
    
    if (!context.currentGoal) {
      console.log("ℹ️ 목표가 설정되지 않아 평가를 건너뜁니다.");
      return;
    }
    
    const dom = summarizeDom();
    const image = await captureScreen();
    
    // 컨텍스트 업데이트
    context.lastDomSnapshot = snapshotDom();
    
    const payload = {
      type: "dom_with_image_evaluation", // 평가 모드 표시
      message: context.currentGoal,
      dom,
      image: image,
      context: context.getContextForServer(),
      evaluationMode: true // 평가 모드 플래그
    };
    
    logMessage(`📊 상황 평가 요청 (단계: ${context.step})`);
    console.log("📊 평가용 컨텍스트:", context.getContextForServer());
    ws.send(JSON.stringify(payload));
    
    context.save();
  }

  // === DOM 전송 ===
  async function sendDom() {
    console.log("🔍 sendDom() 호출됨");
    console.log("🔍 context.currentGoal:", context.currentGoal);
    console.log("🔍 context 전체 상태:", {
      sessionId: context.sessionId,
      goal: context.currentGoal,
      step: context.step,
      actionCount: context.actionHistory.length
    });
    
    if (!context.currentGoal) {
      console.log("ℹ️ 목표가 설정되지 않아 DOM 전송을 건너뜁니다. Extension UI에서 목표를 입력하세요.");
      return;
    }
    
    const dom = summarizeDom();
    const image = await captureScreen();
    
    // 이미지 캡처 결과 로깅
    console.log("📸 이미지 캡처 결과:", {
      imageExists: !!image,
      imageType: typeof image,
      imageLength: image ? image.length : 0,
      imagePrefix: image ? image.substring(0, 50) : null
    });
    
    // 컨텍스트 업데이트
    context.lastDomSnapshot = snapshotDom();
    
    const payload = {
      type: "dom_with_image",
      message: context.currentGoal,
      dom,
      image: image,
      context: context.getContextForServer() // 전체 컨텍스트 포함
    };
    
    logMessage(`📤 DOM + 이미지 전송 (단계: ${context.step})`);
    console.log("📤 전송할 컨텍스트:", context.getContextForServer());
    console.log("📤 이미지 데이터 존재:", !!payload.image);
    ws.send(JSON.stringify(payload));
    
    context.save();
  }

  function snapshotDom() {
    return JSON.stringify(summarizeDom());
  }

  // 현재 상태를 채팅으로 표시
  function showCurrentStatus() {
    const currentUrl = window.location.href;
    const statusEmoji = {
      "idle": "⏸️",
      "planning": "🧠", 
      "executing": "🚀",
      "waiting_for_page": "⏳",
      "evaluating": "📊",
      "completed": "✅"
    };
    
    const emoji = statusEmoji[context.status] || "❓";
    
    logMessage("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    logMessage(`🌐 페이지: ${currentUrl}`);
    logMessage(`${emoji} 상태: ${context.status}`);
    
    if (context.currentGoal) {
      logMessage(`🎯 목표: ${context.currentGoal}`);
      logMessage(`📊 진행: ${context.step}단계 (총 ${context.actionHistory.length}개 액션 완료)`);
      
      if (context.currentPlan && context.currentPlan.length > 0) {
        logMessage(`📋 계획: ${context.currentPlan.length}단계`);
        const currentPlanStep = context.currentPlan[context.step] || context.currentPlan[context.currentPlan.length - 1];
        if (currentPlanStep) {
          logMessage(`   → 다음: ${currentPlanStep.action} - ${currentPlanStep.target}`);
        }
      }
      
      if (context.lastActionType) {
        logMessage(`🔧 마지막 액션: ${context.lastActionType}`);
      }
      
      if (context.expectedPageChange) {
        logMessage(`🔄 페이지 변경 예상됨`);
      }
      
      if (context.waitingForEvaluation) {
        logMessage(`⏳ 평가 대기 중`);
      }
      
    } else {
      logMessage(`❌ 목표가 설정되지 않음`);
    }
    
    logMessage("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  }

  function logMessage(text) {
    const div = document.createElement("div");
    div.textContent = text;
    div.style.margin = "4px 0";
    div.style.color = "#000";
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function summarizeDom() {
    return Array.from(document.querySelectorAll('button, input, a[href], textarea, select, li, div, span'))
      .filter(el => el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`))
      .map(el => ({
        tag: el.tagName.toLowerCase(),
        text: el.innerText || el.placeholder || el.value || '',
        id: el.id,
        name: el.name,
        type: el.type,
        class: el.className,
        selector: getSelector(el)
      }));
  }

  function getSelector(el) {
    // 우선순위: id > name > class > tag
    if (el.id) return `#${el.id}`;
    if (el.name) return `${el.tagName.toLowerCase()}[name='${el.name}']`;
    if (el.type) return `${el.tagName.toLowerCase()}[type='${el.type}']`;
    if (el.className) {
      const classes = el.className.split(' ').filter(c => c).join('.');
      if (classes) return `${el.tagName.toLowerCase()}.${classes}`;
    }
    return el.tagName.toLowerCase();
  }

  function isBrowserUIAction(action) {
    // 브라우저 UI 요소를 대상으로 하는 액션인지 확인
    const browserUIKeywords = [
      '주소창', 'address bar', 'url bar', 'location bar',
      '뒤로가기', 'back button', '앞으로가기', 'forward button',
      '새로고침', 'refresh button', 'reload button',
      '탭', 'tab', '북마크', 'bookmark',
      'browser ui', 'not in dom', 'browser element'
    ];
    
    const targetText = (action.selector || action.target || action.text || '').toLowerCase();
    
    // 키워드 매칭
    for (const keyword of browserUIKeywords) {
      if (targetText.includes(keyword)) {
        return true;
      }
    }
    
    // focus, fill, press 액션이 DOM에 없는 요소를 대상으로 하는 경우
    if (['focus', 'fill', 'press'].includes(action.action)) {
      if (targetText.includes('주소') || targetText.includes('address') || 
          targetText.includes('browser') || targetText.includes('not in dom')) {
        return true;
      }
    }
    
    return false;
  }

  async function executeMcp(actions) {
    for (const action of actions) {
      console.log("🚀 Executing MCP action:", action);
      console.log("🔍 액션 타입:", typeof action);
      console.log("🔍 액션 키들:", Object.keys(action));
      console.log("🔍 action.url 타입:", typeof action.url);
      console.log("🔍 action.url 값:", action.url);
      
      // 브라우저 UI 액션 차단
      if (isBrowserUIAction(action)) {
        logMessage(`🚫 브라우저 UI 제어 불가: ${action.action} - ${action.selector || action.target || 'unknown'}`);
        logMessage(`💡 대신 'goto' 액션으로 직접 페이지 이동을 사용하세요.`);
        continue;
      }
      
      try {
        switch (action.action) {
          case "goto":
            console.log("🔍 goto 액션 디버깅:", action);
            if (action.value) {
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = action.value;
              logMessage(`✅ 페이지 이동: ${action.value}`);
            } else if (action.url) {
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = action.url;
              logMessage(`✅ 페이지 이동: ${action.url}`);
            } else if (action.selector) {
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = action.selector;
              logMessage(`✅ 페이지 이동: ${action.selector}`);
            } else {
              logMessage(`❌ goto 실패: URL이 지정되지 않음`);
              logMessage(`🔍 액션 내용: ${JSON.stringify(action)}`);
            }
            break;
            
          case "google_search":
            console.log("🔍 google_search 액션 디버깅:", action);
            if (action.query) {
              const searchQuery = encodeURIComponent(action.query);
              const googleSearchUrl = `https://www.google.com/search?q=${searchQuery}`;
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = googleSearchUrl;
              logMessage(`🔍 Google 검색: ${action.query}`);
              logMessage(`✅ 검색 페이지로 이동: ${googleSearchUrl}`);
            } else {
              logMessage(`❌ Google 검색 실패: 검색어가 지정되지 않음`);
              logMessage(`🔍 액션 내용: ${JSON.stringify(action)}`);
            }
            break;
            
          case "click":
            const clickEl = findElement(action.selector, action.text);
            if (clickEl) {
              clickEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
              await new Promise(resolve => setTimeout(resolve, 500));
              clickEl.click();
              logMessage(`✅ 클릭 성공: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
            } else {
              logMessage(`❌ 클릭 실패: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
              console.warn("❌ Click element not found:", action.selector, action.text);
              
              // 대안 제시
              const alternatives = findAlternativeElements(action.selector, action.text);
              if (alternatives.length > 0) {
                logMessage(`💡 대안 요소들 발견: ${alternatives.length}개`);
                alternatives.slice(0, 3).forEach((alt, i) => {
                  logMessage(`  ${i + 1}. ${alt.tag}${alt.class ? '.' + alt.class : ''} - "${alt.text}"`);
                });
                
                // 사용자에게 대안 선택 옵션 제공
                const useAlternative = confirm(`요소를 찾지 못했습니다. 대안 요소를 사용하시겠습니까?\n\n${alternatives[0].tag} - "${alternatives[0].text}"`);
                if (useAlternative && alternatives[0]) {
                  const altEl = document.querySelector(alternatives[0].selector);
                  if (altEl) {
                    altEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    await new Promise(resolve => setTimeout(resolve, 500));
                    altEl.click();
                    logMessage(`✅ 대안 요소 클릭 성공: ${alternatives[0].selector}`);
                  }
                }
              }
            }
            break;
            
          case "fill":
            const fillEl = findElement(action.selector, action.text);
            if (fillEl && action.value) {
              fillEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
              await new Promise(resolve => setTimeout(resolve, 500));
              fillEl.focus();
              fillEl.value = action.value;
              fillEl.dispatchEvent(new Event('input', { bubbles: true }));
              fillEl.dispatchEvent(new Event('change', { bubbles: true }));
              logMessage(`✅ 입력 성공: ${action.selector} = "${action.value}"`);
            } else {
              logMessage(`❌ 입력 실패: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
              console.warn("❌ Fill element not found:", action.selector, action.text);
            }
            break;
            
          case "hover":
            const hoverEl = findElement(action.selector, action.text);
            if (hoverEl) {
              hoverEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
              await new Promise(resolve => setTimeout(resolve, 500));
              hoverEl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
              logMessage(`✅ 호버 성공: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
            } else {
              logMessage(`❌ 호버 실패: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
              console.warn("❌ Hover element not found:", action.selector, action.text);
            }
            break;
            
          case "waitUntil":
            if (action.condition) {
              console.log("⏳ Waiting for condition:", action.condition);
              const timeout = action.timeout || 5000;
              const startTime = Date.now();
              
              while (Date.now() - startTime < timeout) {
                const conditionEl = document.querySelector(action.condition);
                if (conditionEl) {
                  console.log("✅ Condition met:", action.condition);
                  break;
                }
                await new Promise(resolve => setTimeout(resolve, 100));
              }
            }
            break;
            
          default:
            console.warn("⚠️ Unknown action:", action.action);
        }
      } catch (error) {
        console.error("❌ Error executing action:", error);
      }
    }
  }

  function findElement(selector, text) {
    if (!selector) return null;
    
    let elements = [];
    
    try {
      // 1. CSS 선택자로 직접 검색
      elements = document.querySelectorAll(selector);
      
      // 2. 선택자가 실패하면 더 유연한 검색 시도
      if (elements.length === 0) {
        console.log(`🔍 CSS 선택자 실패: ${selector}, 유연한 검색 시도...`);
        
        // 태그와 클래스 기반 검색
        const tagMatch = selector.match(/^(\w+)/);
        const classMatch = selector.match(/\.([\w-]+)/);
        
        if (tagMatch && classMatch) {
          const tag = tagMatch[1];
          const className = classMatch[1];
          elements = document.querySelectorAll(`${tag}.${className}`);
        } else if (tagMatch) {
          // 태그만으로 검색
          elements = document.querySelectorAll(tagMatch[1]);
        }
      }
      
      // 3. 텍스트 기반 필터링
      if (text) {
        elements = Array.from(elements).filter(el => {
          const elementText = (el.innerText || el.textContent || el.value || '').toLowerCase();
          const searchText = text.toLowerCase();
          return elementText.includes(searchText);
        });
      }
      
      // 4. 추가적인 유연한 검색 (텍스트가 있는 경우)
      if (elements.length === 0 && text) {
        console.log(`🔍 텍스트 기반 검색: "${text}"`);
        const allElements = document.querySelectorAll('*');
        elements = Array.from(allElements).filter(el => {
          const elementText = (el.innerText || el.textContent || el.value || '').toLowerCase();
          const searchText = text.toLowerCase();
          return elementText.includes(searchText) && 
                 (el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' || 
                  el.tagName === 'LI' || el.tagName === 'DIV' || el.tagName === 'SPAN');
        });
      }
      
      // 5. 마지막 수단: 부분 선택자 매칭
      if (elements.length === 0) {
        console.log(`🔍 부분 선택자 매칭 시도: ${selector}`);
        const allElements = document.querySelectorAll('*');
        elements = Array.from(allElements).filter(el => {
          // 클래스명이 포함된 요소 찾기
          if (selector.includes('.') && el.className) {
            const selectorClasses = selector.match(/\.([\w-]+)/g);
            const elementClasses = el.className.split(' ');
            return selectorClasses && selectorClasses.some(cls => 
              elementClasses.includes(cls.replace('.', ''))
            );
          }
          return false;
        });
      }
      
      // 6. 특별한 경우: 메일 리스트 관련 요소들
      if (elements.length === 0 && (selector.includes('mail') || selector.includes('li'))) {
        console.log(`🔍 메일 리스트 특별 검색: ${selector}`);
        
        // 메일 관련 요소들 검색
        const mailElements = document.querySelectorAll('[class*="mail"], [id*="mail"], li, ul');
        elements = Array.from(mailElements).filter(el => {
          // 클릭 가능한 요소인지 확인
          const isClickable = el.tagName === 'A' || el.tagName === 'BUTTON' || 
                             el.onclick || el.getAttribute('role') === 'button' ||
                             el.style.cursor === 'pointer';
          
          // 텍스트가 있는지 확인
          const hasText = el.innerText && el.innerText.trim().length > 0;
          
          return isClickable || hasText;
        });
      }
      
    } catch (error) {
      console.error(`❌ 요소 검색 오류: ${error}`);
      return null;
    }
    
    if (elements.length > 0) {
      console.log(`✅ 요소 발견: ${selector} (${elements.length}개)`);
      return elements[0];
    } else {
      console.warn(`❌ 요소 없음: ${selector}${text ? ` (text: "${text}")` : ''}`);
      
      // 상세한 디버깅 정보 출력
      console.log('🔍 현재 페이지 DOM 분석:');
      console.log('  - URL:', window.location.href);
      console.log('  - 제목:', document.title);
      
      // 유사한 요소들 찾기
      const similarSelectors = [
        'ul', 'li', '.mail_list', '[class*="mail"]', '[id*="mail"]',
        'a', 'button', '[role="button"]', '[onclick]'
      ];
      
      similarSelectors.forEach(sel => {
        const found = document.querySelectorAll(sel);
        if (found.length > 0) {
          console.log(`  - ${sel}: ${found.length}개 발견`);
          found.slice(0, 3).forEach((el, i) => {
            const text = el.innerText?.substring(0, 30) || '';
            const classes = el.className ? `.${el.className.split(' ').join('.')}` : '';
            console.log(`    ${i + 1}. ${el.tagName}${classes} - "${text}"`);
          });
        }
      });
      
      // 메일 관련 요소 특별 검색
      const mailRelated = document.querySelectorAll('[class*="mail"], [id*="mail"], [data-*="mail"]');
      if (mailRelated.length > 0) {
        console.log(`  - 메일 관련 요소: ${mailRelated.length}개`);
        mailRelated.slice(0, 5).forEach((el, i) => {
          console.log(`    ${i + 1}. ${el.tagName} - ${el.className || el.id} - "${el.innerText?.substring(0, 50)}"`);
        });
      }
      
      return null;
    }
  }

  function findAlternativeElements(selector, text) {
    const alternatives = [];
    
    try {
      // 1. 유사한 태그의 요소들 찾기
      const tagMatch = selector.match(/^(\w+)/);
      if (tagMatch) {
        const tag = tagMatch[1];
        const elements = document.querySelectorAll(tag);
        elements.forEach(el => {
          if (el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
            const elementText = (el.innerText || el.textContent || '').trim();
            if (elementText.length > 0) {
              alternatives.push({
                tag: el.tagName.toLowerCase(),
                class: el.className || '',
                text: elementText.substring(0, 50),
                selector: getSelector(el)
              });
            }
          }
        });
      }
      
      // 2. 텍스트 기반 검색
      if (text) {
        const allElements = document.querySelectorAll('a, button, li, div, span');
        allElements.forEach(el => {
          if (el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
            const elementText = (el.innerText || el.textContent || '').toLowerCase();
            const searchText = text.toLowerCase();
            if (elementText.includes(searchText)) {
              alternatives.push({
                tag: el.tagName.toLowerCase(),
                class: el.className || '',
                text: (el.innerText || el.textContent || '').substring(0, 50),
                selector: getSelector(el)
              });
            }
          }
        });
      }
      
      // 3. 클릭 가능한 요소들 찾기
      const clickableElements = document.querySelectorAll('a, button, [role="button"], [onclick]');
      clickableElements.forEach(el => {
        if (el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
          const elementText = (el.innerText || el.textContent || '').trim();
          if (elementText.length > 0) {
            alternatives.push({
              tag: el.tagName.toLowerCase(),
              class: el.className || '',
              text: elementText.substring(0, 50),
              selector: getSelector(el)
            });
          }
        }
      });
      
    } catch (error) {
      console.error('대안 요소 검색 오류:', error);
    }
    
    // 중복 제거 및 정렬
    const uniqueAlternatives = [];
    const seen = new Set();
    
    alternatives.forEach(alt => {
      const key = `${alt.tag}-${alt.text}`;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueAlternatives.push(alt);
      }
    });
    
    return uniqueAlternatives.slice(0, 5); // 최대 5개 반환
  }

  document.body.appendChild(ui);
  console.log("✅ MCP UI injected");
  
  // UI 생성 후 현재 상태 표시
  setTimeout(() => {
    if (context.currentGoal) {
      showCurrentStatus();
    }
  }, 100);
}
