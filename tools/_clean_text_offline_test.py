# _clean_text_offline_test.py
# 最小離線測試：驗證 _clean_text() 對 bytes 的解碼與控制字元過濾

import os

# 模擬 SQLtest.py 內的 _clean_text

def _clean_text(val):
    if val is None:
        return ""
    if isinstance(val, (bytes, bytearray, memoryview)):
        b = val.tobytes() if isinstance(val, memoryview) else bytes(val)
        enc = (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "").strip()
        candidates = []
        if enc:
            candidates.append(enc)
        candidates.append("cp950")
        candidates.extend(["utf-8", "latin-1"])
        s = ""
        for e in candidates:
            try:
                s = b.decode(e)
                break
            except Exception:
                continue
        if s == "":
            try:
                s = b.decode(candidates[0], errors="ignore")
            except Exception:
                s = ""
    else:
        s = str(val)
    return "".join(ch for ch in s if ch in ("\n", "\r", "\t") or ord(ch) >= 32)


def main():
    # 測試字串
    text = "簽呈/令/呈/函/便籤 測試"

    # 1) cp950 bytes
    b_cp950 = text.encode("cp950", errors="strict")
    print("[cp950]", _clean_text(b_cp950))

    # 2) utf-8 bytes
    b_utf8 = text.encode("utf-8")
    print("[utf-8]", _clean_text(b_utf8))

    # 3) 帶控制字元
    b_ctrl = (text + "\x00\x01\x02").encode("cp950", errors="ignore")
    print("[ctrl ]", _clean_text(b_ctrl))

    # 4) memoryview / bytearray
    print("[mem  ]", _clean_text(memoryview(b_cp950)))
    print("[barr ]", _clean_text(bytearray(b_cp950)))

    # 5) 若你想模擬不同 charset，設定環境變數
    # os.environ["SYBASE_CHARSET"] = "cp950"


if __name__ == "__main__":
    main()
