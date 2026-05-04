from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


TOPIC_PACKS: Dict[str, Dict[str, Any]] = {
    "travel": {
        "labels": ["travel", "trip", "airport", "hotel", "旅遊"],
        "fill_blank": [
            {"question_id": "pack-travel-fill-001", "question": "I would like to ____ a room for two nights.", "choices": ["book", "buy", "borrow"], "answer": "book", "explanation_zh": "book a room 表示預訂房間。", "pattern": "I would like to + V ..."},
            {"question_id": "pack-travel-fill-002", "question": "Could you ____ me how to get to the station?", "choices": ["tell", "say", "speak"], "answer": "tell", "explanation_zh": "tell me how to... 表示告訴我如何做某事。", "pattern": "Could you tell me how to + V ...?"},
            {"question_id": "pack-travel-fill-003", "question": "How long does it ____ to get there?", "choices": ["take", "spend", "cost"], "answer": "take", "explanation_zh": "How long does it take...? 表示需要多久。", "pattern": "How long does it take to + V ...?"},
            {"question_id": "pack-travel-fill-004", "question": "Where can I ____ my luggage?", "choices": ["pick up", "pick", "pick out"], "answer": "pick up", "explanation_zh": "pick up luggage 表示領取行李。", "pattern": "Where can I + V ...?"},
            {"question_id": "pack-travel-fill-005", "question": "Is breakfast ____ in the price?", "choices": ["included", "including", "include"], "answer": "included", "explanation_zh": "be included 表示被包含。", "pattern": "Is + noun + included?"},
        ],
        "reorder": [
            {"question_id": "pack-travel-reorder-001", "prompt": "Put the words in the correct order.", "words": ["like", "I", "to", "book", "a room", "would"], "answer": "I would like to book a room.", "explanation_zh": "would like to 後面接原形動詞。", "pattern": "I would like to + V ..."},
            {"question_id": "pack-travel-reorder-002", "prompt": "Put the words in the correct order.", "words": ["you", "tell", "Could", "me", "the way"], "answer": "Could you tell me the way?", "explanation_zh": "Could you tell me...? 是問路常用句。", "pattern": "Could you tell me + noun clause?"},
            {"question_id": "pack-travel-reorder-003", "prompt": "Put the words in the correct order.", "words": ["does", "How long", "take", "it", "to get there"], "answer": "How long does it take to get there?", "explanation_zh": "How long does it take...? 詢問所需時間。", "pattern": "How long does it take to + V ...?"},
            {"question_id": "pack-travel-reorder-004", "prompt": "Put the words in the correct order.", "words": ["can", "Where", "pick up", "I", "my luggage"], "answer": "Where can I pick up my luggage?", "explanation_zh": "Where can I...? 用來詢問地點。", "pattern": "Where can I + V ...?"},
            {"question_id": "pack-travel-reorder-005", "prompt": "Put the words in the correct order.", "words": ["breakfast", "Is", "included", "the price", "in"], "answer": "Is breakfast included in the price?", "explanation_zh": "included in 表示包含在其中。", "pattern": "Is + noun + included in + noun?"},
        ],
        "translation": [
            {"question_id": "pack-travel-translate-001", "zh_prompt": "我想預訂一間房間。", "sample_answer": "I would like to book a room.", "explanation_zh": "book a room 是預訂房間的自然說法。", "patterns": ["I would like to + V ...", "book a room"]},
            {"question_id": "pack-travel-translate-002", "zh_prompt": "你可以告訴我車站怎麼走嗎？", "sample_answer": "Could you tell me how to get to the station?", "explanation_zh": "Could you tell me how to...? 是問路常用句。", "patterns": ["Could you tell me how to + V ...?", "get to + place"]},
            {"question_id": "pack-travel-translate-003", "zh_prompt": "到那裡需要多久？", "sample_answer": "How long does it take to get there?", "explanation_zh": "How long does it take...? 詢問時間長度。", "patterns": ["How long does it take to + V ...?"]},
            {"question_id": "pack-travel-translate-004", "zh_prompt": "我在哪裡可以領行李？", "sample_answer": "Where can I pick up my luggage?", "explanation_zh": "pick up my luggage 表示領取行李。", "patterns": ["Where can I + V ...?", "pick up luggage"]},
            {"question_id": "pack-travel-translate-005", "zh_prompt": "早餐包含在價格裡嗎？", "sample_answer": "Is breakfast included in the price?", "explanation_zh": "included in the price 表示包含在價格中。", "patterns": ["Is + noun + included?", "included in the price"]},
        ],
    },
    "meeting": {
        "labels": ["meeting", "work", "office", "briefing", "會議", "工作"],
        "fill_blank": [
            {"question_id": "pack-meeting-fill-001", "question": "Let's ____ the main points first.", "choices": ["review", "reviewing", "reviewed"], "answer": "review", "explanation_zh": "let's 後面接原形動詞。", "pattern": "Let's + V ..."},
            {"question_id": "pack-meeting-fill-002", "question": "Could you ____ the agenda with everyone?", "choices": ["share", "sharing", "shared"], "answer": "share", "explanation_zh": "Could you 後面接原形動詞。", "pattern": "Could you + V ...?"},
            {"question_id": "pack-meeting-fill-003", "question": "We need to ____ a decision today.", "choices": ["make", "do", "take"], "answer": "make", "explanation_zh": "make a decision 是固定搭配。", "pattern": "need to + V ..."},
            {"question_id": "pack-meeting-fill-004", "question": "Can we ____ this item until next week?", "choices": ["postpone", "postponing", "postponed"], "answer": "postpone", "explanation_zh": "Can we 後面接原形動詞。", "pattern": "Can we + V ...?"},
            {"question_id": "pack-meeting-fill-005", "question": "Please ____ me if I missed anything.", "choices": ["correct", "correcting", "corrected"], "answer": "correct", "explanation_zh": "Please 後面接原形動詞。", "pattern": "Please + V ..."},
        ],
        "reorder": [
            {"question_id": "pack-meeting-reorder-001", "prompt": "Put the words in the correct order.", "words": ["review", "the", "main points", "Let's", "first"], "answer": "Let's review the main points first.", "explanation_zh": "Let's 後面接原形動詞。", "pattern": "Let's + V ... first."},
            {"question_id": "pack-meeting-reorder-002", "prompt": "Put the words in the correct order.", "words": ["share", "Could", "the agenda", "you"], "answer": "Could you share the agenda?", "explanation_zh": "Could you...? 是禮貌請求。", "pattern": "Could you + V ...?"},
            {"question_id": "pack-meeting-reorder-003", "prompt": "Put the words in the correct order.", "words": ["need", "to", "make", "a decision", "We"], "answer": "We need to make a decision.", "explanation_zh": "need to 後面接原形動詞。", "pattern": "We need to + V ..."},
            {"question_id": "pack-meeting-reorder-004", "prompt": "Put the words in the correct order.", "words": ["postpone", "Can", "this item", "we"], "answer": "Can we postpone this item?", "explanation_zh": "Can we...? 用於提出建議或請求。", "pattern": "Can we + V ...?"},
            {"question_id": "pack-meeting-reorder-005", "prompt": "Put the words in the correct order.", "words": ["me", "Please", "correct", "if I missed anything"], "answer": "Please correct me if I missed anything.", "explanation_zh": "Please correct me 是請對方修正。", "pattern": "Please + V ... if ..."},
        ],
        "translation": [
            {"question_id": "pack-meeting-translate-001", "zh_prompt": "我們先看一下重點。", "sample_answer": "Let's review the main points first.", "explanation_zh": "review the main points 是會議常用說法。", "patterns": ["Let's + V ...", "review the main points"]},
            {"question_id": "pack-meeting-translate-002", "zh_prompt": "你可以分享議程嗎？", "sample_answer": "Could you share the agenda?", "explanation_zh": "share the agenda 是會議常用說法。", "patterns": ["Could you + V ...?", "share the agenda"]},
            {"question_id": "pack-meeting-translate-003", "zh_prompt": "我們今天需要做決定。", "sample_answer": "We need to make a decision today.", "explanation_zh": "make a decision 是做決定的固定搭配。", "patterns": ["need to + V ...", "make a decision"]},
            {"question_id": "pack-meeting-translate-004", "zh_prompt": "我們可以把這項延到下週嗎？", "sample_answer": "Can we postpone this item until next week?", "explanation_zh": "postpone 表示延期。", "patterns": ["Can we + V ...?", "postpone until + time"]},
            {"question_id": "pack-meeting-translate-005", "zh_prompt": "如果我漏掉什麼，請糾正我。", "sample_answer": "Please correct me if I missed anything.", "explanation_zh": "Please correct me 是自然請求修正。", "patterns": ["Please + V ...", "if I missed anything"]},
        ],
    },
    "restaurant": {
        "labels": ["restaurant", "food", "order", "餐廳", "點餐"],
        "fill_blank": [
            {"question_id": "pack-restaurant-fill-001", "question": "Could I ____ the chicken sandwich?", "choices": ["have", "has", "having"], "answer": "have", "explanation_zh": "Could I have...? 是點餐常用句。", "pattern": "Could I have + noun?"},
            {"question_id": "pack-restaurant-fill-002", "question": "I'd like ____ water, please.", "choices": ["some", "any", "many"], "answer": "some", "explanation_zh": "I'd like some... 是自然點餐說法。", "pattern": "I'd like some + noun."},
            {"question_id": "pack-restaurant-fill-003", "question": "Can we ____ the check, please?", "choices": ["have", "take", "make"], "answer": "have", "explanation_zh": "have the check 表示請拿帳單。", "pattern": "Can we have + noun?"},
            {"question_id": "pack-restaurant-fill-004", "question": "Is this dish ____?", "choices": ["spicy", "spice", "spiced"], "answer": "spicy", "explanation_zh": "spicy 是形容詞，表示辣。", "pattern": "Is this dish + adjective?"},
            {"question_id": "pack-restaurant-fill-005", "question": "Could we ____ a table for four?", "choices": ["get", "got", "getting"], "answer": "get", "explanation_zh": "Could we get...? 是自然請求。", "pattern": "Could we get + noun?"},
        ],
        "reorder": [
            {"question_id": "pack-restaurant-reorder-001", "prompt": "Put the words in the correct order.", "words": ["I", "Could", "have", "the chicken sandwich"], "answer": "Could I have the chicken sandwich?", "explanation_zh": "Could I have...? 是禮貌點餐句型。", "pattern": "Could I have + noun?"},
            {"question_id": "pack-restaurant-reorder-002", "prompt": "Put the words in the correct order.", "words": ["like", "some water", "I'd", "please"], "answer": "I'd like some water, please.", "explanation_zh": "I'd like... 是點餐常用句。", "pattern": "I'd like + noun."},
            {"question_id": "pack-restaurant-reorder-003", "prompt": "Put the words in the correct order.", "words": ["have", "Can", "the check", "we", "please"], "answer": "Can we have the check, please?", "explanation_zh": "Can we have...? 可用來請服務生拿東西。", "pattern": "Can we have + noun?"},
            {"question_id": "pack-restaurant-reorder-004", "prompt": "Put the words in the correct order.", "words": ["this dish", "Is", "spicy"], "answer": "Is this dish spicy?", "explanation_zh": "Is + 主詞 + 形容詞？是基本疑問句。", "pattern": "Is + noun + adjective?"},
            {"question_id": "pack-restaurant-reorder-005", "prompt": "Put the words in the correct order.", "words": ["get", "Could", "a table for four", "we"], "answer": "Could we get a table for four?", "explanation_zh": "a table for four 表示四人桌。", "pattern": "Could we get + noun?"},
        ],
        "translation": [
            {"question_id": "pack-restaurant-translate-001", "zh_prompt": "我可以點雞肉三明治嗎？", "sample_answer": "Could I have the chicken sandwich?", "explanation_zh": "Could I have...? 比 I want... 更自然禮貌。", "patterns": ["Could I have + noun?", "I'd like + noun."]},
            {"question_id": "pack-restaurant-translate-002", "zh_prompt": "我想要一些水，謝謝。", "sample_answer": "I'd like some water, please.", "explanation_zh": "I'd like some... 是禮貌點餐句。", "patterns": ["I'd like some + noun.", "please"]},
            {"question_id": "pack-restaurant-translate-003", "zh_prompt": "我們可以結帳嗎？", "sample_answer": "Can we have the check, please?", "explanation_zh": "have the check 表示拿帳單。", "patterns": ["Can we have + noun?", "the check"]},
            {"question_id": "pack-restaurant-translate-004", "zh_prompt": "這道菜會辣嗎？", "sample_answer": "Is this dish spicy?", "explanation_zh": "spicy 是形容詞，表示辣。", "patterns": ["Is this dish + adjective?", "spicy"]},
            {"question_id": "pack-restaurant-translate-005", "zh_prompt": "我們可以要一張四人桌嗎？", "sample_answer": "Could we get a table for four?", "explanation_zh": "a table for four 是四人桌。", "patterns": ["Could we get + noun?", "a table for four"]},
        ],
    },
    "self_intro": {
        "labels": ["self", "intro", "introduction", "自我介紹"],
        "fill_blank": [
            {"question_id": "pack-self-fill-001", "question": "I ____ in the IT department.", "choices": ["work", "works", "working"], "answer": "work", "explanation_zh": "主詞 I 搭配原形動詞 work。", "pattern": "I work in + department."},
            {"question_id": "pack-self-fill-002", "question": "I'm responsible ____ system maintenance.", "choices": ["for", "to", "with"], "answer": "for", "explanation_zh": "be responsible for 是固定搭配。", "pattern": "be responsible for + noun/V-ing"},
            {"question_id": "pack-self-fill-003", "question": "I have ____ in network security.", "choices": ["experience", "experienced", "experiencing"], "answer": "experience", "explanation_zh": "have experience in... 表示有某方面經驗。", "pattern": "have experience in + field"},
            {"question_id": "pack-self-fill-004", "question": "My main job is to ____ users.", "choices": ["support", "supports", "supporting"], "answer": "support", "explanation_zh": "is to 後面接原形動詞。", "pattern": "My main job is to + V ..."},
            {"question_id": "pack-self-fill-005", "question": "I enjoy ____ new tools.", "choices": ["learning", "learn", "learned"], "answer": "learning", "explanation_zh": "enjoy 後面接 V-ing。", "pattern": "I enjoy + V-ing."},
        ],
        "reorder": [
            {"question_id": "pack-self-reorder-001", "prompt": "Put the words in the correct order.", "words": ["work", "I", "in", "the IT department"], "answer": "I work in the IT department.", "explanation_zh": "基本句序是主詞 + 動詞 + 地點。", "pattern": "I work in + place."},
            {"question_id": "pack-self-reorder-002", "prompt": "Put the words in the correct order.", "words": ["responsible", "I'm", "for", "system maintenance"], "answer": "I'm responsible for system maintenance.", "explanation_zh": "responsible for 是固定搭配。", "pattern": "I'm responsible for + noun."},
            {"question_id": "pack-self-reorder-003", "prompt": "Put the words in the correct order.", "words": ["experience", "I", "in", "network security", "have"], "answer": "I have experience in network security.", "explanation_zh": "have experience in 表示具備某領域經驗。", "pattern": "I have experience in + field."},
            {"question_id": "pack-self-reorder-004", "prompt": "Put the words in the correct order.", "words": ["main job", "My", "is", "to support users"], "answer": "My main job is to support users.", "explanation_zh": "My main job is to... 可介紹工作內容。", "pattern": "My main job is to + V ..."},
            {"question_id": "pack-self-reorder-005", "prompt": "Put the words in the correct order.", "words": ["enjoy", "I", "learning", "new tools"], "answer": "I enjoy learning new tools.", "explanation_zh": "enjoy 後面接 V-ing。", "pattern": "I enjoy + V-ing."},
        ],
        "translation": [
            {"question_id": "pack-self-translate-001", "zh_prompt": "我在資訊部門工作。", "sample_answer": "I work in the IT department.", "explanation_zh": "work in 可用於部門或領域。", "patterns": ["I work in + department.", "I'm responsible for + noun/V-ing."]},
            {"question_id": "pack-self-translate-002", "zh_prompt": "我負責系統維護。", "sample_answer": "I'm responsible for system maintenance.", "explanation_zh": "be responsible for 是負責某事的常用搭配。", "patterns": ["I'm responsible for + noun.", "system maintenance"]},
            {"question_id": "pack-self-translate-003", "zh_prompt": "我有網路安全方面的經驗。", "sample_answer": "I have experience in network security.", "explanation_zh": "have experience in 可用於自我介紹專長。", "patterns": ["I have experience in + field.", "network security"]},
            {"question_id": "pack-self-translate-004", "zh_prompt": "我的主要工作是支援使用者。", "sample_answer": "My main job is to support users.", "explanation_zh": "My main job is to... 可說明主要職責。", "patterns": ["My main job is to + V ...", "support users"]},
            {"question_id": "pack-self-translate-005", "zh_prompt": "我喜歡學習新工具。", "sample_answer": "I enjoy learning new tools.", "explanation_zh": "enjoy 後面接 V-ing。", "patterns": ["I enjoy + V-ing.", "learn new tools"]},
        ],
    },
    "phone": {
        "labels": ["phone", "call", "telephone", "電話"],
        "fill_blank": [
            {"question_id": "pack-phone-fill-001", "question": "May I ____ a message?", "choices": ["take", "make", "do"], "answer": "take", "explanation_zh": "take a message 表示幫忙留訊息。", "pattern": "May I take a message?"},
            {"question_id": "pack-phone-fill-002", "question": "Could you ____ the line, please?", "choices": ["hold", "keep", "stay"], "answer": "hold", "explanation_zh": "hold the line 表示電話中請稍候。", "pattern": "Could you hold the line?"},
            {"question_id": "pack-phone-fill-003", "question": "I'll ____ you back later.", "choices": ["call", "talk", "speak"], "answer": "call", "explanation_zh": "call you back 表示回電給你。", "pattern": "I'll call you back + time."},
            {"question_id": "pack-phone-fill-004", "question": "Who is ____?", "choices": ["calling", "called", "call"], "answer": "calling", "explanation_zh": "Who is calling? 用來詢問來電者。", "pattern": "Who is calling?"},
            {"question_id": "pack-phone-fill-005", "question": "Could you ____ that, please?", "choices": ["repeat", "repeated", "repeating"], "answer": "repeat", "explanation_zh": "Could you repeat that? 表示請對方再說一次。", "pattern": "Could you repeat that?"},
        ],
        "reorder": [
            {"question_id": "pack-phone-reorder-001", "prompt": "Put the words in the correct order.", "words": ["take", "May", "a message", "I"], "answer": "May I take a message?", "explanation_zh": "May I...? 是禮貌詢問。", "pattern": "May I + V ...?"},
            {"question_id": "pack-phone-reorder-002", "prompt": "Put the words in the correct order.", "words": ["hold", "Could", "the line", "you"], "answer": "Could you hold the line?", "explanation_zh": "Could you...? 是禮貌請求。", "pattern": "Could you + V ...?"},
            {"question_id": "pack-phone-reorder-003", "prompt": "Put the words in the correct order.", "words": ["call", "I'll", "you", "back", "later"], "answer": "I'll call you back later.", "explanation_zh": "call someone back 表示回電。", "pattern": "I'll call you back + time."},
            {"question_id": "pack-phone-reorder-004", "prompt": "Put the words in the correct order.", "words": ["is", "Who", "calling"], "answer": "Who is calling?", "explanation_zh": "Who is calling? 是電話常用句。", "pattern": "Who is calling?"},
            {"question_id": "pack-phone-reorder-005", "prompt": "Put the words in the correct order.", "words": ["repeat", "Could", "that", "you"], "answer": "Could you repeat that?", "explanation_zh": "repeat that 表示再說一次。", "pattern": "Could you repeat that?"},
        ],
        "translation": [
            {"question_id": "pack-phone-translate-001", "zh_prompt": "我可以幫您留訊息嗎？", "sample_answer": "May I take a message?", "explanation_zh": "take a message 是電話應對常用搭配。", "patterns": ["May I + V ...?", "take a message"]},
            {"question_id": "pack-phone-translate-002", "zh_prompt": "可以請您稍等一下嗎？", "sample_answer": "Could you hold the line, please?", "explanation_zh": "hold the line 是電話中請稍候。", "patterns": ["Could you + V ...?", "hold the line"]},
            {"question_id": "pack-phone-translate-003", "zh_prompt": "我稍後回電給你。", "sample_answer": "I'll call you back later.", "explanation_zh": "call you back 表示回電給你。", "patterns": ["I'll + V ... later.", "call you back"]},
            {"question_id": "pack-phone-translate-004", "zh_prompt": "請問是哪位來電？", "sample_answer": "Who is calling?", "explanation_zh": "Who is calling? 是詢問來電者。", "patterns": ["Who is calling?", "This is + name."]},
            {"question_id": "pack-phone-translate-005", "zh_prompt": "你可以再說一次嗎？", "sample_answer": "Could you repeat that?", "explanation_zh": "Could you repeat that? 是請對方重複。", "patterns": ["Could you repeat that?", "say that again"]},
        ],
    },
}


def find_topic_pack(topic: str) -> Dict[str, Any] | None:
    q = (topic or "").strip().lower()
    if not q:
        return None
    for pack in TOPIC_PACKS.values():
        labels = [str(x).lower() for x in pack.get("labels", [])]
        if any(label and (label in q or q in label) for label in labels):
            return pack
    return None


def get_topic_pack_item(
    topic: str,
    item_type: str,
    level: str | None = None,
    exclude_ids: List[str] | None = None,
) -> Dict[str, Any] | None:
    pack = find_topic_pack(topic)
    if not pack:
        return None
    items: List[Dict[str, Any]] = pack.get(item_type, [])
    if not items:
        return None
    excluded = {str(x) for x in (exclude_ids or []) if str(x)}
    for item in items:
        if str(item.get("question_id")) not in excluded:
            return deepcopy(item)
    return deepcopy(items[0])
