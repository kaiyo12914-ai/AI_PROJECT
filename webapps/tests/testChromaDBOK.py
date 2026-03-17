import chromadb
from chromadb.config import Settings

def test_chromadb_connection():
    try:
        # 初始化與您系統中相同的配置
        client = chromadb.PersistentClient(
            path=r"D:\AI\Django\chroma\rag",
            settings=Settings(
                anonymized_telemetry=False,
                is_persistent=True  # 保持數據持久化
            )
        )

        collection_name = "cm_qna"
        collection = client.get_or_create_collection(name=collection_name)

        print("成功连接到ChromaDB")
        print(f"现有集合: {client.list_collections()}")
    except Exception as e:
        print(f"ChromaDB测试失败: {str(e)}")

test_chromadb_connection()