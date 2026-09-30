import sys
import asyncio
try:
    print("Importing executor...")
    from src.executor import ApplicationExecutor
    print("Executor imported successfully.")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
