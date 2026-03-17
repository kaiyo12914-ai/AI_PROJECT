import re
from typing import Any

class SensitiveDataFilter:
    """
    軍用商規敏感資訊過濾器
    """
    # 範例關鍵字與模式（可依實務需求擴充）
    SENSITIVE_PATTERNS = [
        (r'\d{2}°\d{2}\'\d{2}\"N\s+\d{3}°\d{2}\'\d{2}\"E', "[座標屏蔽]"), # 座標
        (r'機密|極機密|絕對機密', "***"),
        (r'戰備代號:[A-Z0-9]+', "戰備代號:[已遮蔽]"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        
        redacted_text = text
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            redacted_text = re.sub(pattern, replacement, redacted_text, flags=re.IGNORECASE)
        
        return redacted_text

    @classmethod
    def filter_dict(cls, data: dict) -> dict:
        """
        遞迴過濾字典中的敏感字串
        """
        new_data = {}
        for k, v in data.items():
            if isinstance(v, str):
                new_data[k] = cls.redact(v)
            elif isinstance(v, dict):
                new_data[k] = cls.filter_dict(v)
            elif isinstance(v, list):
                new_data[k] = [cls.filter_dict(i) if isinstance(i, dict) else (cls.redact(i) if isinstance(i, str) else i) for i in v]
            else:
                new_data[k] = v
        return new_data
