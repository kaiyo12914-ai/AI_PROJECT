import chromadb
from chromadb.config import Settings
from datetime import datetime

def test_chromadb_crud():
    try:
        # 1. 首先初始化ChromaDB客戶端
        client = chromadb.PersistentClient(
            path=r"d:\AI\AI_TOOLS\chroma\rag",  # 使用與您系統相同的路徑
            settings=Settings(
                anonymized_telemetry=False,
                is_persistent=True  # 保持數據持久化
            )
        )

        print("\n=== ChromaDB CRUD 测试 ===")

        # 2. 獲取或創建集合
        collection_name = "cm_qna"
        collection = client.get_or_create_collection(name=collection_name)
        print(f"当前集合: {client.list_collections()}")

        # 3. 測試數據準備
        test_id = "test-doc-123"
        test_text = "这是一个用于测试的文档内容"

        # 4. 嘗試寫入數據
        print("\n尝试写入数据...")
        collection.add(
            documents=[test_text],
            metadatas={"source": "test", "timestamp": datetime.now().strftime("%Y-%m-%d")},
            ids=[test_id]
        )

        # 5. 測試查詢
        print("查询数据中...")
        results = collection.query(
            query_texts=["查找这个测试文档"],
            n_results=1,
            include=[chromadb.Documents, chromadb.Metadatas]
        )

        # 6. 顯示結果
        if results['ids'][0]:  # 檢查是否返回了任何結果
            print(f"成功找到 {len(results['ids'][0])} 个匹配的文档")
            for i, doc_id in enumerate(results['ids'][0]):
                print(f"\n文档ID: {doc_id}")
                print(f"内容: {results['documents'][0][i]}")
        else:
            print("没有找到匹配的文档")

    except Exception as e:
        print(f"ChromaDB CRUD 测试失败: {str(e)}")

test_chromadb_crud()