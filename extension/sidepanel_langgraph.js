// LangGraph Web Agent Sidepanel
class LangGraphSidepanel {
    constructor() {
        this.isConnected = false;
        this.currentGoal = "";
        this.currentStep = 0;
        this.totalSteps = 0;
        this.plan = [];
        this.status = "idle";
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.updateConnectionStatus();
        this.log("LangGraph Web Agent 시작됨", "info");
    }
    
    setupEventListeners() {
        // 시작 버튼
        document.getElementById('startButton').addEventListener('click', () => {
            this.startWorkflow();
        });
        
        // 중지 버튼
        document.getElementById('stopButton').addEventListener('click', () => {
            this.stopWorkflow();
        });
        
        // 테스트 버튼
        document.getElementById('testButton').addEventListener('click', () => {
            this.testConnection();
        });
        
        // 로그 지우기 버튼
        document.getElementById('clearLogButton').addEventListener('click', () => {
            this.clearLog();
        });
        
        // 설정 토글
        document.getElementById('wireframeToggle').addEventListener('change', (e) => {
            this.saveSetting('wireframeEnabled', e.target.checked);
            this.sendSettingsToContent();
        });
        
        document.getElementById('vectorstoreToggle').addEventListener('change', (e) => {
            this.saveSetting('vectorstoreEnabled', e.target.checked);
            this.sendSettingsToContent();
        });
        
        // Enter 키로 시작
        document.getElementById('goalInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.startWorkflow();
            }
        });
    }
    
    async loadSettings() {
        try {
            const result = await chrome.storage.sync.get([
                'wireframeEnabled',
                'vectorstoreEnabled'
            ]);
            
            document.getElementById('wireframeToggle').checked = result.wireframeEnabled !== false;
            document.getElementById('vectorstoreToggle').checked = result.vectorstoreEnabled !== false;
            
        } catch (error) {
            console.error('설정 로드 실패:', error);
        }
    }
    
    async saveSetting(key, value) {
        try {
            await chrome.storage.sync.set({ [key]: value });
            this.log(`설정 저장: ${key} = ${value}`, "info");
        } catch (error) {
            console.error('설정 저장 실패:', error);
        }
    }
    
    async sendSettingsToContent() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'settings_changed',
                    settings: {
                        wireframeEnabled: document.getElementById('wireframeToggle').checked,
                        vectorstoreEnabled: document.getElementById('vectorstoreToggle').checked
                    }
                });
            }
        } catch (error) {
            console.error('설정 전송 실패:', error);
        }
    }
    
    async startWorkflow() {
        const goal = document.getElementById('goalInput').value.trim();
        if (!goal) {
            this.log("목표를 입력해주세요", "warning");
            return;
        }
        
        this.currentGoal = goal;
        this.status = "starting";
        this.updateProgress();
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'start_langgraph_workflow',
                    goal: goal
                });
                
                this.log(`워크플로우 시작: ${goal}`, "success");
            } else {
                this.log("활성 탭을 찾을 수 없습니다", "error");
            }
        } catch (error) {
            this.log(`워크플로우 시작 실패: ${error.message}`, "error");
            this.status = "error";
            this.updateProgress();
        }
    }
    
    async stopWorkflow() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'stop_langgraph_workflow'
                });
                
                this.log("워크플로우 중지됨", "info");
                this.status = "stopped";
                this.updateProgress();
            }
        } catch (error) {
            this.log(`워크플로우 중지 실패: ${error.message}`, "error");
        }
    }
    
    async testConnection() {
        this.log("서버 연결 테스트 중...", "info");
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'test_langgraph_connection'
                });
            }
        } catch (error) {
            this.log(`연결 테스트 실패: ${error.message}`, "error");
        }
    }
    
    updateConnectionStatus() {
        const statusElement = document.getElementById('connectionStatus');
        
        if (this.isConnected) {
            statusElement.textContent = "✅ LangGraph 서버 연결됨";
            statusElement.className = "status connected";
        } else {
            statusElement.textContent = "🔌 LangGraph 서버 연결 중...";
            statusElement.className = "status";
        }
    }
    
    updateProgress() {
        const progressInfo = document.getElementById('progressInfo');
        const progressBar = document.getElementById('progressBar');
        const currentStepElement = document.getElementById('currentStep');
        
        let progressText = "대기 중...";
        let progressPercent = 0;
        
        switch (this.status) {
            case "starting":
                progressText = "워크플로우 시작 중...";
                progressPercent = 10;
                break;
            case "planning":
                progressText = "계획 수립 중...";
                progressPercent = 20;
                break;
            case "executing":
                if (this.totalSteps > 0) {
                    const percent = Math.round((this.currentStep / this.totalSteps) * 60) + 20;
                    progressText = `실행 중... (${this.currentStep}/${this.totalSteps})`;
                    progressPercent = percent;
                } else {
                    progressText = "실행 중...";
                    progressPercent = 30;
                }
                break;
            case "completed":
                progressText = "완료됨!";
                progressPercent = 100;
                break;
            case "error":
                progressText = "오류 발생";
                progressPercent = 0;
                break;
            case "stopped":
                progressText = "중지됨";
                progressPercent = 0;
                break;
        }
        
        progressInfo.textContent = progressText;
        progressBar.style.width = `${progressPercent}%`;
        
        if (this.totalSteps > 0) {
            currentStepElement.textContent = `단계: ${this.currentStep}/${this.totalSteps}`;
        } else {
            currentStepElement.textContent = "단계: -";
        }
    }
    
    log(message, level = "info") {
        const logContainer = document.getElementById('logContainer');
        const timestamp = new Date().toLocaleTimeString();
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;
        logEntry.textContent = `[${timestamp}] ${message}`;
        
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
        
        // 로그 항목이 너무 많으면 오래된 것들 제거
        if (logContainer.children.length > 50) {
            logContainer.removeChild(logContainer.firstChild);
        }
    }
    
    clearLog() {
        const logContainer = document.getElementById('logContainer');
        logContainer.innerHTML = '<div class="log-entry info">로그가 지워졌습니다</div>';
    }
    
    // 메시지 수신 처리
    handleMessage(message) {
        switch (message.type) {
            case 'langgraph_connection_status':
                this.isConnected = message.connected;
                this.updateConnectionStatus();
                if (message.connected) {
                    this.log("LangGraph 서버에 연결됨", "success");
                } else {
                    this.log("LangGraph 서버 연결 해제됨", "warning");
                }
                break;
                
            case 'langgraph_workflow_update':
                this.currentStep = message.currentStep || 0;
                this.totalSteps = message.totalSteps || 0;
                this.status = message.status || "executing";
                this.plan = message.plan || [];
                this.updateProgress();
                
                if (message.log) {
                    this.log(message.log, message.logLevel || "info");
                }
                break;
                
            case 'langgraph_error':
                this.log(`오류: ${message.error}`, "error");
                this.status = "error";
                this.updateProgress();
                break;
                
            case 'langgraph_completed':
                this.log("워크플로우 완료!", "success");
                this.status = "completed";
                this.updateProgress();
                break;
        }
    }
}

// 사이드패널 초기화
document.addEventListener('DOMContentLoaded', () => {
    window.langGraphSidepanel = new LangGraphSidepanel();
});

// 메시지 리스너
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (window.langGraphSidepanel) {
        window.langGraphSidepanel.handleMessage(message);
    }
    sendResponse({ received: true });
});
