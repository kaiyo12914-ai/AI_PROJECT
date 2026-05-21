DIGITAL_TWIN_LEVELS = [
    {
        "twin_level": "Level 1",
        "level_name": "實體設備層",
        "description": "設備、產線、機台、治具、工件、物理空間與生產資產。",
        "related_systems": ["Equipment", "Line", "Machine", "Fixture", "Workpiece", "Sensor Mount"],
        "example_data": ["設備清單", "產線配置圖", "機台規格", "工件資料", "治具資料"],
        "use_cases": ["設備盤點", "產線配置管理", "資產履歷"],
    },
    {
        "twin_level": "Level 2",
        "level_name": "資料擷取層",
        "description": "Sensor、PLC、SCADA、有線資料擷取、OPC UA、Modbus 與工業乙太網。",
        "related_systems": ["Sensor", "PLC", "SCADA", "OPC UA", "Modbus", "Industrial Ethernet", "IoT"],
        "example_data": ["PLC 訊號", "SCADA 資料", "溫度", "壓力", "振動", "電流", "稼動率"],
        "use_cases": ["狀態監控", "訊號擷取", "資料品質檢核"],
    },
    {
        "twin_level": "Level 3",
        "level_name": "資料整合層",
        "description": "MES、CIM、QMS、WMS、CMMS、ETL、API、資料治理與主資料管理。",
        "related_systems": ["MES", "CIM", "QMS", "WMS", "CMMS", "ETL", "API", "MDM"],
        "example_data": ["製令", "工單", "製程路由", "品質檢驗資料", "維修紀錄", "批號追溯"],
        "use_cases": ["跨系統整合", "製程追溯", "資料治理"],
    },
    {
        "twin_level": "Level 4",
        "level_name": "模型模擬層",
        "description": "Simulation、製程模型、產能模型、品質模型、FMEA、RCA 與可靠度模型。",
        "related_systems": ["Simulation", "FMEA", "RCA", "Process Model", "Capacity Model"],
        "example_data": ["模擬參數", "產能分析", "瓶頸分析", "FMEA 表", "RCA 報告"],
        "use_cases": ["瓶頸分析", "異常根因分析", "風險模型"],
    },
    {
        "twin_level": "Level 5",
        "level_name": "決策優化層",
        "description": "ERP、APS、AI、最佳化、預測性維護、風險預警與管理儀表板。",
        "related_systems": ["ERP", "APS", "AI", "Optimization", "Dashboard"],
        "example_data": ["生產計畫", "交期", "成本", "排程結果", "預測性維護建議", "KPI"],
        "use_cases": ["決策支援", "預測性維護", "資源配置"],
    },
]

SYSTEM_LEVEL_MAP = {
    "ERP": ("Level 5", "決策優化層"),
    "MES": ("Level 3", "資料整合層"),
    "APS": ("Level 5", "決策優化層"),
    "CIM": ("Level 3", "資料整合層"),
    "SCADA": ("Level 2", "資料擷取層"),
    "PLC": ("Level 2", "資料擷取層"),
    "IoT": ("Level 2", "資料擷取層"),
    "Sensor": ("Level 2", "資料擷取層"),
    "AI": ("Level 5", "決策優化層"),
    "Simulation": ("Level 4", "模型模擬層"),
    "FMEA": ("Level 4", "模型模擬層"),
    "RCA": ("Level 4", "模型模擬層"),
    "CMMS": ("Level 3", "資料整合層"),
    "QMS": ("Level 3", "資料整合層"),
    "WMS": ("Level 3", "資料整合層"),
}

ISA95_KEYWORDS = {
    "Level 0": ["感測", "物理製程", "設備動作"],
    "Level 1": ["PLC", "控制", "感測器", "致動器"],
    "Level 2": ["SCADA", "HMI", "監控", "資料擷取"],
    "Level 3": ["MES", "CIM", "QMS", "WMS", "CMMS", "工單", "製程", "維修"],
    "Level 4": ["ERP", "APS", "計畫", "排程", "成本", "資源"],
}


def classify_text(text: str) -> dict:
    src = text or ""
    system_type = ""
    twin_level = ""
    for system, (level, _name) in SYSTEM_LEVEL_MAP.items():
        if system.lower() in src.lower():
            system_type = system
            twin_level = level
            break

    if not twin_level:
        for item in DIGITAL_TWIN_LEVELS:
            keywords = item["related_systems"] + item["example_data"] + item["use_cases"]
            if any(k.lower() in src.lower() for k in keywords):
                twin_level = item["twin_level"]
                break

    isa95_level = ""
    for level, keywords in ISA95_KEYWORDS.items():
        if any(k.lower() in src.lower() for k in keywords):
            isa95_level = level
            break

    return {
        "topic": _guess_topic(src),
        "twin_level": twin_level or "Level 3",
        "isa95_level": isa95_level or "Level 3",
        "system_type": system_type,
        "keywords": _keywords(src),
    }


def _guess_topic(text: str) -> str:
    for key in ["數位孿生", "MES", "SCADA", "PLC", "FMEA", "RCA", "預測性維護", "資安", "軍工產線"]:
        if key.lower() in text.lower():
            return key
    return "未分類"


def _keywords(text: str) -> list[str]:
    candidates = set()
    for item in DIGITAL_TWIN_LEVELS:
        for key in item["related_systems"] + item["example_data"] + item["use_cases"]:
            if key.lower() in text.lower():
                candidates.add(key)
    return sorted(candidates)[:20]
