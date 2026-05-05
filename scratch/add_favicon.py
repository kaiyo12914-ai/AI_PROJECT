import os
file_path = r'H:\AI\AI_TOOLS\webapps\englishchat\templates\englishchat\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

head_block = '''  <title>美語學習教室</title>
  <link rel="icon" type="image/png" sizes="32x32" href="{% custom_static 'portal/img/favicon-ai.png' %}?v=3">
  <link rel="icon" type="image/svg+xml" href="{% custom_static 'portal/img/favicon-ai.svg' %}?v=3">
  <link rel="shortcut icon" href="{% custom_static 'portal/img/favicon-ai.png' %}?v=3">
  <link rel="stylesheet" href="{% custom_static 'englishchat/css/index.css' %}">'''

content = content.replace('  <title>美語學習教室</title>\n  <link rel="stylesheet" href="{% custom_static \'englishchat/css/index.css\' %}">', head_block)

with open(file_path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
