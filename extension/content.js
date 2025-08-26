if (!window.mcpAgentInjected) {
  window.mcpAgentInjected = true;

  const EXTENSION_UI_ID = "mcp-ui";
  const SHOULD_RENDER_UI = (window.top === window.self) && (window.innerWidth >= 320 && window.innerHeight >= 220);
  const MAX_STEPS = 10;
  
  // 와이어프레임 설정 관리
  async function getWireframeSettings() {
    return new Promise((resolve) => {
      chrome.storage.sync.get(['wireframeEnabled'], (result) => {
        resolve({
          enabled: result.wireframeEnabled !== false // 기본값: true
        });
      });
    });
  }
  
  // 사이드패널로부터 메시지 수신
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'settings_changed') {
      logMessage(`🔧 설정 변경: 와이어프레임 ${message.wireframeEnabled ? 'ON' : 'OFF'}`);
    } else if (message.type === 'user_input') {
      logMessage(`👤 사용자 입력: ${message.message}`);
      
      // 사용자 목표 설정 및 자동화 시작
      if (message.message.trim()) {
        context.setGoal(message.message.trim());
        logMessage("🎯 목표 설정됨");
        sendDomWithQuestion(message.message.trim());
      }
    }
    
    sendResponse({success: true});
  });
  
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
    
    async restore() {
      try {
        const result = await chrome.storage.local.get("mcp-context");
        const saved = result["mcp-context"];
        
        if (saved) {
          this.sessionId = saved.sessionId || this.sessionId;
          this.currentGoal = saved.currentGoal || "";
          this.currentPlan = saved.currentPlan || [];
          this.actionHistory = saved.actionHistory || [];
          this.conversationHistory = saved.conversationHistory || [];
          this.step = saved.step || 0;
          this.lastDomSnapshot = saved.lastDomSnapshot || "";
          this.createdAt = saved.createdAt || Date.now();
          
          // 진행 상태 복원
          this.status = saved.status || "idle";
          this.lastActionType = saved.lastActionType || null;
          this.expectedPageChange = saved.expectedPageChange || false;
          this.waitingForEvaluation = saved.waitingForEvaluation || false;
          
          console.log("🔄 컨텍스트 복원 (Cross-Origin Safe):", {
            goal: this.currentGoal,
            step: this.step,
            actionsCount: this.actionHistory.length,
            planCount: this.currentPlan.length,
            conversationsCount: this.conversationHistory.length,
            status: this.status,
            lastActionType: this.lastActionType,
            expectedPageChange: this.expectedPageChange,
            waitingForEvaluation: this.waitingForEvaluation,
            domain: window.location.origin
          });
        } else {
          console.log("📝 새 컨텍스트 시작 (저장된 데이터 없음)");
        }
      } catch (e) {
        console.error("❌ 컨텍스트 복원 실패:", e);
        // Fallback to localStorage for backward compatibility
        console.log("🔄 localStorage 폴백 시도...");
        const saved = localStorage.getItem("mcp-context");
        if (saved) {
          try {
            const data = JSON.parse(saved);
            this.currentGoal = data.currentGoal || "";
            this.currentPlan = data.currentPlan || [];
            this.step = data.step || 0;
            this.status = data.status || "idle";
            console.log("✅ localStorage에서 복원 완료");
          } catch (fallbackError) {
            console.error("❌ localStorage 폴백도 실패:", fallbackError);
          }
        }
      }
    }
    
    async save() {
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

      await chrome.storage.local.set({"mcp-context": data});
      console.log("💾 컨텍스트 저장 완료 (Cross-Origin Safe):", window.location.origin);
      
      // 하위 호환성을 위해 현재 도메인의 localStorage에도 저장
      localStorage.setItem("mcp-context", JSON.stringify(data));
      localStorage.setItem("mcp-goal", this.currentGoal);
      localStorage.setItem("mcp-actionHistory", JSON.stringify(this.actionHistory));
      localStorage.setItem("mcp-currentPlan", JSON.stringify(this.currentPlan));

    }
    
    // 상태 관리 메서드들
    async setStatus(status, details = {}) {
      console.log(`🔄 상태 변경: ${this.status} → ${status}`, details);
      this.status = status;
      this.lastActionType = details.actionType || this.lastActionType;
      this.expectedPageChange = details.expectedPageChange || false;
      this.waitingForEvaluation = details.waitingForEvaluation || false;
      await this.save();
    }
    
    shouldSendDomOnPageLoad() {
      console.log("🤔 페이지 로드 시 DOM 전송 여부 판단:");
      console.log(`   - 목표: ${this.currentGoal}`);
      console.log(`   - 계획: ${this.currentPlan.length}개`);
      console.log(`   - 액션 히스토리: ${this.actionHistory.length}개`);
      
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
      
      // 단순 로직: 목표 + 계획이 있으면 진행 중인 작업
      if (this.currentGoal && this.currentPlan.length > 0) {
        console.log("✅ 진행 중인 작업 발견 - 평가 모드로 DOM 전송");
        return "evaluation";
      }
      
      // 목표만 있으면 새로운 작업 시작
      if (this.currentGoal) {
        console.log("✅ 새 목표 발견 - 일반 모드로 DOM 전송");
        return "normal";
      }
      
      console.log("❌ 조건에 맞지 않아 DOM 전송하지 않음");
      return false;
    }
    
    async addAction(action) {
      this.actionHistory.push({
        ...action,
        timestamp: Date.now(),
        step: this.step
      });
      this.step++;
      await this.save();
    }
    
    async setPlan(plan) {
      this.currentPlan = plan || [];
      await this.save();
    }
    
    getCurrentStepAction() {
      if (this.currentPlan.length === 0) return null;
      // step은 1부터 시작, 배열 인덱스는 0부터
      const stepIndex = this.step - 1;
      return this.currentPlan[stepIndex] || null;
    }
    
    isLastStep() {
      return this.step >= this.currentPlan.length;
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
    
    async setGoal(goal) {
      console.log("🎯 setGoal() 호출:", goal);
      this.currentGoal = goal;
      this.step = 0;
      this.actionHistory = [];
      this.currentPlan = [];
      this.conversationHistory = [];
      this.addConversation('user', goal);
      
      // 새 목표 시작 시 상태 설정
      await this.setStatus("planning", { actionType: null, expectedPageChange: false });
      
      // CRITICAL: Save the goal to Chrome Storage (Cross-Origin Safe)
      await this.save();
      
      console.log("✅ setGoal() 완료 (Cross-Origin Safe):", this.currentGoal);
    }
    

    
    async clear() {
      this.sessionId = this.generateUUID();
      this.currentGoal = "";
      this.currentPlan = [];
      this.actionHistory = [];
      this.conversationHistory = [];
      this.step = 0;
      this.lastDomSnapshot = "";
      this.createdAt = Date.now();
      
      // 상태 초기화
      this.status = "idle";
      this.lastActionType = null;
      this.expectedPageChange = false;
      this.waitingForEvaluation = false;
      
      // Clear both Chrome Storage and localStorage
      try {
        await chrome.storage.local.remove("mcp-context");
        console.log("🗑️ Chrome Storage 클리어 완료");
      } catch (e) {
        console.log("❌ Chrome Storage 클리어 실패:", e);
      }
      
      localStorage.removeItem("mcp-context");
      localStorage.removeItem("mcp-goal");
      localStorage.removeItem("mcp-actionHistory");
      localStorage.removeItem("mcp-currentPlan");
      localStorage.removeItem("mcp-lastDomSnapshot");
      
      await this.save();
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
  async function saveContext() {
    await context.save();
  }
  
  async function restoreContext() {
    await context.restore();
    // 변수 동기화
    actionHistory = context.actionHistory;
    currentPlan = context.currentPlan;
    lastDomSnapshot = context.lastDomSnapshot;
  }

  let ws = null;
  
  function handleWsOpen() {
    console.log("✅ WebSocket 연결됨");
    // UI 로그는 UI 생성 이후에만 수행 (초기 로딩 시 TDZ 회피)
    try { typeof log !== 'undefined' && log && logMessage && logMessage("🔌 서버 연결 성공"); } catch (e) {}
    chrome.runtime.sendMessage({type: 'connection_status', connected: true});
  }
  
  function handleWsClose() {
    console.log("❌ WebSocket 연결 끊김");
    try { typeof log !== 'undefined' && log && logMessage && logMessage("🔌 서버 연결 끊김"); } catch (e) {}
    chrome.runtime.sendMessage({type: 'connection_status', connected: false});
  }
  
  function handleWsError(error) {
    console.error("❌ WebSocket 오류:", error);
    try { typeof log !== 'undefined' && log && logMessage && logMessage("🔌 서버 연결 오류"); } catch (e) {}
    chrome.runtime.sendMessage({type: 'connection_status', connected: false});
  }
  
  function initWebSocket() {
    ws = new WebSocket("ws://localhost:8000/ws");
    console.log("🔌 WebSocket connecting...");
    ws.onopen = handleWsOpen;
    ws.onclose = handleWsClose;
    ws.onerror = handleWsError;
    // onmessage 핸들러는 선언 이후에 바인딩 (초기화 시에는 바인딩하지 않음)
  }
  
  initWebSocket();
  
  // 페이지 로드 시 컨텍스트 복원 및 평가 처리
  (async () => {
    await restoreContext();
    
    // 페이지 완전 로드 대기 후 평가 처리
    if (document.readyState === 'complete') {
      await handlePageLoadEvaluation();
    } else {
      window.addEventListener('load', async () => {
        await handlePageLoadEvaluation();
      });
    }
  })();
  
  // 페이지 로드 완료 후 평가 처리 함수
  async function handlePageLoadEvaluation() {
    console.log("📄 페이지 로드 완료 - 평가 처리 시작");
    
    // 컨텍스트가 복원되지 않았으면 다시 복원
    if (!context.currentGoal) {
      await context.restore();
    }
    
    console.log("🔍 페이지 로드 후 평가 검사:", {
      goal: context.currentGoal,
      step: context.step,
      planLength: context.currentPlan.length,
      status: context.status,
      expectedPageChange: context.expectedPageChange,
      waitingForEvaluation: context.waitingForEvaluation
    });
    
    // 평가가 필요한 상황인지 확인
    if (context.currentGoal && context.currentPlan.length > 0 && context.waitingForEvaluation) {
      console.log("✅ 평가 조건 충족 - DOM 전송 시작");
      logMessage(`📊 페이지 로드 완료 - 상황 평가 시작 (단계: ${context.step})`);
      
      // WebSocket 연결 대기
      console.log("⏳ WebSocket 연결 확인 중...");
      let retries = 0;
      const maxRetries = 10;
      
      while (ws.readyState !== WebSocket.OPEN && retries < maxRetries) {
        console.log(`🔄 WebSocket 연결 대기 중... (${retries + 1}/${maxRetries}) - 상태: ${ws.readyState}`);
        await new Promise(resolve => setTimeout(resolve, 500));
        retries++;
      }
      
      if (ws.readyState === WebSocket.OPEN) {
        console.log("✅ WebSocket 연결 확인됨 - 평가 DOM 전송");
        try {
          await sendDomForEvaluation();
          logMessage("📤 상황 평가 요청 전송 완료");
        } catch (error) {
          console.error("❌ 평가 DOM 전송 실패:", error);
          logMessage("❌ 평가 요청 실패");
        }
      } else {
        console.error("❌ WebSocket 연결 실패 - 평가 중단");
        logMessage("❌ 연결 실패로 평가 중단");
      }
    } else {
      console.log("ℹ️ 평가 조건 미충족 - 평가 건너뜀");
    }
  }

  // === UI 생성 ===
  const ui = document.createElement("div");
  ui.id = EXTENSION_UI_ID;
  ui.style = "position:fixed;bottom:20px;right:20px;width:340px;padding:10px;background:rgba(255,255,255,0.95);border:1px solid #ccc;border-radius:10px;z-index:2147483647;font-family:sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.15);";
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
    await context.setGoal(message);
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
    // 서버에 프롬프트만 전송 (DOM은 필요시에만 요청)
    console.log("📤 init 메시지 전송:", { type: "init", message });
    ws.send(JSON.stringify({ type: "init", message }));
    console.log("✅ 프롬프트 우선 분석 모드 - DOM은 서버 요청시에만 전송");
  });
  ui.appendChild(sendButton);

  const clearButton = document.createElement("button");
  clearButton.textContent = "Clear";
  clearButton.style = "width:100%;margin-top:8px;padding:8px;border:1px solid #aaa;border-radius:6px;background:#f0f0f0;color:#333;cursor:pointer;font-size:13px;";
  clearButton.addEventListener("click", async (e) => {
    e.stopPropagation();
    
    // 컨텍스트 완전 초기화
    await context.clear();
    
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
      
      // 진행 명령어 특별 처리
      if (message === "진행" || message === "continue") {
        ws.send(JSON.stringify({
          type: "user_continue", 
          message: "진행"
        }));
        logMessage("▶️ 진행 명령 전송");
        return;
      }
      
      // 컨텍스트에 새로운 목표 설정
      console.log("🎯 [Enter] 목표 설정 시도:", message);
      await context.setGoal(message);
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
      console.log("✅ [Enter] 프롬프트 우선 분석 모드 - DOM은 서버 요청시에만 전송");
    }
  });

  // === WebSocket 연결 ===
  const waitUntilReady = () =>
    new Promise(resolve => {
      if (!ws || ws.readyState === 2 || ws.readyState === 3) {
        console.log("🔁 WebSocket 재연결 시도 (state:", ws ? ws.readyState : 'none', ")");
        initWebSocket();
      }
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
          await context.restore();
          actionHistory = context.actionHistory;
          currentPlan = context.currentPlan;
          lastDomSnapshot = context.lastDomSnapshot;
          
          console.log("🔍 재개 검사 (WebSocket 연결 완료 후):", {
            goal: context.currentGoal,
            step: context.step,
            actionHistoryLength: context.actionHistory.length,
            hasGoal: !!context.currentGoal,
            hasActions: context.actionHistory.length > 0,
            wsReadyState: ws.readyState
          });
          
          // 현재 상태를 채팅으로 표시 (UI가 생성된 후)
          setTimeout(() => {
            showCurrentStatus();
          }, 500);
          
          console.log("ℹ️ DOM 전송은 페이지 로드 완료 후 handlePageLoadEvaluation()에서 처리됨");
        }, 2000); // 페이지 로딩 완료를 위해 2초 대기
        
        resolve();
      });
    });

  const handleWsMessage = async (event) => {
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
    } else if (data.type === "request_dom") {
      logMessage("📊 서버에서 DOM 요청");
      setTimeout(() => {
        sendDom();
      }, 500);
    } else if (data.type === "plan") {
      // Planning 결과 수신
      await context.setPlan(data.plan);
      
      // 계획 수립 완료 상태로 변경
      await context.setStatus("executing", { actionType: null, expectedPageChange: false });
      
      // 하위 호환성을 위해 변수 동기화
      currentPlan = context.currentPlan;
      
      logMessage(`🧠 계획 수립 완료: ${currentPlan.length}단계`);
      showPlanProgress();
      
      // 계획 수립 완료 후 첫 번째 액션 실행을 위해 DOM 재전송
      console.log("🚀 계획 완료, 첫 번째 액션 실행을 위해 DOM 재전송");
      setTimeout(() => {
        sendDom();
      }, 1000);
    } else if (data.type === "page_analysis") {
      // === 새로운 기능: 페이지 분석 결과 표시 ===
      displayPageAnalysis(data);
      
    } else if (data.type === "action") {
      // 액션 실행 전 상태 업데이트
      const actionType = data.action.action;
      const expectedPageChange = (actionType === "goto" || actionType === "google_search");
      
      await context.setStatus("executing", { 
        actionType: actionType, 
        expectedPageChange: expectedPageChange,
        waitingForEvaluation: expectedPageChange // goto의 경우 평가 대기
      });
      
      // 컨텍스트에 액션 추가
      await context.addAction(data.action);
      
      // 하위 호환성을 위해 변수 동기화
      actionHistory = context.actionHistory;
      await saveContext(); // 컨텍스트 저장
      logMessage(`🤖 액션(${actionHistory.length}): ${JSON.stringify(data.action)}`, "ACTION_RECEIVED");
      
      // 액션 실행 후 진행 상황 업데이트
      if (context.currentPlan && context.currentPlan.length > 0) {
        showPlanProgress();
      }
      console.log("🔍 액션 상세 정보:", data.action);
      
      // 액션 실행 로그
      sendLogToServer("ACTION_EXECUTION", `액션 실행 시작: ${data.action.action}`, {
        action: data.action,
        step: context.step,
        actionCount: actionHistory.length
      });
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

      // goto나 google_search 액션의 경우 페이지 이동으로 인해 이 코드가 실행되지 않음
      if (data.action.action === 'goto' || data.action.action === 'google_search') {
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
    } else if (data.type === "login_detected") {
      // 로그인 감지 시 대기 UI 표시
      showLoginWaitingMode(data.message);
    } else if (data.type === "automation_resumed") {
      // 자동화 재개 시 대기 UI 제거
      hideLoginWaitingMode();
      logMessage(`🔄 ${data.message}`);
    } else if (data.type === "resume_confirmed") {
      // 작업 재개 확인
      logMessage(`🔄 ${data.message}`);
      logMessage(`🎯 목표: ${data.goal} (단계: ${data.step})`);
    } else if (data.type === "error") {
      logMessage(`❌ 오류: ${data.detail}`);
    }
  };
  // 현재 ws 인스턴스에 핸들러 바인딩 (초기 1회 보장)
  if (ws) {
    ws.onmessage = handleWsMessage;
  }

  // === 화면 캡처 기능 ===
  async function captureScreen() {
    try {
      console.log('📸 화면 캡처 시작...');
      
      // Canvas API를 사용한 화면 캡처 시도
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      
      // 용량 최적화: 캔버스 크기를 50% 축소
      const scale = 0.5;
      canvas.width = Math.floor(window.innerWidth * scale);
      canvas.height = Math.floor(window.innerHeight * scale);
      
      // 스케일 적용을 위한 컨텍스트 변환
      ctx.scale(scale, scale);
      
      console.log(`📐 캔버스 크기: ${canvas.width}x${canvas.height}`);
      
      // 배경을 흰색으로 설정
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // DOM 요소들을 캔버스에 그리기 (중요한 요소들만 선별)
      const elements = document.querySelectorAll('button, input, a, h1, h2, h3, img, form, select, textarea');
      console.log(`🎯 캡처할 요소 수: ${elements.length}`);
      
      let drawnElements = 0;
      const maxElements = 200; // 최대 200개 요소만 그리기
      
      // 요소들을 크기순으로 정렬 (큰 요소가 더 중요)
      const sortedElements = Array.from(elements).sort((a, b) => {
        const aSize = a.offsetWidth * a.offsetHeight;
        const bSize = b.offsetWidth * b.offsetHeight;
        return bSize - aSize;
      }).slice(0, maxElements);
      
      sortedElements.forEach(el => {
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
              ctx.font = 'bold 8px Arial';
              
            } else if (tagName === 'input' || tagName === 'textarea') {
              // 입력창: 연한 회색 배경 + 실선 테두리
              ctx.fillStyle = '#f8f9fa';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#6c757d';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#495057';
              ctx.font = '7px Arial';
              
            } else if (tagName === 'select') {
              // 드롭다운: 노란색 배경
              ctx.fillStyle = '#fff3cd';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#856404';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#856404';
              ctx.font = '7px Arial';
              
            } else if (tagName === 'a') {
              // 링크: 파란색 점선 테두리
              ctx.strokeStyle = '#0d6efd';
              ctx.lineWidth = 1;
              ctx.setLineDash([3, 3]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#0d6efd';
              ctx.font = '7px Arial';
              
            } else if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName)) {
              // 제목: 주황색 배경 + 굵은 테두리
              ctx.fillStyle = '#fff3e0';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#f57c00';
              ctx.lineWidth = 2;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#f57c00';
              const fontSize = tagName === 'h1' ? 10 : tagName === 'h2' ? 9 : 8;
              ctx.font = `bold ${fontSize}px Arial`;
              
            } else if (tagName === 'img') {
              // 이미지: 초록색 배경 + 이미지 표시
              ctx.fillStyle = '#e8f5e8';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#4caf50';
              ctx.lineWidth = 1;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#4caf50';
              ctx.font = '8px Arial';
              const centerX = rect.left + rect.width / 2 - 15;
              const centerY = rect.top + rect.height / 2 + 4;
              ctx.fillText('[IMG]', centerX, centerY);
              ctx.fillStyle = '#2e7d32';
              ctx.font = '6px Arial';
              
            } else if (['ul', 'ol', 'li'].includes(tagName)) {
              // 리스트: 연한 보라색
              ctx.strokeStyle = '#9c27b0';
              ctx.lineWidth = 1;
              ctx.setLineDash([2, 2]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#9c27b0';
              ctx.font = '7px Arial';
              
            } else if (tagName === 'form') {
              // 폼: 연한 파란색 배경
              ctx.fillStyle = '#f0f8ff';
              ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
              ctx.strokeStyle = '#4682b4';
              ctx.lineWidth = 1;
              ctx.setLineDash([5, 3]);
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#4682b4';
              ctx.font = '7px Arial';
              
            } else {
              // 기타 요소: 연한 회색
              ctx.strokeStyle = '#dee2e6';
              ctx.lineWidth = 0.5;
              ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
              ctx.fillStyle = '#6c757d';
              ctx.font = '6px Arial';
            }
            
            // 텍스트 추가 (더 짧게 제한)
            const text = el.innerText || el.placeholder || el.value || el.alt || el.title || '';
            if (text.trim() && rect.width > 15 && rect.height > 8) {
              const maxWidth = rect.width - 4;
              const maxChars = Math.min(Math.floor(maxWidth / 4), 20); // 최대 20자 제한
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
      
      // Canvas를 JPEG로 변환 (압축률 높음, 품질 70%)
      const dataURL = canvas.toDataURL('image/jpeg', 0.7);
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
    
    // 와이어프레임 설정 확인
    const wireframeSettings = await getWireframeSettings();
    let image = null;
    
    if (wireframeSettings.enabled) {
      image = await captureScreen();
    }
    
    // WebSocket 보장
    await waitUntilReady();
    
    const payload = {
      type: "question",
      message: goal,
      dom,
      image: image,
      wireframeEnabled: wireframeSettings.enabled
    };
    
    logMessage(`📤 질문 전송 ${wireframeSettings.enabled ? '(+이미지)' : '(텍스트만)'}`);
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
    
    console.log("📤 평가용 DOM 전송 시작 - readyState:", ws.readyState);
    
    const dom = summarizeDom();
    
    // 와이어프레임 설정 확인
    const wireframeSettings = await getWireframeSettings();
    let image = null;
    
    if (wireframeSettings.enabled) {
      image = await captureScreen();
    }
    
    // WebSocket 보장
    await waitUntilReady();

    // 컨텍스트 업데이트
    context.lastDomSnapshot = snapshotDom();
    
    const payload = {
      type: wireframeSettings.enabled ? "dom_with_image_evaluation" : "dom_evaluation",
      message: context.currentGoal,
      dom,
      image: image,
      context: context.getContextForServer(),
      evaluationMode: true,
      wireframeEnabled: wireframeSettings.enabled
    };
    
    logMessage(`📊 상황 평가 요청 (단계: ${context.step})`);
    console.log("📊 평가용 컨텍스트:", context.getContextForServer());
    console.log("📤 평가용 DOM 전송:", payload.type);
    ws.send(JSON.stringify(payload));
    
    await context.save();
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
    
    // WebSocket 보장
    await waitUntilReady();
    console.log("✅ WebSocket 연결 확인 (일반 모드) - readyState:", ws.readyState);
    
    const dom = summarizeDom();
    
    // 와이어프레임 설정 확인 후 이미지 캡처
    const wireframeSettings = await getWireframeSettings();
    let image = null;
    
    if (wireframeSettings.enabled) {
      image = await captureScreen();
      console.log("📸 와이어프레임 이미지 캡처:", {
        imageExists: !!image,
        imageLength: image ? image.length : 0
      });
    } else {
      console.log("🎨 와이어프레임 비활성화 - 이미지 전송 건너뜀");
    }
    
    // 컨텍스트 업데이트
    context.lastDomSnapshot = snapshotDom();
    
    const payload = {
      type: wireframeSettings.enabled ? "dom_with_image" : "dom_only",
      message: context.currentGoal,
      dom,
      image: image,
      context: context.getContextForServer(),
      wireframeEnabled: wireframeSettings.enabled
    };
    
    logMessage(`📤 DOM ${wireframeSettings.enabled ? '+ 이미지' : '(텍스트만)'} 전송 (단계: ${context.step})`);
    console.log("📤 전송할 컨텍스트:", context.getContextForServer());
    console.log("📤 와이어프레임 모드:", wireframeSettings.enabled);
    ws.send(JSON.stringify(payload));
    
    await context.save();
  }

  function snapshotDom() {
    return JSON.stringify(summarizeDom());
  }

  // === 새로운 기능: 페이지 분석 결과 표시 ===
  function displayPageAnalysis(analysisData) {
    console.log("📊 페이지 분석 결과 수신:", analysisData);
    
    const { web_guide, page_understanding, progress_evaluation } = analysisData;
    
    // 웹 가이드 표시
    if (web_guide) {
      logMessage(`🎯 웹 가이드: ${web_guide}`, "PAGE_ANALYSIS");
    }
    
    // 페이지 이해도 표시 (3영역 구조)
    if (page_understanding) {
      const { page_type, understanding_level, layout_confidence, menu_area, function_area, content_area, item_structure, clickable_items, visual_patterns, dom_elements, analysis_method, is_login_page } = page_understanding;
      
      logMessage(`📄 페이지 구조 분석:`, "PAGE_ANALYSIS");
      const hasLegacy = page_type || understanding_level || layout_confidence;
      if (hasLegacy) {
        logMessage(`  • 타입: ${page_type} | 이해도: ${understanding_level} | 레이아웃: ${layout_confidence}`, "PAGE_ANALYSIS");
      } else {
        const loginInfo = typeof is_login_page === 'boolean' ? (is_login_page ? '로그인 필요' : '로그인 상태') : '알수없음';
        logMessage(`  • 요소: ${dom_elements ?? '알수없음'}개 | 분석: ${analysis_method ?? 'llm_delegation'} | 상태: ${loginInfo}`, "PAGE_ANALYSIS");
      }
      
      // 항목 구조 타입 표시
      if (item_structure && item_structure !== 'unknown') {
        const structureEmoji = {
          'table_list': '📊',
          'ul_list': '📋', 
          'card_layout': '🗂️'
        };
        const structureNames = {
          'table_list': '테이블 리스트 (Gmail 스타일)',
          'ul_list': 'UL/LI 리스트 (Daum Mail 스타일)',
          'card_layout': '카드 레이아웃 (모던 UI 스타일)'
        };
        
        logMessage(`  • ${structureEmoji[item_structure]} 항목구조: ${structureNames[item_structure]}`, "PAGE_ANALYSIS");
      }
      
      // 3영역 구조 표시
      if (menu_area && menu_area.length > 0) {
        const menuItems = menu_area.slice(0, 3).map(m => m.text || m.tag).filter(t => t).join(', ');
        logMessage(`  • 🧭 메뉴영역(좌측): ${menu_area.length}개 - ${menuItems}${menu_area.length > 3 ? '...' : ''}`, "PAGE_ANALYSIS");
      }
      
      if (function_area && function_area.length > 0) {
        const funcItems = function_area.slice(0, 3).map(f => f.text || f.tag).filter(t => t).join(', ');
        logMessage(`  • 🔧 기능영역(상단): ${function_area.length}개 - ${funcItems}${function_area.length > 3 ? '...' : ''}`, "PAGE_ANALYSIS");
      }
      
      if (content_area && content_area.length > 0) {
        const contentItems = content_area.slice(0, 3).map(c => c.text || c.tag).filter(t => t).join(', ');
        logMessage(`  • 📋 컨텐츠영역(메인): ${content_area.length}개 - ${contentItems}${content_area.length > 3 ? '...' : ''}`, "PAGE_ANALYSIS");
      }
      
      // 클릭 가능한 항목들 표시
      if (clickable_items && clickable_items.length > 0) {
        const subjectItems = clickable_items.filter(item => item.is_subject);
        const mainItems = subjectItems.length > 0 ? subjectItems : clickable_items;
        
        logMessage(`  • 🎯 클릭 가능한 항목: ${clickable_items.length}개 발견`, "PAGE_ANALYSIS");
        
        if (mainItems.length > 0) {
          const firstItem = mainItems[0];
          logMessage(`  • 📌 첫 번째 항목: "${firstItem.text}" (${firstItem.class})`, "PAGE_ANALYSIS");
          
          // 권장 셀렉터 제안
          if (item_structure === 'ul_list') {
            logMessage(`  • 💡 권장 셀렉터: ul.list_mail li:first-child a.link_subject`, "PAGE_ANALYSIS");
          } else if (item_structure === 'table_list') {
            logMessage(`  • 💡 권장 셀렉터: tbody tr:first-child a`, "PAGE_ANALYSIS");
          } else {
            logMessage(`  • 💡 권장 셀렉터: .items .item:first-child a`, "PAGE_ANALYSIS");
          }
        }
      } else {
        logMessage(`  • ⚠️ 클릭 가능한 항목을 찾을 수 없음`, "PAGE_ANALYSIS");
      }
      
      // 와이어프레임 패턴 분석 표시
      if (visual_patterns) {
        const { repeated_items, primary_content_links, visual_weight_items } = visual_patterns;
        
        if (repeated_items > 0) {
          logMessage(`  • 🔄 반복 패턴: ${repeated_items}개 항목이 일관된 구조로 배치됨`, "PAGE_ANALYSIS");
        }
        
        if (visual_weight_items && visual_weight_items.length > 0) {
          const topPattern = visual_weight_items[0];
          logMessage(`  • 📐 주요 구조: ${topPattern.pattern} (${topPattern.count}회 반복)`, "PAGE_ANALYSIS");
        }
        
        if (primary_content_links && primary_content_links.length > 0) {
          const topLink = primary_content_links[0];
          logMessage(`  • 🎯 최우선 링크: "${topLink.text}" (우선순위: ${topLink.priority})`, "PAGE_ANALYSIS");
          
          // 다음 메일 구조 특화 메시지
          if (topLink.class && topLink.class.includes('link_subject')) {
            logMessage(`  • 💡 다음메일 감지: ul.list_mail li:first-child a.link_subject 권장`, "PAGE_ANALYSIS");
          }
        }
        
        // 와이어프레임 기반 클릭 가이드
        if (repeated_items > 2 && primary_content_links && primary_content_links.length > 0) {
          logMessage(`  • 📋 와이어프레임 분석: 수직 반복 구조 감지 → 첫 번째 항목의 주요 링크 클릭 권장`, "PAGE_ANALYSIS");
        }
      }
    }
    
    // 목표 진행도 표시 (서버 스키마 변화 대응: current_step/total_steps 폴백 처리)
    if (progress_evaluation) {
      const { progress_percentage, current_phase, completion_feasibility, recommendations, current_step, total_steps } = progress_evaluation;
      const pct = typeof progress_percentage === 'number' ? progress_percentage : 0;
      const phaseText = (current_phase != null && current_phase !== undefined)
        ? current_phase
        : `${(current_step != null ? current_step : '?')}/${(total_steps != null ? total_steps : '?')}`;
      let feasibility = completion_feasibility;
      if (!feasibility && typeof pct === 'number') {
        feasibility = pct >= 90 ? 'high' : (pct >= 50 ? 'medium' : 'low');
      }
      
      logMessage(`🎯 목표 진행도:`, "PROGRESS_EVALUATION");
      logMessage(`  • 진행률: ${Number(pct).toFixed(1)}% | 단계: ${phaseText} | 완료가능성: ${feasibility ?? 'unknown'}` , "PROGRESS_EVALUATION");
      
      if (recommendations && recommendations.length > 0) {
        logMessage(`  • 권장사항: ${recommendations.join(', ')}`, "PROGRESS_EVALUATION");
      }
    }
  }

  // 계획 진행 상황을 표시
  function showPlanProgress() {
    if (!context.currentPlan || context.currentPlan.length === 0) {
      return;
    }
    
    const totalSteps = context.currentPlan.length;
    const currentStepIndex = context.step; // step은 0부터 시작하는 인덱스로 사용
    
    logMessage(`📋 계획 진행 상황:`);
    
    context.currentPlan.forEach((step, index) => {
      const stepNumber = index + 1;
      let status = "";
      
      if (index < currentStepIndex) {
        // 완료된 단계
        status = "✅";
      } else if (index === currentStepIndex) {
        // 현재 진행중인 단계
        status = "🔄";
      } else {
        // 앞으로 진행할 단계
        status = "⏳";
      }
      
      const actionText = step.action;
      const targetText = step.target || step.reason || "";
      
      logMessage(`  ${status} ${stepNumber}. ${actionText} - ${targetText.substring(0, 40)}${targetText.length > 40 ? '...' : ''}`);
    });
    
    const completedSteps = currentStepIndex;
    const remainingSteps = totalSteps - currentStepIndex;
    logMessage(`📊 진행: ${completedSteps}/${totalSteps} 완료 (남은 단계: ${remainingSteps}개)`);
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
      
      // 계획이 있으면 진행 상황 표시, 없으면 단순 진행 표시
      if (context.currentPlan && context.currentPlan.length > 0) {
        showPlanProgress();
      } else {
        logMessage(`📊 진행: ${context.step}단계 (총 ${context.actionHistory.length}개 액션 완료)`);
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

  function logMessage(text, eventType = "UI") {
    const div = document.createElement("div");
    div.textContent = text;
    div.style.margin = "4px 0";
    div.style.color = "#000";
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    
    // 로그 전송 관련 메시지와 반복적인 UI 메시지는 서버로 전송하지 않음
    const skipLogPatterns = [
      "로그", "LOG", "━━━", "WebSocket", "메시지", "전송", "수신", "연결"
    ];
    
    const shouldSkip = skipLogPatterns.some(pattern => text.includes(pattern)) || eventType === "LOG_RELATED";
    
    if (!shouldSkip) {
      sendLogToServer(eventType, text);
    }
  }
  
  function sendLogToServer(eventType, message, extraData = {}) {
    // WebSocket이 연결되어 있고 목표가 설정된 경우에만 로그 전송
    if (ws.readyState === WebSocket.OPEN && context.currentGoal) {
      try {
        ws.send(JSON.stringify({
          type: "client_log",
          event_type: eventType,
          message: message,
          extra_data: extraData,
          timestamp: new Date().toISOString()
        }));
      } catch (e) {
        console.error("로그 전송 실패:", e);
      }
    }
  }

  function summarizeDom() {
    try {
      // 도우미들
      const normalize = (s) => (s || '').replace(/\s+/g, ' ').trim();
      const isSameOriginHref = (href) => {
        try {
          const u = new URL(href, location.href);
          return u.origin === location.origin;
        } catch { return false; }
      };
      const safeClassNameOf = (el) => {
        try {
          if (!el.className) return '';
          return typeof el.className === 'string' ? el.className : el.className.toString();
        } catch { return ''; }
      };
      const isNoiseElement = (el) => {
        const tag = (el.tagName || '').toLowerCase();
        if (['script', 'style', 'noscript', 'template'].includes(tag)) return true;
        const cls = (safeClassNameOf(el) || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const attrHit = (name) => (el.getAttribute && el.getAttribute(name)) ? String(el.getAttribute(name)).toLowerCase() : '';
        const patterns = ['ad', 'ads', 'advert', 'banner', 'promo', 'promotion', 'sponsored', 'tracking', 'track', 'beacon', 'pixel', 'outbrain', 'taboola', 'gtm', 'ga-'];
        const hay = `${cls} ${id} ${attrHit('data-ad')} ${attrHit('data-ads')} ${attrHit('data-gtm')} ${attrHit('data-ga')} ${attrHit('data-track')} ${attrHit('data-trk')}`;
        return patterns.some(p => hay.includes(p));
      };
      const isVisible = (el) => {
        try {
          if (el.getAttribute && el.getAttribute('aria-hidden') === 'true') return false;
          const style = window.getComputedStyle(el);
          if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
          if (el.offsetParent === null && style.position !== 'fixed') return false;
          const rect = el.getBoundingClientRect();
          const inViewport = rect && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < (window.innerHeight || 0) && rect.left < (window.innerWidth || 0);
          return inViewport;
        } catch { return true; }
      };
      const isInteractive = (el) => {
        const tag = (el.tagName || '').toLowerCase();
        if (['a', 'button', 'input', 'select', 'textarea'].includes(tag)) return true;
        const role = (el.getAttribute && el.getAttribute('role')) || '';
        return ['button', 'link'].includes((role || '').toLowerCase()) || !!el.onclick;
      };
      const isSemanticKeep = (el) => {
        const tag = (el.tagName || '').toLowerCase();
        const keepTags = ['h1','h2','h3','section','article','main','nav','aside','p','li'];
        return keepTags.includes(tag) || isInteractive(el);
      };
      const computeScore = (el, text) => {
        const tag = (el.tagName || '').toLowerCase();
        const children = (el.children && el.children.length) || 0;
        const textDensity = (text.length || 0) / (children + 1);
        const weights = { h1:3.0, h2:2.5, h3:2.0, main:2.0, article:2.0, section:1.8, nav:1.5, aside:1.3, p:1.2, li:1.1, a:1.8, button:1.8, input:1.5 };
        const semantic = weights[tag] || 1.0;
        const clickable = isInteractive(el) ? 1 : 0;
        const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width:0, height:0 };
        const area = Math.max(1, rect.width * rect.height);
        const areaFactor = Math.min(1.0, area / (window.innerWidth * window.innerHeight));
        return Number((semantic * (1 + clickable * 0.2) + Math.min(1.0, textDensity / 200) + areaFactor * 0.2).toFixed(3));
      };
      const pickDataAttrs = (el) => {
        const out = {};
        const allow = ['data-testid','data-test','data-qa'];
        for (const name of allow) {
          const v = el.getAttribute && el.getAttribute(name);
          if (v) out[name] = String(v);
        }
        return out;
      };

      // 수집 대상: 의미/인터랙션/구조 중심
      const selector = [
        'h1','h2','h3','section','article','main','nav','aside','p','li',
        'a','button','input','select','textarea','form','label','header','footer'
      ].join(',');
      const candidates = Array.from(document.querySelectorAll(selector));
      console.log(`🔍 후보 요소 수집: ${candidates.length}개`);

      const results = [];
      for (const el of candidates) {
        try {
          if (!el) continue;
          if (el.closest && el.closest(`#${EXTENSION_UI_ID}`)) continue; // 확장 UI 제외
          if (isNoiseElement(el)) continue; // 광고/스크립트 등 제외
          if (!isVisible(el)) continue; // 비가시 제외
          if (!isSemanticKeep(el)) continue; // 보존 기준 미충족 제외

          const tag = (el.tagName || 'unknown').toLowerCase();
          const selectorStr = getSelector(el);
          const textRaw = el.innerText || el.placeholder || el.value || el.title || '';
          const text = normalize(textRaw).slice(0, 500);

          // 화이트리스트 속성
          const item = { tag, selector: selectorStr };
          if (text) item.text = text;
          if (el.id) item.id = el.id;
          const role = el.getAttribute && el.getAttribute('role');
          if (role) item.role = role;
          const aria = el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'));
          if (aria) item['aria-label'] = aria;
          if (el.type) item.type = el.type;
          // value: 텍스트 입력만
          if ((tag === 'input' || tag === 'textarea')) {
            const t = (el.type || 'text').toLowerCase();
            if (['text','search','email','tel','url','number','password'].includes(t)) {
              if (el.value) item.value = String(el.value).slice(0, 200);
            }
          }
          // href: 동일 출처만
          if (tag === 'a' && el.href && isSameOriginHref(el.href)) {
            item.href = el.href;
          }
          // data-* 일부
          Object.assign(item, pickDataAttrs(el));

          // 스코어링 (선택)
          item.clickable = isInteractive(el);
          item.inViewport = true;
          item.score = computeScore(el, item.text || '');

          results.push(item);
        } catch (e) {
          console.log(`⚠️ DOM 요소 처리 오류: ${e.message}`);
        }
      }

      console.log(`📊 필터링 후 DOM: ${results.length}개`);
      return results;
    } catch (error) {
      console.error('DOM 요약 오류:', error);
      return [];
    }
  }

  function getSelector(el) {
    if (!el || !el.tagName) return 'unknown';
    
    try {
      // 우선순위: id > name > class > tag
      if (el.id) return `#${el.id}`;
      if (el.name) return `${el.tagName.toLowerCase()}[name='${el.name}']`;
      if (el.type) return `${el.tagName.toLowerCase()}[type='${el.type}']`;
      
      // 안전한 className 처리
      if (el.className) {
        try {
          let classNameStr = '';
          if (typeof el.className === 'string') {
            classNameStr = el.className;
          } else if (el.className.toString) {
            classNameStr = el.className.toString();
          }
          
          if (classNameStr) {
            const classes = classNameStr.split(' ').filter(c => c && c.trim()).join('.');
            if (classes) return `${el.tagName.toLowerCase()}.${classes}`;
          }
        } catch (e) {
          console.log(`⚠️ getSelector className 처리 오류: ${e.message}`);
        }
      }
      
      return el.tagName.toLowerCase();
    } catch (error) {
      console.log(`⚠️ getSelector 전체 오류: ${error.message}`);
      return 'unknown';
    }
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
            if (action.url) {
              // 서버에서 이미 분석한 최적의 URL로 직접 이동
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = action.url;
              logMessage(`🔍 Google 검색 완료: ${action.query || 'unknown'}`);
              logMessage(`✅ 선택된 사이트로 이동: ${action.url}`);
            } else if (action.query) {
              // 폴백: URL이 없으면 Google 검색 페이지로 이동
              const searchQuery = encodeURIComponent(action.query);
              const googleSearchUrl = `https://www.google.com/search?q=${searchQuery}`;
              saveContext(); // 페이지 이동 전 컨텍스트 저장
              window.location.href = googleSearchUrl;
              logMessage(`🔍 Google 검색 폴백: ${action.query}`);
              logMessage(`✅ 검색 페이지로 이동: ${googleSearchUrl}`);
            } else {
              logMessage(`❌ Google 검색 실패: URL과 검색어가 모두 지정되지 않음`);
              logMessage(`🔍 액션 내용: ${JSON.stringify(action)}`);
            }
            break;
            
          case "click":
            console.log(`🖱️ [클릭 시작] selector: "${action.selector}", text: "${action.text}"`);
            const clickEl = findElement(action.selector, action.text);
            if (clickEl) {
              console.log(`🎯 [클릭 준비] 요소 발견됨, 스크롤 시작`);
              clickEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
              await new Promise(resolve => setTimeout(resolve, 500));
              
              console.log(`🖱️ [클릭 실행] 이벤트 발생 시작`);
              // Medium과 같은 SPA에서 클릭 이벤트 강화
              try {
                // 1. 포커스 먼저 설정
                clickEl.focus();
                
                // 2. 마우스 이벤트 시뮬레이션
                clickEl.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                clickEl.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                clickEl.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                
                // 3. 추가 이벤트들 (React 컴포넌트용)
                clickEl.dispatchEvent(new Event('change', { bubbles: true }));
                clickEl.dispatchEvent(new Event('input', { bubbles: true }));
                
                console.log(`✅ [클릭 완료] 모든 이벤트 발생됨`);
                logMessage(`✅ 클릭 성공: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
                console.log(`🎯 클릭된 요소:`, clickEl);
                console.log(`🎯 요소 정보:`, {
                  tagName: clickEl.tagName,
                  className: clickEl.className,
                  textContent: clickEl.textContent?.substring(0, 50),
                  visible: clickEl.offsetParent !== null,
                  clickable: clickEl.onclick || clickEl.getAttribute('role') === 'button'
                });
              } catch (clickError) {
                console.error("클릭 이벤트 실행 오류:", clickError);
                // 기본 클릭 시도
                try {
                  clickEl.click();
                  logMessage(`✅ 기본 클릭 성공: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
                } catch (e) {
                  logMessage(`❌ 기본 클릭 실패: ${action.selector}`);
                  // 서버에 실패 보고
                  try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: 'client_log', event_type: 'ACTION_FAILURE', message: 'click_failed', extra_data: { selector: action.selector, text: action.text } })); } catch (e2) {}
                }
              }
            } else {
              console.log(`❌ [클릭 실패] 요소를 찾을 수 없음`);
              logMessage(`❌ 클릭 실패: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
              console.warn("❌ Click element not found:", action.selector, action.text);
              
              // SPA에서는 요소가 동적으로 로드될 수 있으므로 재시도
              logMessage(`🔄 동적 로딩 대기 후 재시도...`);
              await new Promise(resolve => setTimeout(resolve, 2000));
              
              const retryEl = findElement(action.selector, action.text);
              if (retryEl) {
                retryEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                await new Promise(resolve => setTimeout(resolve, 500));
                try {
                  retryEl.click();
                  logMessage(`✅ 재시도 클릭 성공: ${action.selector}${action.text ? ` (${action.text})` : ''}`);
                } catch (e) {
                  logMessage(`❌ 재시도 클릭 실패: ${action.selector}`);
                  try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: 'client_log', event_type: 'ACTION_FAILURE', message: 'click_retry_failed', extra_data: { selector: action.selector, text: action.text } })); } catch (e2) {}
                }
              } else {
                // 대안 제시
                const alternatives = findAlternativeElements(action.selector, action.text);
                if (alternatives.length > 0) {
                  logMessage(`💡 대안 요소들 발견: ${alternatives.length}개`);
                  alternatives.slice(0, 3).forEach((alt, i) => {
                    logMessage(`  ${i + 1}. ${alt.tag}${alt.class ? '.' + alt.class : ''} - "${alt.text}"`);
                  });
                  
                  // 첫 번째 대안 자동 시도
                  if (alternatives[0]) {
                    const altEl = document.querySelector(alternatives[0].selector);
                    if (altEl) {
                      altEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      await new Promise(resolve => setTimeout(resolve, 500));
                      try {
                        altEl.click();
                        logMessage(`✅ 대안 요소 자동 클릭: ${alternatives[0].selector}`);
                      } catch (e) {
                        logMessage(`❌ 대안 요소 클릭 실패: ${alternatives[0].selector}`);
                        try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: 'client_log', event_type: 'ACTION_FAILURE', message: 'click_alternative_failed', extra_data: { selector: alternatives[0].selector } })); } catch (e2) {}
                      }
                    }
                  }
                } else {
                  logMessage(`❌ 대안 요소도 찾을 수 없음`);
                  try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: 'client_log', event_type: 'ACTION_FAILURE', message: 'click_not_found', extra_data: { selector: action.selector, text: action.text } })); } catch (e2) {}
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
              
              // 전송 버튼 찾기
              const submitButton = findSubmitButton(fillEl);
              if (submitButton) {
                logMessage(`🔍 전송 버튼 발견: ${submitButton.tagName}${submitButton.type ? `[${submitButton.type}]` : ''}`);
              } else {
                // 전송 버튼이 없으면 Enter 키 입력
                logMessage(`🎯 전송 버튼 없음 → Enter 키 입력`);
                await new Promise(resolve => setTimeout(resolve, 300));
                fillEl.dispatchEvent(new KeyboardEvent('keydown', { 
                  key: 'Enter', 
                  keyCode: 13, 
                  which: 13, 
                  bubbles: true 
                }));
                fillEl.dispatchEvent(new KeyboardEvent('keypress', { 
                  key: 'Enter', 
                  keyCode: 13, 
                  which: 13, 
                  bubbles: true 
                }));
                fillEl.dispatchEvent(new KeyboardEvent('keyup', { 
                  key: 'Enter', 
                  keyCode: 13, 
                  which: 13, 
                  bubbles: true 
                }));
                logMessage(`⌨️ Enter 키 입력 완료`);
              }
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
    
    // 상세한 탐지 과정 로깅
    console.log(`🔍 [요소 탐지 시작] selector: "${selector}", text: "${text || ''}"`);
    logMessage(`🔍 요소 탐지: ${selector}${text ? ` (텍스트: "${text}")` : ''}`);
    
    const startTime = Date.now();
    let elements = [];
    
    try {
      // 1. CSS 선택자로 직접 검색
      console.log(`🔍 [1단계] CSS 직접 검색: ${selector}`);
      try {
        elements = Array.from(document.querySelectorAll(selector) || []);
        console.log(`   → 발견: ${elements.length}개`);
      } catch (selectorError) {
        console.log(`   → CSS 선택자 오류: ${selectorError.message}`);
        elements = [];
      }
      
      // 2. 선택자가 실패하면 더 유연한 검색 시도
      if (elements.length === 0) {
        console.log(`🔍 [2단계] CSS 선택자 실패: ${selector}, 유연한 검색 시도...`);
        
        // 태그와 클래스 기반 검색
        const tagMatch = selector.match(/^(\w+)/);
        const classMatch = selector.match(/\.([\w-]+)/);
        
        if (tagMatch && classMatch) {
          const tag = tagMatch[1];
          const className = classMatch[1];
          const altSelector = `${tag}.${className}`;
          console.log(`🔍 [2-1] 태그+클래스: ${altSelector}`);
          try {
            elements = Array.from(document.querySelectorAll(altSelector) || []);
            console.log(`   → 발견: ${elements.length}개`);
          } catch (e) {
            console.log(`   → 태그+클래스 검색 실패: ${e.message}`);
            elements = [];
          }
        } else if (tagMatch) {
          // 태그만으로 검색
          console.log(`🔍 [2-2] 태그만: ${tagMatch[1]}`);
          try {
            elements = Array.from(document.querySelectorAll(tagMatch[1]) || []);
            console.log(`   → 발견: ${elements.length}개`);
          } catch (e) {
            console.log(`   → 태그 검색 실패: ${e.message}`);
            elements = [];
          }
        }
      }
      
      // 3. 텍스트 기반 필터링
      if (text && elements && elements.length > 0) {
        console.log(`🔍 [3단계] 텍스트 필터링: "${text}" (필터 전: ${elements.length}개)`);
        try {
          elements = elements.filter(el => {
            if (!el) return false;
            const elementText = (el.innerText || el.textContent || el.value || '').toLowerCase();
            const searchText = text.toLowerCase();
            return elementText.includes(searchText);
          });
          console.log(`   → 텍스트 필터 후: ${elements.length}개`);
        } catch (filterError) {
          console.log(`   → 텍스트 필터링 오류: ${filterError.message}`);
          // 필터링 실패 시 원본 elements 유지
        }
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
      
      // 7. Medium 특화 검색
      if (elements.length === 0 && window.location.hostname.includes('medium')) {
        console.log(`🔍 Medium 특화 검색: ${selector}`);
        
        // Medium의 일반적인 클릭 가능한 요소들
        const mediumElements = document.querySelectorAll(`
          [data-testid], [data-action], [role="button"], [role="link"],
          .crayons-btn, .c-btn, [class*="button"], [class*="link"],
          article, h1, h2, h3, [class*="title"], [class*="story"],
          div[tabindex], span[tabindex], p[tabindex]
        `);
        
        elements = Array.from(mediumElements).filter(el => {
          // 보이는 요소인지 확인
          const isVisible = el.offsetParent !== null && 
                           el.getBoundingClientRect().width > 0 && 
                           el.getBoundingClientRect().height > 0;
          
          // 텍스트가 있거나 클릭 가능한 요소인지 확인
          const hasText = el.innerText && el.innerText.trim().length > 0;
          const isInteractive = el.onclick || el.getAttribute('tabindex') || 
                               el.getAttribute('role') === 'button' ||
                               el.getAttribute('role') === 'link' ||
                               el.style.cursor === 'pointer';
          
          return isVisible && (hasText || isInteractive);
        });
        
        // 텍스트 매칭이 있으면 우선적으로 필터링
        if (text && elements.length > 0) {
          const textMatched = elements.filter(el => {
            const elementText = (el.innerText || el.textContent || '').toLowerCase();
            return elementText.includes(text.toLowerCase());
          });
          if (textMatched.length > 0) {
            elements = textMatched;
          }
        }
      }
      
    } catch (error) {
      console.error(`❌ 요소 검색 오류: ${error}`);
      return null;
    }
    
    if (elements.length > 0) {
      const elapsedTime = Date.now() - startTime;
      const foundElement = elements[0];
      
      console.log(`✅ [요소 탐지 성공] ${selector} (${elements.length}개 발견, ${elapsedTime}ms)`);
      console.log(`📍 선택된 요소:`, foundElement);
      
      // 안전한 className 처리
      let classNameStr = '';
      try {
        if (foundElement.className) {
          if (typeof foundElement.className === 'string') {
            classNameStr = foundElement.className;
          } else if (foundElement.className.toString) {
            classNameStr = foundElement.className.toString();
          }
        }
      } catch (e) {
        console.log(`⚠️ className 처리 오류: ${e.message}`);
        classNameStr = '';
      }
      
      // 안전한 속성 접근
      let attributesInfo = [];
      try {
        if (foundElement.attributes && foundElement.attributes.length > 0) {
          attributesInfo = Array.from(foundElement.attributes).map(attr => `${attr.name}="${attr.value}"`);
        }
      } catch (e) {
        console.log(`⚠️ attributes 처리 오류: ${e.message}`);
        attributesInfo = [];
      }
      
      console.log(`📊 요소 상세 정보:`, {
        tagName: foundElement.tagName || 'unknown',
        className: classNameStr,
        id: foundElement.id || '',
        textContent: (foundElement.textContent || '').substring(0, 100),
        visible: foundElement.offsetParent !== null,
        rect: foundElement.getBoundingClientRect(),
        attributes: attributesInfo,
        clickable: !!(foundElement.onclick || foundElement.getAttribute('role') === 'button' || foundElement.style.cursor === 'pointer')
      });
      
      // 안전한 표시용 클래스명 추출
      let displayClassName = '';
      if (classNameStr) {
        try {
          const firstClass = classNameStr.split(' ')[0];
          if (firstClass) {
            displayClassName = '.' + firstClass;
          }
        } catch (e) {
          console.log(`⚠️ 표시용 클래스명 처리 오류: ${e.message}`);
        }
      }
      
      logMessage(`✅ 요소 발견: ${foundElement.tagName}${displayClassName} - "${(foundElement.textContent || '').substring(0, 30)}"`);
      
      return foundElement;
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
          try {
            if (el && el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
              const elementText = (el.innerText || el.textContent || '').trim();
              if (elementText.length > 0) {
                // 안전한 className 처리
                let safeClassName = '';
                try {
                  if (el.className) {
                    if (typeof el.className === 'string') {
                      safeClassName = el.className;
                    } else if (el.className.toString) {
                      safeClassName = el.className.toString();
                    }
                  }
                } catch (e) {
                  safeClassName = '';
                }
                
                alternatives.push({
                  tag: el.tagName.toLowerCase(),
                  class: safeClassName,
                  text: elementText.substring(0, 50),
                  selector: getSelector(el)
                });
              }
            }
          } catch (e) {
            console.log(`⚠️ 대안 요소 처리 오류: ${e.message}`);
          }
        });
      }
      
      // 2. 텍스트 기반 검색
      if (text) {
        const allElements = document.querySelectorAll('a, button, li, div, span');
        allElements.forEach(el => {
          try {
            if (el && el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
              const elementText = (el.innerText || el.textContent || '').toLowerCase();
              const searchText = text.toLowerCase();
              if (elementText.includes(searchText)) {
                // 안전한 className 처리
                let safeClassName = '';
                try {
                  if (el.className) {
                    if (typeof el.className === 'string') {
                      safeClassName = el.className;
                    } else if (el.className.toString) {
                      safeClassName = el.className.toString();
                    }
                  }
                } catch (e) {
                  safeClassName = '';
                }
                
                alternatives.push({
                  tag: el.tagName.toLowerCase(),
                  class: safeClassName,
                  text: (el.innerText || el.textContent || '').substring(0, 50),
                  selector: getSelector(el)
                });
              }
            }
          } catch (e) {
            console.log(`⚠️ 텍스트 기반 검색 오류: ${e.message}`);
          }
        });
      }
      
      // 3. 클릭 가능한 요소들 찾기
      const clickableElements = document.querySelectorAll('a, button, [role="button"], [onclick]');
      clickableElements.forEach(el => {
        try {
          if (el && el.offsetParent !== null && !el.closest(`#${EXTENSION_UI_ID}`)) {
            const elementText = (el.innerText || el.textContent || '').trim();
            if (elementText.length > 0) {
              // 안전한 className 처리
              let safeClassName = '';
              try {
                if (el.className) {
                  if (typeof el.className === 'string') {
                    safeClassName = el.className;
                  } else if (el.className.toString) {
                    safeClassName = el.className.toString();
                  }
                }
              } catch (e) {
                safeClassName = '';
              }
              
              alternatives.push({
                tag: el.tagName.toLowerCase(),
                class: safeClassName,
                text: elementText.substring(0, 50),
                selector: getSelector(el)
              });
            }
          }
        } catch (e) {
          console.log(`⚠️ 클릭 가능 요소 검색 오류: ${e.message}`);
        }
      });
      
    } catch (error) {
      console.error('대안 요소 검색 오류:', error);
    }
    
    // 중복 제거 및 정렬
    const uniqueAlternatives = [];
    const seen = new Set();
    
    alternatives.forEach(alt => {
      try {
        const key = `${alt.tag}-${alt.text}`;
        if (!seen.has(key)) {
          seen.add(key);
          uniqueAlternatives.push(alt);
        }
      } catch (e) {
        console.log(`⚠️ 중복 제거 오류: ${e.message}`);
      }
    });
    
    return uniqueAlternatives.slice(0, 5); // 최대 5개 반환
  }
  
  function findSubmitButton(inputElement) {
    // 1. 같은 폼 내에서 submit 버튼 찾기
    const form = inputElement.closest('form');
    if (form) {
      const submitInForm = form.querySelector('input[type="submit"], button[type="submit"], button:not([type])');
      if (submitInForm && submitInForm.offsetParent !== null) {
        return submitInForm;
      }
    }
    
    // 2. 입력 필드 근처의 버튼 찾기 (같은 부모 컨테이너)
    const container = inputElement.closest('div, section, fieldset') || inputElement.parentElement;
    if (container) {
      const nearbyButtons = container.querySelectorAll('button, input[type="submit"]');
      for (const btn of nearbyButtons) {
        if (btn.offsetParent !== null && !btn.closest(`#${EXTENSION_UI_ID}`)) {
          const btnText = btn.textContent.toLowerCase() || btn.value?.toLowerCase() || '';
          // 전송/검색/확인 관련 버튼 키워드
          const submitKeywords = ['전송', '보내기', '검색', '확인', '등록', '제출', 'submit', 'send', 'search', 'go', 'enter'];
          if (submitKeywords.some(keyword => btnText.includes(keyword))) {
            return btn;
          }
        }
      }
      
      // 키워드가 없어도 버튼이 하나뿐이면 해당 버튼 사용
      const visibleButtons = Array.from(nearbyButtons).filter(btn => 
        btn.offsetParent !== null && !btn.closest(`#${EXTENSION_UI_ID}`)
      );
      if (visibleButtons.length === 1) {
        return visibleButtons[0];
      }
    }
    
    // 3. 페이지 전체에서 검색 관련 버튼 찾기
    const searchButtons = document.querySelectorAll('button, input[type="submit"]');
    for (const btn of searchButtons) {
      if (btn.offsetParent !== null && !btn.closest(`#${EXTENSION_UI_ID}`)) {
        const btnText = btn.textContent.toLowerCase() || btn.value?.toLowerCase() || '';
        if (btnText.includes('검색') || btnText.includes('search')) {
          // 입력 필드와 가까운 거리에 있는지 확인
          const inputRect = inputElement.getBoundingClientRect();
          const btnRect = btn.getBoundingClientRect();
          const distance = Math.sqrt(
            Math.pow(inputRect.x - btnRect.x, 2) + Math.pow(inputRect.y - btnRect.y, 2)
          );
          if (distance < 300) { // 300px 이내
            return btn;
          }
        }
      }
    }
    
    return null; // 전송 버튼을 찾지 못함
  }

  function attachUI() {
    if (!SHOULD_RENDER_UI) {
      return;
    }
    if (document.getElementById(EXTENSION_UI_ID)) {
      return;
    }
    
    // 모든 프레임에서 시도 (iframe 포함)
    const frames = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => f.contentDocument).filter(Boolean)];
    
    for (const frame of frames) {
      try {
        const body = frame.body;
        if (!body) {
          continue;
        }
        
        // 이미 존재하는지 확인
        if (frame.getElementById(EXTENSION_UI_ID)) {
          continue;
        }
        
        // UI 복제하여 각 프레임에 주입
        const frameUI = ui.cloneNode(true);
        frameUI.id = EXTENSION_UI_ID;
        
        // 이벤트 리스너 재바인딩
        const input = frameUI.querySelector('input');
        const sendButton = frameUI.querySelector('button');
        const clearButton = frameUI.querySelectorAll('button')[1];
        
        if (input && sendButton && clearButton) {
          // 전송 버튼 이벤트
          sendButton.addEventListener("click", async (e) => {
            e.stopPropagation();
            const message = input.value.trim();
            if (!message) return;
            input.value = '';
            
            await context.setGoal(message);
            actionHistory = context.actionHistory;
            currentPlan = context.currentPlan;
            
            logMessage(`👉 ${message}`);
            await waitUntilReady();
            ws.send(JSON.stringify({ type: "init", message }));
          });
          
          // Clear 버튼 이벤트
          clearButton.addEventListener("click", async (e) => {
            e.stopPropagation();
            await context.clear();
            actionHistory = context.actionHistory;
            currentPlan = context.currentPlan;
            lastDomSnapshot = context.lastDomSnapshot;
            
            const log = frameUI.querySelector('div');
            if (log) log.innerHTML = "";
            if (input) input.value = "";
            logMessage("🧹 모든 컨텍스트가 초기화되었습니다.");
          });
        }
        
        frame.body.appendChild(frameUI);
        console.log("✅ MCP UI injected in frame:", frame.location?.href || 'main');
        
        // UI가 제거되면 재부착 (각 프레임별로)
        try {
          const reattachObserver = new MutationObserver(() => {
            if (!frame.getElementById(EXTENSION_UI_ID)) {
              setTimeout(() => attachUI(), 100);
            }
          });
          reattachObserver.observe(frame.documentElement, { childList: true, subtree: true });
        } catch (_) {}
        
      } catch (e) {
        console.log("⚠️ 프레임 UI 주입 실패:", e);
      }
    }
  }

  attachUI();
  
  // UI 생성 후 현재 상태 표시
  setTimeout(() => {
    if (context.currentGoal) {
      showCurrentStatus();
    }
  }, 100);


  // === 로그인 대기 UI 함수들 ===
  function showLoginWaitingMode(message) {
    logMessage(`🔐 ${message}`);
    
    // 진행 버튼 생성
    const continueBtn = document.createElement("button");
    continueBtn.textContent = "진행";
    continueBtn.id = "continue-btn";
    continueBtn.style.cssText = `
        background: #28a745; color: white; border: none; 
        padding: 10px 20px; margin: 10px; 
        border-radius: 5px; cursor: pointer;
        font-size: 14px; font-weight: bold;
    `;
    
    continueBtn.onclick = () => {
        // 진행 메시지 전송
        ws.send(JSON.stringify({
            type: "user_continue",
            message: "진행"
        }));
        logMessage("▶️ 로그인 완료 - 자동화 재개 요청");
    };
    
    // UI에 버튼 추가
    const ui = document.getElementById(EXTENSION_UI_ID);
    if (ui) {
        ui.appendChild(continueBtn);
    }
  }

  function hideLoginWaitingMode() {
    const continueBtn = document.getElementById("continue-btn");
    if (continueBtn) {
        continueBtn.remove();
    }
  }

}