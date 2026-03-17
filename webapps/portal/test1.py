import urllib.parse

# 原始URL
url = "https://mpcai.mpc.mil.tw/comment//?aaa=Hy1o2u1r3a5s6t5u7p8i"

# 解析URL，提取查詢參數
query_params = urllib.parse.urlparse(url).query

# 將查詢字符串轉換為字典
params_dict = urllib.parse.parse_qs(query_params)

# 提取 'aaa' 參數的值（注意可能會是列表，因為同一個key可以有多個值）
aaa_value = params_dict.get('aaa', [''])[0]

print(f"原始值: {aaa_value}")

# 進行奇數位保留和偶數位移除操作
result = []

# 使用索引(從1開始計算，即第一個字元是奇數位)
for i, char in enumerate(aaa_value):
    # 如果索引+1是奇數(1,3,5...)，則保留這個字元
    if (i + 1) % 2 == 1:
        result.append(char)

# 將結果轉換為字串
processed_value = ''.join(result)
print(f"處理後的值: {processed_value}")

# 重建完整的URL
new_url = urllib.parse.urlunparse((
    url.split('://')[0] + '://',
    *urllib.parse.urlsplit(url)[1:4],
    params_dict['aaa'][0].replace(aaa_value, processed_value),
    ''
))

print(f"新的URL: {new_url}")