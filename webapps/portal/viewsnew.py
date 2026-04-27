from django.shortcuts import render
from datetime import datetime

def index(request):
    # 获取 aaa 参数
    aaa_value = request.GET.get('aaa', '')

    # 初始化 processed_str 变量
    processed_str = ''

    if aaa_value:  # 如果存在参数值才进行处理
        processed_id = [char for i, char in enumerate(aaa_value) if (i+1) % 2 == 1]
        processed_str = ''.join(processed_id)
        print(f"[用户登录] 原始ID: {aaa_value}")
        if processed_str != aaa_value:
            print(f"[处理后] ID: {processed_str}")

    # 传递给模板
    context = {
        "year": datetime.now().year,
        "original_id": aaa_value,   # 原始ID
        "processed_id": processed_str  # 处理后的ID
    }
    return render(request, "portal/index.html", context)