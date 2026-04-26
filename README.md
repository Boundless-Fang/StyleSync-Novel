# StyleSync-Novel

面向小说创作场景的 AI 原型项目。  
它不是“一键出文”工具，而是把创作过程拆成若干可控环节，用来验证长篇创作里的风格控制、设定整理、章节规划、正文生成和局部修改。

## 使用前先准备

启动前只需要先确认 3 件事：

1. Python 3.11 或 3.12
2. `DEEPSEEK_API_KEY`
3. `SILICONFLOW_API_KEY`

说明：

- `DEEPSEEK_API_KEY`：用于聊天、设定补全、大纲生成、正文生成、工作台微调等主流程
- `SILICONFLOW_API_KEY`：用于 embedding / RAG / 检索相关流程；想完整跑通风格分析和知识库能力时需要
- 前端直接加载在线静态资源，建议在中国大陆常见网络环境下使用；如果页面样式、图标或脚本加载不完整，先检查网络

`.env.example` 示例：

```env
DEEPSEEK_API_KEY=your_deepseek_key
SILICONFLOW_API_KEY=your_siliconflow_key
DEFAULT_CHAT_MODEL=deepseek-v4-flash
DEFAULT_EMBEDDING_MODEL=BAAI/bge-m3
```

## 当前已实现功能

- 风格分析
- 词汇库建立
- 世界观提取
- 角色信息卡提取
- 设定补全
- 章节大纲生成
- 正文生成
- 章内局部修改
- 工作台内的提示词注入、复制、查找与微调

## 项目定位

这是一个用于展示和验证 AI 小说创作产品链路的 MVP，重点不是部署上线，而是：

- 验证“先分析、再规划、再生成、再修改”的工作流是否成立
- 验证风格分析、设定整理、章节生成、局部改写能否串成闭环
- 作为 GitHub 作品，用于演示产品思路、原型能力和后续迭代方向

## 主要流程

1. 项目初始化与素材准备
2. 风格分析与词汇整理
3. 世界观 / 人物信息提取
4. 设定补全
5. 章节大纲生成
6. 正文生成
7. 章内局部修改
8. 工作台微调

## 目录结构

```text
StyleSync-Novel/
├─ style_imitation_code/
│  ├─ api/                  # FastAPI 路由与任务接口
│  ├─ core/                 # LLM、RAG、配置与通用能力
│  ├─ frontend/             # 前端工作台
│  ├─ scripts/              # 各阶段脚本
│  └─ main.py               # 启动入口
├─ docs/                    # 设计与评估文档
├─ tests/                   # 接口与流程测试
├─ dictionaries/            # 词典与词汇库
├─ reference_novels/        # 参考文本
├─ text_style_imitation/    # 风格分析相关数据
├─ novel_projects/          # 项目运行产物
├─ requirements.txt
└─ README.md
```

## 快速启动

### 1. 创建虚拟环境并安装依赖

```powershell
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

### 2. 配置 `.env`

```powershell
Copy-Item .env.example .env
```

然后把你的 API Key 填进去。

### 3. 启动项目

```powershell
python style_imitation_code/main.py
```

默认访问：

- <http://127.0.0.1:8000>

## 推荐演示重点

如果你要录视频或做作品展示，优先演示：

- `f5a`：章节大纲生成
- `f5b`：正文生成
- `f5c`：章内局部修改

这三步最能体现“先规划、再生成、再修改”的产品链路。

## 测试

```powershell
python -m pytest tests
```

如需图形化测试入口，可运行：

```powershell
python tests/0_test_runner_gui.py
```
