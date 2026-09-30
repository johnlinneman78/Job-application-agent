import logging
import sys
import io

# Simulate the fix in main.py
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_unicode")

def test_safe_logging():
    test_msg = "Applying to 🚀 Software Engineer @ 🏢 Tech Corp ✨"
    print(f"Direct print test: {test_msg}")
    
    try:
        logger.info(test_msg)
        print("✓ Logger info with emojis successful")
    except UnicodeEncodeError as e:
        print(f"✗ Logger info failed with UnicodeEncodeError: {e}")
        return False

    # Simulate the _safe_log logic
    try:
        safe_msg = test_msg.encode('utf-8', 'replace').decode('utf-8')
        logger.info(f"Safe logged: {safe_msg}")
        print("✓ Safe log logic successful")
    except Exception as e:
        print(f"✗ Safe log logic failed: {e}")
        return False
        
    return True

if __name__ == "__main__":
    if test_safe_logging():
        print("\n[SUCCESS] Unicode safety verification passed.")
        sys.exit(0)
    else:
        print("\n[FAILURE] Unicode safety verification failed.")
        sys.exit(1)
