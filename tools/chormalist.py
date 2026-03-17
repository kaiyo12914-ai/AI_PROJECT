from chromadb.config import Settings
import chromadb

def check_chromadb():
    try:
        # 初始化 Chroma 客户端
        chroma_client = chromadb.PersistentClient(
            path=r"D:\AI\Django\chroma\rag",
            settings=Settings(anonymized_telemetry=False)
        )

        # 获取现有集合（collection）
        try:
            collection = chroma_client.get_collection("cm_qna")

            # 先获取所有ID，再逐批查询
            all_ids = collection.get()["ids"]
            print(f"找到 {len(all_ids)} 个文件：")

            for i, doc_id in enumerate(all_ids[:10]):  # 最多显示前10个
                try:
                    result = collection.get(
                        ids=[doc_id],
                        include=["documents", "metadatas"]
                    )

                    print(f"\n文件ID: {doc_id}")
                    if result["documents"]:
                        print(f"内容: {result['documents'][0][:100]}...")
                    else:
                        print("没有关联的内容")

                    if result["metadatas"]:
                        print("元数据:", result["metadatas"][0])
                except Exception as inner_error:
                    print(f"\n获取文件{doc_id}时出错: {inner_error}")

        except chromadb.api.exceptions.GetCollectionError:
            print("\n未找到名为 'cm_qna' 的集合")
        except Exception as e:
            print(f"\n查询 ChromaDB 失败: {e}")

    except Exception as init_error:
        print(f"\n初始化 Chroma 客户端失败: {init_error}")

if __name__ == "__main__":
    check_chromadb()