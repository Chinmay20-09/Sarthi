with open("hermes/routes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the broken lines and fix them
fixed = 0
for i, line in enumerate(lines):
    if "yield b'event: error" in line and "data" in line:
        lines[i] = "        yield b'event: error\ndata: {\"message\": \"invalid JSON body\"}\n\n'\n"
        fixed += 1
    elif "yield b'event: error" in line and "Message cannot be empty" in line:
        lines[i] = "        yield b'event: error\ndata: {\"message\": \"Message cannot be empty\"}\n\n'\n"
        fixed += 1

with open("hermes/routes.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"Fixed {fixed} lines")
