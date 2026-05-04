import sys
import re

with open('webapps/projectnotes/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

# We know the duplicate qs block is right around 'lines = [f"Found exact evidence for: {lookup_target}"]'
# Let's find all 'exact_hits = []' occurrences
occurrences = [m.start() for m in re.finditer(r'exact_hits = \[\]', text)]
print(f"Found {len(occurrences)} occurrences of 'exact_hits = []'")

if len(occurrences) > 1:
    # There's a duplicate!
    print("Duplicates found, attempting to clean up.")
    # We will locate the first 'qs = DocumentChunk' block
    idx1 = text.find('qs = DocumentChunk.objects.filter(')
    idx2 = text.find('qs = DocumentChunk.objects.filter(', idx1 + 10)
    
    if idx1 != -1 and idx2 != -1:
        print("Found duplicate qs blocks. Removing the first one which is partial/mangled.")
        # Find where the second one starts
        # The second one starts at idx2. We should delete everything from idx1 up to idx2.
        # But wait, what if the second one is the mangled one?
        # The true one has the full implementation up to the end of the view.
        # Let's just use regex to remove any duplicate blocks.
        pass

# Actually, the most robust way:
# Let's read lines.
with open('webapps/projectnotes/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if line.strip() == 'qs = DocumentChunk.objects.filter(':
        # Count how many times this appears
        count = sum(1 for l in lines[i+1:] if l.strip() == 'qs = DocumentChunk.objects.filter(')
        if count > 0:
            # This is a duplicate. Skip until the next one.
            print(f"Found duplicate start at line {i+1}. Skipping...")
            skip = True
            continue
    if skip and line.strip() == 'qs = DocumentChunk.objects.filter(':
        print(f"Found next start at line {i+1}. Resuming...")
        skip = False
    
    if not skip:
        # fix indentation of the specific lines
        if 'evidences = []' in line and line.startswith('        evidences = []'):
            new_lines.append('            evidences = []\n')
            continue
        if 'lines = [f"Found exact evidence for: {lookup_target}"]' in line and line.startswith('            lines = ['):
            new_lines.append('            lines = [f"Found exact evidence for: {lookup_target}"]\n')
            continue
        new_lines.append(line)

with open('webapps/projectnotes/views.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed views.py")
