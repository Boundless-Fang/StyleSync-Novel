import requests
import json

# ==========================================
# 1. 填入你最新生成的硅基流动 API Key
# ==========================================
API_KEY = "sk-blrjxqvjrjpefkruqufxqyoiitfpjmrjsiktpdaflpyhgxtv"

# 2. 硅基流动的 Embedding 接口地址
URL = "https://api.siliconflow.cn/v1/embeddings"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 3. 准备最简单的测试数据
payload = {
    "model": "BAAI/bge-m3",
    "input": ["你好，这是一条测试文本。", "测试硅基流动的API是否畅通。"]
}

print("🚀 正在向硅基流动发送测试请求...")

try:
    response = requests.post(URL, headers=headers, json=payload, timeout=30)
    
    print("\n" + "="*40)
    print(f"📡 HTTP 状态码: {response.status_code}")
    print("="*40)
    
    if response.status_code == 200:
        data = response.json()
        print("✅ 测试成功！API 完全正常！")
        print(f"📊 成功获取了 {len(data['data'])} 条向量数据。")
        print(f"📏 第一条向量的维度是: {len(data['data'][0]['embedding'])} 维")
        print(f"💰 消耗 Token 数量: {data['usage']['total_tokens']}")
    else:
        print("❌ 测试失败！官方拒绝了请求。")
        print(f"🚨 官方报错原文:\n{response.text}")
        
except Exception as e:
    print(f"💥 发生严重网络/代码错误: {e}")