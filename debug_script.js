// 네이버 페이지에서 실행할 디버깅 스크립트

console.log("=== 확장 프로그램 상태 디버깅 ===");

// 1. 확장 프로그램 로드 여부
console.log("1. 확장 프로그램 주입 여부:", !!window.mcpAgentInjected);

// 2. 컨텍스트 저장소 확인
console.log("2. localStorage 확인:");
console.log("   - mcp-context:", !!localStorage.getItem("mcp-context"));
console.log("   - mcp-goal:", localStorage.getItem("mcp-goal"));

// 3. 저장된 컨텍스트 내용
try {
  const savedContext = localStorage.getItem("mcp-context");
  if (savedContext) {
    const parsed = JSON.parse(savedContext);
    console.log("3. 저장된 컨텍스트:");
    console.log("   - 목표:", parsed.currentGoal);
    console.log("   - 단계:", parsed.step);
    console.log("   - 계획:", parsed.currentPlan?.length || 0, "개");
    console.log("   - 액션:", parsed.actionHistory?.length || 0, "개");
    console.log("   - 상태:", parsed.status);
    console.log("   - 마지막 액션:", parsed.lastActionType);
    console.log("   - 페이지 변경 예상:", parsed.expectedPageChange);
    console.log("   - 평가 대기:", parsed.waitingForEvaluation);
  }
} catch (e) {
  console.log("3. 컨텍스트 파싱 오류:", e);
}

// 4. WebSocket 상태
if (typeof ws !== 'undefined') {
  console.log("4. WebSocket 상태:", ws.readyState);
  // 0: CONNECTING, 1: OPEN, 2: CLOSING, 3: CLOSED
} else {
  console.log("4. WebSocket 변수 없음");
}

// 5. context 객체 확인
if (typeof context !== 'undefined') {
  console.log("5. context 객체 상태:");
  console.log("   - 목표:", context.currentGoal);
  console.log("   - 단계:", context.step);
  console.log("   - 계획:", context.currentPlan?.length || 0);
  console.log("   - shouldSendDomOnPageLoad():", context.shouldSendDomOnPageLoad());
} else {
  console.log("5. context 객체 없음");
}

// 6. UI 요소 확인
const ui = document.getElementById("mcp-ui");
console.log("6. UI 요소 존재:", !!ui);
if (ui) {
  console.log("   - 표시 여부:", ui.style.display !== 'none');
}

console.log("=== 디버깅 완료 ===");
