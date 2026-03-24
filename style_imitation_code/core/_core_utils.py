import re
import sys
import os

def smart_read_text(file_path, max_len=None):
    """
    智能读取中文小说，防止崩溃，同时拦截彻底的乱码文件。
    """
    # 1. 尝试常用中文编码库 (GB18030 是 GBK 的超集，容错率极高)
    encodings_to_try = ['utf-8', 'gb18030', 'utf-16']
    text = None
    
    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                text = f.read(max_len) if max_len else f.read()
            return text  # 只要有一种能完美读取，直接返回
        except UnicodeDecodeError:
            continue
            
    # 2. 如果主流编码全军覆没，开启容错模式读取（丢弃无法识别的坏字节）
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read(max_len) if max_len else f.read()
            
        # 3. 乱码质检：如果容错后读出来的内容里，常见中文标点和汉字太少，说明基本全是乱码
        # 随便取前 1000 个字符进行抽样检测
        sample = text[:1000]
        # 计算常见中文字符的密度（使用正则匹配汉字）
        chinese_chars = re.findall(r'[\u4e00-\u9fa5，。！？“”]', sample)
        
        if len(sample) > 100 and (len(chinese_chars) / len(sample)) < 0.2:
            raise Exception("文件读取后汉字密度过低，判定为乱码或格式损坏，已拦截。")
            
        print("⚠️ 警告：文件存在非法字节，已强行修复并清理乱码碎片。")
        return text
        
    except Exception as e:
        print(f"error: 文件解析彻底失败 - {e}")
        sys.exit(1)
