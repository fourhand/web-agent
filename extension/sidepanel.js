const logEl = document.getElementById('log');
const inputEl = document.getElementById('chatInput');
let ws;

function log(msg) {
  logEl.textContent += `\n${msg}`;
  logEl.scrollTop = logEl.scrollHeight;
}

function connect() {
  ws = new WebSocket('ws://localhost:8001/ws');
  ws.onopen = () => log('🔌 ActionMCP 연결됨');
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'chat') {
      log(`🤖 ${msg.message}`);
    } else if (msg.type === 'action') {
      forwardToTab({ type: 'EXECUTE_ACTION', action: msg.action, step: msg.step });
    } else if (msg.type === 'request_dom') {
      forwardToTab({ type: 'CAPTURE_DOM' });
    }
  };
  ws.onclose = () => {
    log('❌ 연결 종료, 재시도 중...');
    setTimeout(connect, 1000);
  };
}

function forwardToTab(message) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, message);
    }
  });
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (msg.type === 'DOM_DATA') {
    chrome.tabs.captureVisibleTab({ format: 'png' }, (image) => {
      ws.send(JSON.stringify({ type: 'dom_with_image', dom: msg.dom, image }));
    });
  } else {
    ws.send(JSON.stringify(msg));
  }
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && inputEl.value) {
    const text = inputEl.value;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'chat', message: text }));
      log(`🧑 ${text}`);
    }
    inputEl.value = '';
  }
});

connect();
