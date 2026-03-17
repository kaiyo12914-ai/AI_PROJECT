import sys, traceback
try:
    import chromadb
    print('chromadb', chromadb.__version__)
    from chromadb.api.types import ReadLevel
    print('ReadLevel OK', ReadLevel)
except Exception as e:
    print('ERR', repr(e))
    traceback.print_exc()
    sys.exit(1)
