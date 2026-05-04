import sys

with open('webapps/projectnotes/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'qs = DocumentChunk.objects.filter(' in line:
        print(f'MATCH at line {i+1}: {line.strip()}')
    if 'def api_chat' in line:
        print(f'api_chat at line {i+1}')
