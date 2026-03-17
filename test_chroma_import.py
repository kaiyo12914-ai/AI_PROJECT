import traceback
import sys

print(f"Python executable: {sys.executable}")
print(f"Python path: {sys.path}")

try:
    import chromadb
    print("Successfully imported chromadb")
    print(f"Chromadb file: {chromadb.__file__}")
except Exception as e:
    print("Failed to import chromadb")
    traceback.print_exc()
