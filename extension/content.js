(function(){
  if (window.actionMcpInjected) return;
  window.actionMcpInjected = true;

  window.addEventListener('load', () => {
    chrome.runtime.sendMessage({ type: 'LOAD_COMPLETE' });
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'EXECUTE_ACTION') {
      executeAction(msg.action).then((result) => {
        chrome.runtime.sendMessage({ type: 'ACTION_RESULT', result });
      });
    } else if (msg.type === 'CAPTURE_DOM') {
      const dom = document.documentElement.outerHTML;
      chrome.runtime.sendMessage({ type: 'DOM_DATA', dom });
    }
  });

  async function executeAction(action) {
    try {
      if (action.action === 'click') {
        const el = document.querySelector(action.selector);
        if (el) { el.click(); return { status: 'ok' }; }
        return { status: 'error', reason: 'selector not found' };
      }
      if (action.action === 'fill') {
        const el = document.querySelector(action.selector);
        if (el) {
          el.value = action.value || '';
          el.dispatchEvent(new Event('input', { bubbles: true }));
          return { status: 'ok' };
        }
        return { status: 'error', reason: 'selector not found' };
      }
      if (action.action === 'goto') {
        window.location.href = action.url;
        return { status: 'ok' };
      }
      if (action.action === 'hover') {
        const el = document.querySelector(action.selector);
        if (el) {
          el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
          return { status: 'ok' };
        }
        return { status: 'error', reason: 'selector not found' };
      }
      if (action.action === 'waitUntil') {
        const timeout = action.timeout || 1000;
        await new Promise((r) => setTimeout(r, timeout));
        return { status: 'ok' };
      }
      if (action.action === 'end') {
        return { status: 'ended' };
      }
      return { status: 'error', reason: 'unknown action' };
    } catch (e) {
      return { status: 'error', reason: e.message };
    }
  }
})();
