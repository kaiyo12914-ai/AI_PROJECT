from langchain_ollama import OllamaEmbeddings

try:
    # 初始化與您系統中相同的模型和超時
    emb = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url="http://mpcai.mpc.mil.tw:11434",
        timeout=3000  # 增加超時時間
    )

    test_texts = ["测试", "嵌入", "功能"]
    embeddings = emb.embed_documents(test_texts)

    print(f"成功生成 {len(embeddings)} 个嵌入向量")
    for i, text in enumerate(test_texts):
        print(f"文本: '{text}' -> 向量长度: {len(embeddings[i])}")
except Exception as e:
    print(f"Ollama embedding测试失败: {str(e)}")