import sys
try:
    import chromadb
    print(f"chromadb version: {chromadb.__version__}")
    from chromadb.api.types import ReadLevel
    print("Import ReadLevel OK")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
