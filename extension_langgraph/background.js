// LangGraph Web Agent Background Service Worker
chrome.runtime.onInstalled.addListener(() => {
    console.log('LangGraph Web Agent 확장 프로그램이 설치되었습니다');
    
    // 기본 설정 초기화
    chrome.storage.sync.set({
        wireframeEnabled: true,
        vectorstoreEnabled: true
    });
});

// 탭 업데이트 시 content script 주입
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.url && 
        (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
        
        // content script 주입
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ['content.js']
        }).catch(err => {
            console.log('Content script 주입 실패:', err);
        });
    }
});

// 확장 프로그램 아이콘 클릭 시 사이드패널 열기
chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ windowId: tab.windowId });
});

// 메시지 라우팅
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Background에서 메시지 수신:', message.type);
    
    switch (message.type) {
        case 'langgraph_workflow_update':
            // 사이드패널로 워크플로우 업데이트 전송
            chrome.runtime.sendMessage(message);
            break;
            
        case 'langgraph_connection_status':
            // 사이드패널로 연결 상태 전송
            chrome.runtime.sendMessage(message);
            break;
            
        case 'langgraph_error':
            // 사이드패널로 오류 전송
            chrome.runtime.sendMessage(message);
            break;
            
        case 'langgraph_completed':
            // 사이드패널로 완료 상태 전송
            chrome.runtime.sendMessage(message);
            break;
    }
    
    sendResponse({ received: true });
});

// 확장 프로그램 시작 시 초기화
chrome.runtime.onStartup.addListener(() => {
    console.log('LangGraph Web Agent 시작됨');
});
