from __future__ import annotations

from typing import List, Any
import base64
import io

from markitdown import MarkItDown

from model.DCS1_EMAL_FILE import DCS1_EMAL_FILE

# ✅ 統一走 llm_factory（禁止在子系統 new Ollama / 自打 OpenAI HTTP）
from webapps.llm.llm_factory import get_chat_model


def _as_text(x: Any) -> str:
    """
    把 LangChain 回傳統一轉成字串（支援 AIMessage.content / 或直接 str）
    """
    if x is None:
        return ""
    if hasattr(x, "content"):
        try:
            return str(x.content or "")
        except Exception:
            pass
    return str(x)


class docService:
    def __init__(self, model: str = "mistral_small_3_1_2503:latest", *, temperature: float | None = None, timeout: int | None = None):
        """
        model 參數保留（相容舊呼叫點），但實際模型由 .env 的 OLLAMA_MODEL / OPENAI_MODEL 控制。
        若你想讓 model 真的生效，建議改成：在 llm_factory 以 env 控制，不在這裡硬塞。
        """
        self.temperature = temperature
        self.timeout = timeout
        self.llm = get_chat_model(temperature=temperature, timeout=timeout)

    def convert_to_file_list(self, json_data):
        dcsi_emal_files = [DCS1_EMAL_FILE(**item) for item in json_data]
        return dcsi_emal_files

    def summary(self, docFiles: List[DCS1_EMAL_FILE]):
        if len(docFiles) == 0:
            raise Exception("沒有來文附件可供總結")

        context: List[str] = []
        md = MarkItDown()

        for docFile in docFiles:
            # 解碼 Base64 字串
            decoded_data = base64.b64decode(docFile.EF_DATA)
            stream = io.BytesIO(decoded_data)

            md_result = md.convert_stream(stream)
            md_text = (getattr(md_result, "text_content", "") or "").strip()

            md_content = f"檔案名稱：{docFile.EF_NAME}，內容：{md_text}---"
            context.append(md_content)

        context_str = "\n".join(context)

        system_prompt = """
你是軍備局生產製造中心的公文助理，請遵守規則進行任務處理並且只能使用繁體中文回覆，另外可以參考以下資訊以協助你進行總結：
1.有意義的檔案名稱高機率代表來文的文頭，裡面的標題可以先讓你鎖定處理範圍。
2.來文的附件說明會有說明檔名的用途，你可以用這個作為檔案內容參考。
Content:
{context}
""".strip()

        html_output = """
回答時請依照以下要求：
1.用html格式輸出，請用div包住結果即可
2.不用特地告知我是使用html格式回覆
3.去除換行符號(\\n或\\\\n)，改用<br/>
4.不要在結果的頭尾出現「"」與「```」
5.開頭需要請列出發文字號與來文主旨
""".strip()

        # 你原本還有 markdown_output，但目前流程用 html_output；保留註解即可
        # markdown_output = """..."""

        # ✅ 組合成最終 prompt（直接用字串，避免不同 LLM 對 PromptValue 型別不相容）
        final_prompt = f"""{system_prompt}

{html_output}

請總結並條列出Content內的重點
""".strip().format(context=context_str)

        result = self.llm.invoke(final_prompt)
        return _as_text(result).strip()
