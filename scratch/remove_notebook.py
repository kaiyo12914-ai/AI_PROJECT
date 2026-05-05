import os
file_path = r'H:\AI\AI_TOOLS\webapps\portal\templates\portal\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('      {% allow "open_notebook" as can_open_notebook %}\n', '')
block = '''      {% if can_open_notebook %}
        {% include "portal/_svg_card.html" with href=open_notebook_url title="Open Notebook" subtitle="Notebook LM / RAG research" tone="green" icon="open_notebook" variant=card_variant new_tab=True %}
      {% endif %}

'''
content = content.replace(block, '')

with open(file_path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
