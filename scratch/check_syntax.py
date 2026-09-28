import re

with open('static/js/app.js', encoding='utf-8') as f:
    text = f.read()

# We can check with a basic JS parser or scope stack
# Let's count braces to track scope
scopes = [{}]
errors = []

lines = text.split('\n')
for line_no, line in enumerate(lines, 1):
    # Strip string literals and comments
    clean_line = re.sub(r'//.*', '', line)
    clean_line = re.sub(r'"(?:\\.|[^"\\])*"', '""', clean_line)
    clean_line = re.sub(r"'(?:\\.|[^'\\])*'", "''", clean_line)
    clean_line = re.sub(r'`(?:\\.|[^`\\])*`', '``', clean_line)

    for ch in clean_line:
        if ch == '{':
            scopes.append({})
        elif ch == '}':
            if len(scopes) > 1:
                scopes.pop()

    decl_matches = re.findall(r'(?:const|let)\s+([a-zA-Z0-9_]+)\s*=', clean_line)
    curr_scope = scopes[-1]
    for v in decl_matches:
        if v in curr_scope:
            errors.append(f'SyntaxError: Identifier "{v}" has already been declared at line {line_no} (previously line {curr_scope[v]}): {line.strip()[:60]}')
        else:
            curr_scope[v] = line_no

for err in errors:
    print(err)
if not errors:
    print('SUCCESS: No duplicate identifier declarations found in any scope block!')
