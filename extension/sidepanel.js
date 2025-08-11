document.addEventListener('DOMContentLoaded', () => {
  const log = document.getElementById('log');
  const input = document.getElementById('input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.trim()) {
      const msg = document.createElement('div');
      msg.textContent = '> ' + input.value;
      log.appendChild(msg);
      log.scrollTop = log.scrollHeight;
      input.value = '';
    }
  });
}); 