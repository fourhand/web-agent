# content.js 파일 읽기
with open('../extension/content.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Enter 이벤트 처리에서 진행 명령어 특별 처리 추가
old_enter_handler = '''      const message = input.value.trim();
      if (!message) return;
      input.value = '';
      
      // 컨텍스트에 새로운 목표 설정'''

new_enter_handler = '''      const message = input.value.trim();
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
      
      // 컨텍스트에 새로운 목표 설정'''

content = content.replace(old_enter_handler, new_enter_handler)

# 파일 저장
with open('../extension/content.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 채팅 입력에서 진행 명령어 처리 추가 완료')
