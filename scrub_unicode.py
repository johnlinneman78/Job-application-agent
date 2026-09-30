import os
from pathlib import Path

def scrub():
    for p in Path('.').rglob('*.py'):
        if 'venv' in str(p) or 'browser_context' in str(p):
            continue
        try:
            content = p.read_text(encoding='utf-8', errors='ignore')
            new_content = ''.join([c if ord(c) < 128 else ' ' for c in content])
            if content != new_content:
                p.write_text(new_content, encoding='utf-8')
                print(f"Scrubbed {p}")
        except Exception as e:
            print(f"Failed to scrub {p}: {e}")

if __name__ == "__main__":
    scrub()
