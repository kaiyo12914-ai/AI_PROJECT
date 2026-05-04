from __future__ import annotations

from typing import Any, Dict, List


LEVEL_SETTINGS: Dict[str, Dict[str, str]] = {
    "beginner": {
        "modal": "can",
        "closer": "today",
        "adverb": "carefully",
        "time_phrase": "this morning",
    },
    "intermediate": {
        "modal": "could",
        "closer": "this week",
        "adverb": "efficiently",
        "time_phrase": "before lunch",
    },
    "advanced": {
        "modal": "would",
        "closer": "as soon as possible",
        "adverb": "strategically",
        "time_phrase": "before the deadline",
    },
}


QUESTION_TOPICS: List[Dict[str, Any]] = [
    {
        "key": "travel",
        "labels": ["travel", "trip", "airport", "hotel", "旅遊"],
        "subject": "I",
        "verb": "book",
        "verb_zh": "預訂",
        "items": [
            {"en": "a room", "zh": "房間"},
            {"en": "a shuttle", "zh": "接駁車"},
            {"en": "a train ticket", "zh": "火車票"},
        ],
        "places": [
            {"en": "at the hotel", "zh": "在飯店"},
            {"en": "at the station", "zh": "在車站"},
            {"en": "at the airport", "zh": "在機場"},
        ],
        "synonyms": ["reserve", "arrange"],
    },
    {
        "key": "meeting",
        "labels": ["meeting", "work", "office", "briefing", "會議", "工作"],
        "subject": "we",
        "verb": "review",
        "verb_zh": "檢視",
        "items": [
            {"en": "the agenda", "zh": "議程"},
            {"en": "the action list", "zh": "行動清單"},
            {"en": "the main points", "zh": "重點"},
        ],
        "places": [
            {"en": "in the meeting room", "zh": "在會議室"},
            {"en": "before the briefing", "zh": "在簡報前"},
            {"en": "with the team", "zh": "和團隊一起"},
        ],
        "synonyms": ["go over", "discuss"],
    },
    {
        "key": "restaurant",
        "labels": ["restaurant", "food", "order", "餐廳", "點餐"],
        "subject": "I",
        "verb": "order",
        "verb_zh": "點",
        "items": [
            {"en": "a chicken sandwich", "zh": "雞肉三明治"},
            {"en": "a bowl of soup", "zh": "一碗湯"},
            {"en": "a glass of water", "zh": "一杯水"},
        ],
        "places": [
            {"en": "at the restaurant", "zh": "在餐廳"},
            {"en": "from the menu", "zh": "從菜單上"},
            {"en": "for lunch", "zh": "當作午餐"},
        ],
        "synonyms": ["get", "choose"],
    },
    {
        "key": "self_intro",
        "labels": ["self", "intro", "introduction", "自我介紹"],
        "subject": "I",
        "verb": "support",
        "verb_zh": "支援",
        "items": [
            {"en": "users", "zh": "使用者"},
            {"en": "new staff", "zh": "新進同仁"},
            {"en": "the help desk", "zh": "服務台"},
        ],
        "places": [
            {"en": "in the IT department", "zh": "在資訊部門"},
            {"en": "at work", "zh": "在工作上"},
            {"en": "during office hours", "zh": "在上班時間"},
        ],
        "synonyms": ["assist", "help"],
    },
    {
        "key": "phone",
        "labels": ["phone", "call", "telephone", "電話"],
        "subject": "I",
        "verb": "return",
        "verb_zh": "回覆",
        "items": [
            {"en": "your call", "zh": "你的電話"},
            {"en": "the message", "zh": "留言"},
            {"en": "the voicemail", "zh": "語音訊息"},
        ],
        "places": [
            {"en": "from my desk", "zh": "在我的座位"},
            {"en": "after the meeting", "zh": "在會後"},
            {"en": "before lunch", "zh": "在午餐前"},
        ],
        "synonyms": ["answer", "handle"],
    },
    {
        "key": "shopping",
        "labels": ["shopping", "store", "mall", "購物", "買東西"],
        "subject": "I",
        "verb": "compare",
        "verb_zh": "比較",
        "items": [
            {"en": "the prices", "zh": "價格"},
            {"en": "the sizes", "zh": "尺寸"},
            {"en": "the colors", "zh": "顏色"},
        ],
        "places": [
            {"en": "at the store", "zh": "在商店"},
            {"en": "before I buy anything", "zh": "在購買前"},
            {"en": "with my family", "zh": "和家人一起"},
        ],
        "synonyms": ["check", "look at"],
    },
    {
        "key": "hospital",
        "labels": ["hospital", "clinic", "doctor", "醫院", "看病"],
        "subject": "I",
        "verb": "see",
        "verb_zh": "看",
        "items": [
            {"en": "the doctor", "zh": "醫生"},
            {"en": "the nurse", "zh": "護理師"},
            {"en": "the schedule", "zh": "看診時間"},
        ],
        "places": [
            {"en": "at the clinic", "zh": "在診所"},
            {"en": "this afternoon", "zh": "今天下午"},
            {"en": "before the appointment", "zh": "在預約前"},
        ],
        "synonyms": ["meet", "consult"],
    },
    {
        "key": "school",
        "labels": ["school", "class", "teacher", "學校", "上課"],
        "subject": "we",
        "verb": "finish",
        "verb_zh": "完成",
        "items": [
            {"en": "the homework", "zh": "作業"},
            {"en": "the worksheet", "zh": "學習單"},
            {"en": "the group project", "zh": "分組報告"},
        ],
        "places": [
            {"en": "in class", "zh": "在課堂上"},
            {"en": "before school ends", "zh": "在放學前"},
            {"en": "with our teacher", "zh": "和老師一起"},
        ],
        "synonyms": ["complete", "wrap up"],
    },
    {
        "key": "bank",
        "labels": ["bank", "atm", "account", "銀行"],
        "subject": "I",
        "verb": "check",
        "verb_zh": "查看",
        "items": [
            {"en": "my account", "zh": "我的帳戶"},
            {"en": "the balance", "zh": "餘額"},
            {"en": "the transfer record", "zh": "轉帳紀錄"},
        ],
        "places": [
            {"en": "at the bank", "zh": "在銀行"},
            {"en": "at the ATM", "zh": "在提款機"},
            {"en": "on the app", "zh": "在 App 上"},
        ],
        "synonyms": ["review", "confirm"],
    },
    {
        "key": "delivery",
        "labels": ["delivery", "package", "shipping", "物流", "宅配"],
        "subject": "I",
        "verb": "track",
        "verb_zh": "追蹤",
        "items": [
            {"en": "the package", "zh": "包裹"},
            {"en": "the shipment", "zh": "貨件"},
            {"en": "the delivery status", "zh": "配送狀態"},
        ],
        "places": [
            {"en": "online", "zh": "在線上"},
            {"en": "before it arrives", "zh": "在送達前"},
            {"en": "from my phone", "zh": "用手機"},
        ],
        "synonyms": ["check", "follow"],
    },
    {
        "key": "weather",
        "labels": ["weather", "rain", "forecast", "天氣"],
        "subject": "we",
        "verb": "check",
        "verb_zh": "查看",
        "items": [
            {"en": "the forecast", "zh": "天氣預報"},
            {"en": "the rain chance", "zh": "降雨機率"},
            {"en": "the temperature", "zh": "氣溫"},
        ],
        "places": [
            {"en": "before the trip", "zh": "在出發前"},
            {"en": "every morning", "zh": "每天早上"},
            {"en": "on the weather app", "zh": "在天氣 App 上"},
        ],
        "synonyms": ["review", "look at"],
    },
    {
        "key": "fitness",
        "labels": ["fitness", "gym", "exercise", "健身", "運動"],
        "subject": "I",
        "verb": "finish",
        "verb_zh": "完成",
        "items": [
            {"en": "my workout", "zh": "我的訓練"},
            {"en": "the cardio session", "zh": "有氧課表"},
            {"en": "the warm-up", "zh": "暖身"},
        ],
        "places": [
            {"en": "at the gym", "zh": "在健身房"},
            {"en": "before dinner", "zh": "在晚餐前"},
            {"en": "with my coach", "zh": "和教練一起"},
        ],
        "synonyms": ["complete", "wrap up"],
    },
    {
        "key": "computer",
        "labels": ["computer", "software", "system", "電腦", "軟體"],
        "subject": "I",
        "verb": "update",
        "verb_zh": "更新",
        "items": [
            {"en": "the system", "zh": "系統"},
            {"en": "the software", "zh": "軟體"},
            {"en": "the settings", "zh": "設定"},
        ],
        "places": [
            {"en": "on my computer", "zh": "在我的電腦上"},
            {"en": "before restarting", "zh": "在重新開機前"},
            {"en": "after work", "zh": "下班後"},
        ],
        "synonyms": ["upgrade", "refresh"],
    },
    {
        "key": "customer_service",
        "labels": ["customer service", "support", "complaint", "客服"],
        "subject": "we",
        "verb": "solve",
        "verb_zh": "解決",
        "items": [
            {"en": "the problem", "zh": "問題"},
            {"en": "the complaint", "zh": "客訴"},
            {"en": "the request", "zh": "需求"},
        ],
        "places": [
            {"en": "for the customer", "zh": "為客戶"},
            {"en": "before the deadline", "zh": "在期限前"},
            {"en": "through email", "zh": "透過電子郵件"},
        ],
        "synonyms": ["handle", "fix"],
    },
    {
        "key": "airport",
        "labels": ["airport", "boarding", "flight", "機場"],
        "subject": "I",
        "verb": "confirm",
        "verb_zh": "確認",
        "items": [
            {"en": "my gate", "zh": "我的登機門"},
            {"en": "the boarding time", "zh": "登機時間"},
            {"en": "the flight status", "zh": "航班狀態"},
        ],
        "places": [
            {"en": "at the airport", "zh": "在機場"},
            {"en": "before security", "zh": "在安檢前"},
            {"en": "on the display board", "zh": "在看板上"},
        ],
        "synonyms": ["check", "verify"],
    },
]
