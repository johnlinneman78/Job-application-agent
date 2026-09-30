import os
from pathlib import Path

def sanitize_file(path):
    """Try to read file using various encodings and write back as clean UTF-8."""
    # List of encodings to try in order of likelihood on Windows
    encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252', 'latin-1']
    
    try:
        raw_data = path.read_bytes()
        if not raw_data:
            return
            
        content = None
        # Special check for UTF-16 BOM
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            try:
                content = raw_data.decode('utf-16')
            except:
                pass

        if content is None:
            for enc in encodings:
                try:
                    content = raw_data.decode(enc)
                    # Check if it's actually sensible (no null bytes for text files unless it's utf-16)
                    if '\x00' in content and 'utf-16' not in enc:
                        continue
                    break
                except UnicodeDecodeError:
                    continue
        
        if content is None:
            # Last resort: decode as utf-8 but replace errors
            content = raw_data.decode('utf-8', errors='replace')

        # Clean up any remaining broken surrogates or invalid chars
        # that might still be in the string and would trigger Protobuf errors
        safe_content = content.encode('utf-8', errors='replace').decode('utf-8')
        
        # Write back as standard UTF-8 without BOM
        path.write_text(safe_content, encoding='utf-8')
        return True
    except Exception as e:
        print(f"Error processing {path}: {e}")
        return False

def run_sanitization(directory):
    extensions = {'.py', '.md', '.txt', '.log', '.json', '.yaml', '.yml', '.csv'}
    count = 0
    for root, dirs, files in os.walk(directory):
        # Skip internal directories
        if any(x in root for x in ['.git', '.venv', 'venv', 'browser_context', 'brain']):
            continue
            
        for file in files:
            path = Path(root) / file
            if path.suffix.lower() in extensions:
                if sanitize_file(path):
                    count += 1
    print(f"Successfully sanitized {count} files.")

if __name__ == "__main__":
    run_sanitization('.')
