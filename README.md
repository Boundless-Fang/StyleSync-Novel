# StyleSync-Novel

一个面向小说创作场景的 AI 产品原型，用于探索 `LLM + 风格分析 + RAG` 在长文本续写、同人衍生和创作辅助中的应用。

## 项目定位

StyleSync-Novel 不是一个已经商业化部署的平台，而是一个可本地运行的 MVP 原型。它主要解决长文本创作中三个高频问题：

- 角色设定容易漂移
- 长篇连载时上下文容易遗忘
- 多次续写后文风不稳定

当前项目更适合作为：

- AI 写作产品原型
- 本地可测试的创作辅助工具
- AI 产品经理方向的作品集项目

## 适用用户

- 小说原作者：希望在控制成本的前提下做连载续写和内容补全
- 同人创作者：希望在保留原著风格和设定的前提下生成衍生内容

## 核心能力

- 参考文本风格分析：提取叙事节奏、句段结构、词汇偏好、修辞倾向
- 世界观与角色设定抽取：生成结构化世界观和角色信息卡
- 分层 RAG 检索：通过摘要到正文映射，提升长文本上下文召回效率
- 章节大纲生成：根据剧情简述与设定动态生成详细大纲
- 正文流式生成：支持基于前文上下文的章节续写
- 文本校验与后续扩展：预留剧情推演和事实一致性校验能力

## 技术方案概览

- 后端：FastAPI
- 前端：原生 HTML + JavaScript 静态页面
- 本地 NLP：Jieba、词频统计、文本切分
- 向量检索：FAISS + `BAAI/bge-m3`
- 大模型：DeepSeek 系列模型
- 运行方式：本地主导 + 云端 API 协同

更完整的设计说明见 [docs/technical-design.md](docs/technical-design.md)。

## 项目结构

```text
StyleSync-Novel/
├── style_imitation_code/
│   ├── api/
│   ├── core/
│   ├── frontend/
│   ├── scripts/
│   └── main.py
├── reference_novels/
├── text_style_imitation/
├── novel_projects/
├── dictionaries/
├── text_testing_code/
├── requirements.txt
└── README.md
```

说明：

- `style_imitation_code/`：核心代码
- `reference_novels/`：参考文本输入目录
- `text_style_imitation/`：风格特征与全局 RAG 数据
- `novel_projects/`：具体创作项目目录

## 快速开始

### 1. 准备环境

建议使用 Python 3.11 或 3.12。

创建虚拟环境：

```powershell
python -m venv venv
```

Windows 激活：

```powershell
venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

### 2. 配置 `.env`

在项目根目录创建 `.env` 文件，至少包含：

```env
DEEPSEEK_API_KEY=your_deepseek_key
SILICONFLOW_API_KEY=your_siliconflow_key
```

可选配置：

```env
DEFAULT_CHAT_MODEL=deepseek-chat
DEFAULT_EMBEDDING_MODEL=BAAI/bge-m3
```

### 3. 启动服务

```powershell
python style_imitation_code/main.py
```

启动后访问：

- 本地地址：`http://127.0.0.1:8000`

## 当前实现状态

已完成的主流程：

- 参考文本统计与风格特征提取
- 关键词库、世界观、角色信息抽取
- 分层 RAG 检索库构建
- 大纲生成与正文流式生成

规划中的下一阶段能力：

- 剧情方向自动推演
- 跨章节事实一致性校验
- 文风偏移量化监测
- 角色状态时间线与版本控制

## 当前限制

- 当前主要面向本地运行，不是线上托管产品
- 超长文本处理仍受本地算力和 API 窗口限制影响
- 生成质量仍依赖参考文本质量、提示词设计与召回效果

## 项目价值

这个项目的重点不只是“调用了大模型”，而是尝试把小说创作中真实存在的问题拆成一条完整工作流：

- 风格提取
- 设定抽取
- 检索增强
- 章节生成
- 后续校验

它更适合作为 AI 应用原型和产品思路验证项目，而不是单纯的模型调用 Demo。

## 反馈与后续

如果你愿意测试这个项目，最有价值的反馈包括：

- 哪个功能最有价值
- 哪个步骤最难理解
- 生成结果最不满意的地方
- 是否愿意继续使用，为什么

## 文档导航

- GitHub 首页说明：当前文件
- 技术文档：[docs/technical-design.md](docs/technical-design.md)
- 旧版详细说明：[功能说明文档.txt](功能说明文档.txt)
