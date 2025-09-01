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
      const dom = captureDom();
      chrome.runtime.sendMessage({ type: 'DOM_DATA', dom });
    }
  });

  function getSelector(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    while (el && parts.length < 4) {
      let part = el.nodeName.toLowerCase();
      if (el.classList.length) {
        part += '.' + Array.from(el.classList).map(c => CSS.escape(c)).join('.');
      }
      const parent = el.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.nodeName === el.nodeName);
        if (siblings.length > 1) {
          const index = siblings.indexOf(el) + 1;
          part += `:nth-of-type(${index})`;
        }
      }
      parts.unshift(part);
      el = parent;
    }
    return parts.join(' > ');
  }

  function captureDom() {
    const elements = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) {
      const rect = node.getBoundingClientRect();
      if (!rect.width && !rect.height) continue;
      const entry = {
        tag: node.tagName.toLowerCase(),
        selector: getSelector(node)
      };
      if (node.id) entry.id = node.id;
      if (node.name) entry.name = node.name;
      if (node.type) entry.type = node.type;
      if (node.className) entry.class = node.className;
      if (node.href) entry.href = node.href;
      if ('value' in node && node.value) entry.value = node.value;
      const text = node.innerText || '';
      if (text.trim()) entry.text = text.trim().slice(0, 100);
      elements.push(entry);
    }
    return elements;
  }

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
