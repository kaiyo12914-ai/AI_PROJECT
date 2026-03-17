# webapps/portal/utils.py

from typing import Optional

def aaadecode(aaa: Optional[str]) -> str:
    """
    解碼規則：
    - 取 aaa 的奇數位字元（1-based）
    - Python index = 0,2,4...
    """
    if not aaa:
        return ""
    return aaa[::2]
