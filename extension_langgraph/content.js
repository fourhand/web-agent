// LangGraph 기반 웹 에이전트 Content Script
const EXTENSION_UI_ID = "mcp-extension-ui";

// ============================
// Context Management
// ============================
class LangGraphContext {
    constructor() {
        this.currentGoal = "";
        this.currentStep = 0;
        this.totalSteps = 0;
        this.plan = [];
        this.actionHistory = [];
        this.lastDomSnapshot = [];
        this.status = "idle";
        this.errorMessage = null;
        this.workflowId = null;
    }

    async save() {
        const data = {
            goal: this.currentGoal,
            step: this.currentStep,
            totalSteps: this.totalSteps,
            plan: this.plan,
            actionHistory: this.actionHistory,
            lastDomSnapshot: this.lastDomSnapshot,
            status: this.status,
            errorMessage: this.errorMessage,
            workflowId: this.workflowId
        };

        await chrome.storage.local.set({"langgraph-context": data});
        console.log("💾 LangGraph 컨텍스트 저장 완료");
    }

    async restore() {
        try {
            const result = await chrome.storage.local.get("langgraph-context");
            if (result["langgraph-context"]) {
                const data = result["langgraph-context"];
                this.currentGoal = data.goal || "";
                this.currentStep = data.step || 0;
                this.totalSteps = data.totalSteps || 0;
                this.plan = data.plan || [];
                this.actionHistory = data.actionHistory || [];
                this.lastDomSnapshot = data.lastDomSnapshot || [];
                this.status = data.status || "idle";
                this.errorMessage = data.errorMessage || null;
                this.workflowId = data.workflowId || null;
                console.log("✅ LangGraph 컨텍스트 복원 완료");
            }
        } catch (e) {
            console.error("❌ 컨텍스트 복원 실패:", e);
        }
    }

    async clear() {
        this.currentGoal = "";
        this.currentStep = 0;
        this.totalSteps = 0;
        this.plan = [];
        this.actionHistory = [];
        this.lastDomSnapshot = [];
        this.status = "idle";
        this.errorMessage = null;
        this.workflowId = null;
        await chrome.storage.local.remove("langgraph-context");
        console.log("🧹 LangGraph 컨텍스트 초기화 완료");
    }

    setPlan(plan) {
        this.plan = plan;
        this.totalSteps = plan.length;
        this.currentStep = 0;
        this.status = "executing";
    }

    addAction(action) {
        this.actionHistory.push(action);
        this.currentStep = action.step;
        this.lastAction = action;
    }

    setStatus(status, errorMessage = null) {
        this.status = status;
        this.errorMessage = errorMessage;
    }
}

// ============================
// WebSocket Management
// ============================
let ws = null;
const context = new LangGraphContext();

function initWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    
    ws = new WebSocket("ws://localhost:8001/ws");
    
    ws.onopen = () => {
        console.log("✅ LangGraph WebSocket 연결됨");
        logMessage("🔗 LangGraph 서버 연결됨");
        
        // 사이드패널에 연결 상태 전송
        chrome.runtime.sendMessage({
            type: 'langgraph_connection_status',
            connected: true
        });
        
        // 연결 복구 시 이전 상태 복원
        if (context.currentGoal && context.status !== "idle") {
            console.log("🔄 이전 워크플로우 상태 복원 시도");
            restoreWorkflowState();
        }
    };
    
    ws.onclose = () => {
        console.log("🔌 LangGraph WebSocket 연결 해제됨");
        logMessage("❌ LangGraph 서버 연결 해제됨");
        
        // 사이드패널에 연결 상태 전송
        chrome.runtime.sendMessage({
            type: 'langgraph_connection_status',
            connected: false
        });
    };
    
    ws.onerror = (error) => {
        console.error("❌ LangGraph WebSocket 오류:", error);
        logMessage("❌ LangGraph 서버 연결 오류");
    };
    
    ws.onmessage = handleLangGraphMessage;
}

async function waitUntilReady() {
    if (!ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED) {
        initWebSocket();
    }
    
    let retries = 0;
    while (ws.readyState !== WebSocket.OPEN && retries < 20) {
        await new Promise(resolve => setTimeout(resolve, 500));
        retries++;
    }
    
    if (ws.readyState !== WebSocket.OPEN) {
        throw new Error("WebSocket 연결 실패");
    }
}

// 워크플로우 상태 복원
async function restoreWorkflowState() {
    try {
        await waitUntilReady();
        
        // 현재 DOM 스냅샷 전송하여 상태 복원
        const domSnapshot = await summarizeDom();
        
        ws.send(JSON.stringify({
            type: "restore_workflow",
            goal: context.currentGoal,
            current_step: context.currentStep,
            total_steps: context.totalSteps,
            plan: context.plan,
            action_history: context.actionHistory,
            dom: domSnapshot,
            status: context.status
        }));
        
        logMessage("🔄 워크플로우 상태 복원 요청됨");
    } catch (error) {
        console.error("❌ 상태 복원 실패:", error);
        logMessage("❌ 워크플로우 상태 복원 실패");
    }
}

// ============================
// Message Handling
// ============================
async function handleLangGraphMessage(event) {
    console.log("📩 LangGraph 메시지 수신:", event.data);
    const data = JSON.parse(event.data);
    
    switch (data.type) {
        case "workflow_result":
            await handleWorkflowResult(data);
            break;
            
        case "dom_updated":
            logMessage(`📊 ${data.message}`);
            break;
            
        case "action_executed":
            logMessage(`✅ 액션 실행됨: ${data.action.description || data.action.action}`);
            break;
        case "execute_action":
            await handleExecuteAction(data.action);
            break;            break;
            
        case "error":
            logMessage(`❌ 오류: ${data.detail}`);
            context.setStatus("error", data.detail);
            break;
            
        default:
            console.log("📩 알 수 없는 메시지 타입:", data.type);
    }
}

// 사이드패널 메시지 처리
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log("📩 사이드패널 메시지 수신:", message.type);
    
    switch (message.type) {
        case 'start_langgraph_workflow':
            handleStartWorkflow(message.goal);
            break;
            
        case 'stop_langgraph_workflow':
            handleStopWorkflow();
            break;
            
        case 'test_langgraph_connection':
            handleTestConnection();
            break;
            
        case 'settings_changed':
            handleSettingsChanged(message.settings);
            break;
    }
    
    sendResponse({ received: true });
});

async function handleStartWorkflow(goal) {
    try {
        context.currentGoal = goal;
        context.setStatus("planning");
        await context.save();
        
        logMessage("🚀 LangGraph 워크플로우 시작");
        await sendGoal(goal);
        
        // 사이드패널에 상태 업데이트 전송
        chrome.runtime.sendMessage({
            type: 'langgraph_workflow_update',
            status: 'starting',
            currentStep: 0,
            totalSteps: 0,
            log: '워크플로우 시작됨',
            logLevel: 'success'
        });
        
    } catch (error) {
        console.error("❌ 워크플로우 시작 실패:", error);
        chrome.runtime.sendMessage({
            type: 'langgraph_error',
            error: error.message
        });
    }
}

async function handleStopWorkflow() {
    try {
        context.setStatus("stopped");
        await context.save();
        
        logMessage("⏹️ 워크플로우 중지됨");
        
        chrome.runtime.sendMessage({
            type: 'langgraph_workflow_update',
            status: 'stopped',
            log: '워크플로우 중지됨',
            logLevel: 'info'
        });
        
    } catch (error) {
        console.error("❌ 워크플로우 중지 실패:", error);
    }
}

async function handleTestConnection() {
    try {
        await waitUntilReady();
        
        chrome.runtime.sendMessage({
            type: 'langgraph_connection_status',
            connected: true
        });
        
        logMessage("✅ LangGraph 서버 연결 확인됨");
        
    } catch (error) {
        console.error("❌ 연결 테스트 실패:", error);
        
        chrome.runtime.sendMessage({
            type: 'langgraph_connection_status',
            connected: false
        });
        
        logMessage("❌ LangGraph 서버 연결 실패");
    }
}

function handleSettingsChanged(settings) {
    console.log("⚙️ 설정 변경됨:", settings);
    // 설정 변경 처리 로직 추가 가능
}

async function handleWorkflowResult(data) {
    console.log("🎯 워크플로우 결과:", data);
    
    context.setStatus(data.status);
    context.errorMessage = data.error_message;
    
    if (data.plan && data.plan.length > 0) {
        context.setPlan(data.plan);
        logMessage(`🧠 계획 수립 완료: ${data.plan.length}단계`);
        showPlanProgress();
        
        // 사이드패널에 계획 전송
        chrome.runtime.sendMessage({
            type: 'langgraph_workflow_update',
            status: 'planning',
            plan: data.plan,
            totalSteps: data.plan.length,
            log: `계획 수립 완료: ${data.plan.length}단계`,
            logLevel: 'success'
        });
    }
    
    if (data.action_history && data.action_history.length > 0) {
        context.actionHistory = data.action_history;
        context.currentStep = data.current_step;
        const progressPercent = ((data.current_step/data.total_steps)*100).toFixed(1);
        logMessage(`📊 진행률: ${data.current_step}/${data.total_steps} (${progressPercent}%)`);
        
        // 사이드패널에 진행 상황 전송
        chrome.runtime.sendMessage({
            type: 'langgraph_workflow_update',
            status: 'executing',
            currentStep: data.current_step,
            totalSteps: data.total_steps,
            actionHistory: data.action_history,
            log: `진행률: ${data.current_step}/${data.total_steps} (${progressPercent}%)`,
            logLevel: 'info'
        });
    }
    
    if (data.status === "completed") {
        logMessage("🎉 작업 완료!");
        context.setStatus("completed");
        
        chrome.runtime.sendMessage({
            type: 'langgraph_completed',
            log: '작업 완료!',
            logLevel: 'success'
        });
        
    } else if (data.status === "error") {
        logMessage(`❌ 오류: ${data.error_message}`);
        context.setStatus("error", data.error_message);
        
        chrome.runtime.sendMessage({
            type: 'langgraph_error',
            error: data.error_message
        });
    }
    
    await context.save();
}

// ============================
// DOM Processing
// ============================
function summarizeDom() {
    const selector = 'a, button, input, select, textarea, h1, h2, h3, h4, h5, h6, p, div, span, li, td, th, label, img, form, nav, main, section, article, aside, header, footer';
    const candidates = Array.from(document.querySelectorAll(selector));
    const results = [];
    
    for (const el of candidates) {
        // Extension UI 제외
        if (el.id === EXTENSION_UI_ID || el.closest(`#${EXTENSION_UI_ID}`)) {
            continue;
        }
        
        // 숨겨진 요소 제외
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            continue;
        }
        
        // 텍스트 정규화
        const text = (el.innerText || el.textContent || '').trim();
        if (!text && !el.tagName.match(/^(INPUT|TEXTAREA|SELECT|IMG|BUTTON|A)$/i)) {
            continue;
        }
        
        // 요소 정보 추출
        const rect = el.getBoundingClientRect();
        const isClickable = el.tagName.match(/^(A|BUTTON)$/i) || 
                           el.onclick || 
                           el.getAttribute('role') === 'button' ||
                           el.classList.contains('btn') ||
                           el.classList.contains('button');
        
        const isInput = el.tagName.match(/^(INPUT|TEXTAREA|SELECT)$/i);
        
        const item = {
            tag: el.tagName.toLowerCase(),
            text: text.substring(0, 200),
            class: el.className,
            id: el.id,
            selector: generateSelector(el),
            is_clickable: isClickable,
            is_input: isInput,
            rect: {
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height
            }
        };
        
        results.push(item);
    }
    
    return results.slice(0, 500); // 최대 500개 요소로 제한
}

function generateSelector(el) {
    if (el.id) {
        return `#${el.id}`;
    }
    
    if (el.className) {
        const classes = el.className.split(' ').filter(c => c.trim());
        if (classes.length > 0) {
            return `${el.tagName.toLowerCase()}.${classes[0]}`;
        }
    }
    
    return el.tagName.toLowerCase();
}

// ============================
// Action Execution
// ============================
async function executeAction(action) {
    try {
        logMessage(`🤖 액션 실행: ${action.action} - ${action.description || action.text}`);
        
        switch (action.action) {
            case "click":
                await executeClick(action);
                break;
                
            case "fill":
                await executeFill(action);
                break;
                
            case "goto":
                await executeGoto(action);
                break;
                
            case "wait":
                await executeWait(action);
                break;
                
            default:
                logMessage(`⚠️ 알 수 없는 액션: ${action.action}`);
        }
        
        // 액션 실행 후 DOM 업데이트
        setTimeout(() => {
            sendDomUpdate();
        }, 1000);
        
    } catch (error) {
        console.error("❌ 액션 실행 실패:", error);
        logMessage(`❌ 액션 실행 실패: ${error.message}`);
    }
}

async function executeClick(action) {
    const element = document.querySelector(action.selector);
    if (element) {
        element.click();
        logMessage(`✅ 클릭 성공: ${action.text || action.selector}`);
    } else {
        throw new Error(`요소를 찾을 수 없음: ${action.selector}`);
    }
}

async function executeFill(action) {
    const element = document.querySelector(action.selector);
    if (element && (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA')) {
        element.value = action.value || action.text || '';
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        logMessage(`✅ 입력 성공: ${action.value || action.text}`);
    } else {
        throw new Error(`입력 요소를 찾을 수 없음: ${action.selector}`);
    }
}

async function executeGoto(action) {
    if (action.url) {
        window.location.href = action.url;
        logMessage(`🌐 페이지 이동: ${action.url}`);
    } else {
        throw new Error("URL이 없습니다");
    }
}

async function executeWait(action) {
    const duration = action.duration || 2000;
    logMessage(`⏳ 대기 중: ${duration}ms`);
    await new Promise(resolve => setTimeout(resolve, duration));
}

// ============================
// Communication
// ============================
async function sendGoal(goal) {
    try {
        await waitUntilReady();
        
        const message = {
            type: "init",
            message: goal
        };
        
        ws.send(JSON.stringify(message));
        logMessage(`📤 목표 전송: ${goal}`);
        
    } catch (error) {
        console.error("❌ 목표 전송 실패:", error);
        logMessage(`❌ 목표 전송 실패: ${error.message}`);
    }
}

async function sendDomUpdate() {
    try {
        const domElements = summarizeDom();
        context.lastDomSnapshot = domElements;
        
        await waitUntilReady();
        
        const message = {
            type: "dom_with_image",
            dom: domElements,
            image: await captureScreen()
        };
        
        ws.send(JSON.stringify(message));
        logMessage(`📊 DOM 업데이트 전송: ${domElements.length}개 요소`);
        
    } catch (error) {
        console.error("❌ DOM 업데이트 전송 실패:", error);
        logMessage(`❌ DOM 업데이트 전송 실패: ${error.message}`);
    }
}

// ============================
// UI Functions
// ============================
function showPlanProgress() {
    if (context.plan.length > 0) {
        logMessage(`📋 계획: ${context.plan.length}단계`);
        context.plan.forEach((step, index) => {
            const status = index < context.currentStep ? "✅" : index === context.currentStep ? "🔄" : "⏳";
            logMessage(`  ${status} ${step.step}. ${step.description}`);
        });
    }
}

function logMessage(message, level = "info") {
    const logElement = document.querySelector(`#${EXTENSION_UI_ID} div`);
    if (logElement) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement("div");
        logEntry.style.marginBottom = "4px";
        logEntry.style.fontSize = "12px";
        logEntry.style.color = level === "error" ? "#ff4444" : level === "success" ? "#44ff44" : "#000000";
        logEntry.textContent = `[${timestamp}] ${message}`;
        logElement.appendChild(logEntry);
        logElement.scrollTop = logElement.scrollHeight;
    }
    console.log(`[${level.toUpperCase()}] ${message}`);
}

// ============================
// Screen Capture
// ============================
async function captureScreen() {
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        
        // 와이어프레임 생성
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        const elements = document.querySelectorAll('a, button, input, select, textarea, h1, h2, h3, h4, h5, h6, p, div, span, li, td, th, label, img, form, nav, main, section, article, aside, header, footer');
        
        elements.forEach(el => {
            if (el.id === EXTENSION_UI_ID || el.closest(`#${EXTENSION_UI_ID}`)) {
                return;
            }
            
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) {
                return;
            }
            
            const tagName = el.tagName.toLowerCase();
            
            // 요소별 스타일링
            if (tagName === 'button' || tagName === 'a') {
                ctx.fillStyle = '#e3f2fd';
                ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
                ctx.strokeStyle = '#1976d2';
                ctx.lineWidth = 2;
                ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
            } else if (tagName === 'input' || tagName === 'textarea') {
                ctx.fillStyle = '#f5f5f5';
                ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
                ctx.strokeStyle = '#9e9e9e';
                ctx.lineWidth = 1;
                ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
            } else if (tagName.match(/^h[1-6]$/)) {
                ctx.fillStyle = '#fff3e0';
                ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
                ctx.strokeStyle = '#f57c00';
                ctx.lineWidth = 2;
                ctx.strokeRect(rect.left, rect.top, rect.width, rect.height);
            }
            
            // 텍스트 추가
            const text = el.innerText || el.placeholder || el.value || '';
            if (text && rect.width > 20 && rect.height > 10) {
                ctx.fillStyle = '#000000';
                ctx.font = '10px Arial';
                const maxWidth = rect.width - 4;
                const truncatedText = text.length > maxWidth / 6 ? text.substring(0, Math.floor(maxWidth / 6)) + '...' : text;
                ctx.fillText(truncatedText, rect.left + 2, rect.top + rect.height - 4);
            }
        });
        
        return canvas.toDataURL('image/jpeg', 0.7);
        
    } catch (error) {
        console.error('❌ 화면 캡처 실패:', error);
        return null;
    }
}

// ============================
// UI Creation
// ============================
function createUI() {
    if (document.getElementById(EXTENSION_UI_ID)) {
        return;
    }
    
    const ui = document.createElement("div");
    ui.id = EXTENSION_UI_ID;
    ui.style = "position:fixed;bottom:20px;right:20px;width:400px;padding:15px;background:rgba(255,255,255,0.95);border:2px solid #1976d2;border-radius:10px;z-index:2147483647;font-family:sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.15);";
    
    const header = document.createElement("div");
    header.style = "font-weight:bold;margin-bottom:10px;color:#1976d2;font-size:14px;";
    header.textContent = "🤖 LangGraph Web Agent";
    ui.appendChild(header);
    
    const log = document.createElement("div");
    log.style = "max-height:200px;overflow-y:auto;margin-bottom:10px;font-size:12px;color:#333;border:1px solid #ddd;padding:8px;background:#f9f9f9;border-radius:4px;";
    ui.appendChild(log);
    
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "목표를 입력하세요... (예: 네이버에서 최신 메일을 보여줘)";
    input.style = "width:calc(100% - 80px);padding:8px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;font-size:12px;";
    ui.appendChild(input);
    
    const sendButton = document.createElement("button");
    sendButton.textContent = "시작";
    sendButton.style = "width:70px;margin-left:8px;padding:8px;border:1px solid #1976d2;border-radius:4px;background:#1976d2;color:#fff;cursor:pointer;font-size:12px;";
    sendButton.addEventListener("click", async () => {
        const goal = input.value.trim();
        if (!goal) return;
        
        input.value = '';
        context.currentGoal = goal;
        context.setStatus("planning");
        await context.save();
        
        logMessage("🚀 LangGraph 워크플로우 시작");
        await sendGoal(goal);
    });
    ui.appendChild(sendButton);
    
    const clearButton = document.createElement("button");
    clearButton.textContent = "초기화";
    clearButton.style = "width:100%;margin-top:8px;padding:8px;border:1px solid #ddd;border-radius:4px;background:#f5f5f5;color:#333;cursor:pointer;font-size:12px;";
    clearButton.addEventListener("click", async () => {
        await context.clear();
        log.innerHTML = "";
        logMessage("🧹 LangGraph 컨텍스트 초기화됨");
    });
    ui.appendChild(clearButton);
    
    document.body.appendChild(ui);
    logMessage("🚀 LangGraph Web Agent 시작됨");
}

// ============================
// Initialization
// ============================
async function initialize() {
    console.log("🚀 LangGraph Web Agent 초기화 시작");
    
    // 컨텍스트 복원
    await context.restore();
    
    // UI 생성
    createUI();
    
    // WebSocket 연결
    initWebSocket();
    
    // 페이지 로드 완료 후 DOM 전송
    if (context.currentGoal && context.status !== "completed") {
        setTimeout(() => {
            sendDomUpdate();
        }, 2000);
    }
    
    console.log("✅ LangGraph Web Agent 초기화 완료");
}

// 페이지 로드 시 초기화
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    initialize();
}

// 페이지 변경 감지
let currentUrl = window.location.href;
setInterval(() => {
    if (window.location.href !== currentUrl) {
        currentUrl = window.location.href;
        console.log("🌐 페이지 변경 감지:", currentUrl);
        setTimeout(() => {
            sendDomUpdate();
        }, 1000);
    }
}, 1000);
