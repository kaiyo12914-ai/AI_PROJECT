import chromadb
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings
from datetime import datetime

def test_full_pipeline():
    try:
        print("\n=== 运行完整AI管道测试 ===")

        # 1. 初始化Ollama嵌入模型
        emb = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url="http://mpcai.mpc.mil.tw:11434",  # 使用正確的URL
            timeout=30  # 增加超時時間
        )

        # 2. 初始化ChromaDB客戶端和集合
        client = chromadb.PersistentClient(
            path=r"D:\AI\Django\chroma\rag",  # 使用您的路徑
            settings=Settings(anonymized_telemetry=False)
        )

        collection_name = "cm_qna"
        collection = client.get_or_create_collection(name=collection_name)

        # 測試數據準備
        test_text = "这是一个用于验证的样本文档"

        # 3. 測試嵌入功能
        print("\n生成嵌入中...")
        embeddings = emb.embed_documents([test_text])
        if not embeddings:
            raise ValueError("Ollama embedding返回了空结果")
        print(f"嵌入向量长度: {len(embeddings[0])}")

        # 4. 測試ChromaDB寫入
        print("\n写入数据到ChromaDB...")
        collection.add(
            documents=[test_text],
            metadatas={"source": "test", "timestamp": datetime.now().strftime("%Y-%m-%d")},
            ids=["test-doc-123"]
        )

        # 5. 測試查詢功能
        print("\n尝试查询...")
        results = collection.query(
            query_texts=[test_text],
            n_results=1,
            include=[chromadb.Documents, chromadb.Metadatas]
        )

        if not results['ids'][0]:
            raise ValueError("ChromaDB查询返回空结果")

        print(f"找到的结果数: {len(results['ids'][0])}")
        for i, doc_id in enumerate(results['ids'][0]):
            print(f"\n文档ID: {doc_id}")
            print(f"内容: {results['documents'][0][i]}")
            if 'metadatas' in results:
                print(f"元数据: {json.dumps(results['metadatas'][0][i], indent=2)}")

    except Exception as e:
        print(f"\n完整系统测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

# 運行測試
test_full_pipeline()