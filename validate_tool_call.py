import sys
import re

def main():
    # Read command arguments or stdin
    command_line = ""
    if len(sys.argv) > 1:
        command_line = " ".join(sys.argv[1:])
    else:
        # Read from stdin if no arguments
        command_line = sys.stdin.read().strip()
        
    print(f"[AegisMed Sandbox] Inspecting command: {command_line}", file=sys.stderr)

    # Simple regex to block common destructive commands on Windows and Linux/macOS
    destructive_patterns = [
        r"\brm\s+-rf\b",
        r"\brm\s+-f\b",
        r"\bdel\b.*\b/s\b",
        r"\bdel\b.*\b/q\b",
        r"\brmdir\b.*\b/s\b",
        r"\bformat\b\s+[a-zA-Z]:",
        r"\bshred\b",
        r"\bdd\b\s+if=",
        r"\bdrop\s+database\b",
        r"\bdrop\s+table\b",
    ]

    for pattern in destructive_patterns:
        if re.search(pattern, command_line, re.IGNORECASE):
            print(f"[AegisMed Sandbox] CRITICAL: Destructive command detected! Rule matched: '{pattern}'", file=sys.stderr)
            sys.exit(1)

    print("[AegisMed Sandbox] Command approved.", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
