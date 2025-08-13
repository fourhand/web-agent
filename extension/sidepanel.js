document.addEventListener('DOMContentLoaded', () => {
  console.log('🚀 사이드패널 로드됨');
  
  const log = document.getElementById('log');
  const input = document.getElementById('input');
  const wireframeToggle = document.getElementById('wireframeToggle');
  const chunkingToggle = document.getElementById('chunkingToggle');
  const connectionStatus = document.getElementById('connectionStatus');
  const statusText = document.getElementById('statusText');
  
  console.log('🔍 요소 확인:', {
    log: !!log,
    input: !!input,
    wireframeToggle: !!wireframeToggle,
    chunkingToggle: !!chunkingToggle,
    connectionStatus: !!connectionStatus,
    statusText: !!statusText
  });

  // 설정 로드
  loadSettings();

  // 와이어프레임 체크박스 이벤트
  if (wireframeToggle) {
    wireframeToggle.addEventListener('change', (e) => {
      console.log('🎨 와이어프레임 토글 변경:', e.target.checked);
      const enabled = e.target.checked;
      chrome.storage.sync.set({ 'wireframeEnabled': enabled }, () => {
        addLogMessage(`🎨 와이어프레임 이미지 ${enabled ? 'ON' : 'OFF'}`, enabled ? 'success' : 'info');
        
        // content script에 설정 변경 알림
        chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
          if (tabs[0]) {
            chrome.tabs.sendMessage(tabs[0].id, {
              type: 'settings_changed',
              wireframeEnabled: enabled
            });
          }
        });
      });
    });
  } else {
    console.error('❌ wireframeToggle 요소를 찾을 수 없음');
  }

  // DOM 청킹 체크박스 이벤트
  if (chunkingToggle) {
    chunkingToggle.addEventListener('change', (e) => {
      console.log('📦 청킹 토글 변경:', e.target.checked);
      const enabled = e.target.checked;
      chrome.storage.sync.set({ 'chunkingEnabled': enabled }, () => {
        addLogMessage(`📦 DOM 청킹 ${enabled ? 'ON' : 'OFF'}`, enabled ? 'success' : 'info');
      });
    });
  } else {
    console.error('❌ chunkingToggle 요소를 찾을 수 없음');
  }

  // 입력 이벤트
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.trim()) {
      const message = input.value.trim();
      addLogMessage('> ' + message, 'user');
      
      // content script에 메시지 전송
      chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
        if (tabs[0]) {
          chrome.tabs.sendMessage(tabs[0].id, {
            type: 'user_input',
            message: message
          });
        }
      });
      
      input.value = '';
    }
  });

  // content script로부터 메시지 수신
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'log') {
      addLogMessage(message.content, message.level || 'info');
    } else if (message.type === 'connection_status') {
      updateConnectionStatus(message.connected);
    }
  });

  // 로그 메시지 추가 함수
  function addLogMessage(content, level = 'info') {
    const msg = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString();
    
    msg.style.marginBottom = '4px';
    msg.style.fontSize = '11px';
    
    if (level === 'user') {
      msg.style.color = '#2196F3';
      msg.style.fontWeight = 'bold';
    } else if (level === 'error') {
      msg.style.color = '#f44336';
    } else if (level === 'success') {
      msg.style.color = '#4CAF50';
    } else {
      msg.style.color = '#333';
    }
    
    msg.innerHTML = `<span style="color: #999">${timestamp}</span> ${content}`;
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
    
    // 로그가 너무 많으면 오래된 것 제거
    if (log.children.length > 100) {
      log.removeChild(log.firstChild);
    }
  }

  // 연결 상태 업데이트
  function updateConnectionStatus(connected) {
    if (connected) {
      connectionStatus.className = 'status-indicator status-connected';
      statusText.textContent = '서버 연결됨';
    } else {
      connectionStatus.className = 'status-indicator status-disconnected';
      statusText.textContent = '서버 연결 끊김';
    }
  }

  // 설정 로드
  function loadSettings() {
    chrome.storage.sync.get(['wireframeEnabled', 'chunkingEnabled'], (result) => {
      wireframeToggle.checked = result.wireframeEnabled !== false; // 기본값 true
      chunkingToggle.checked = result.chunkingEnabled !== false;   // 기본값 true
      
      addLogMessage(`🎨 와이어프레임: ${wireframeToggle.checked ? 'ON' : 'OFF'}`);
      addLogMessage(`📦 DOM 청킹: ${chunkingToggle.checked ? 'ON' : 'OFF'}`);
    });
  }

  // 초기화
  addLogMessage('🚀 Web Agent 사이드패널이 준비되었습니다');
  addLogMessage('💡 팁: 목표를 입력하고 Enter를 누르세요');
}); 