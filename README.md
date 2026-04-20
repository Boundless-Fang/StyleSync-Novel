codex/f0
# StyleSync-Novel

一个面向小说创作场景的 AI 产品原型，用于探索 `LLM + 风格分析 + RAG` 在长文本续写、同人衍生和创作辅助中的应用。

## 项目定位

StyleSync-Novel 不是一个已经商业化部署的在线平台，而是一个本地可运行的 MVP 原型。  
它更适合作为：

- AI 写作产品原型
- 本地可测试的创作辅助工具
- AI 产品经理方向的作品集项目

当前项目重点解决三个高频问题：

- 角色设定容易漂移
- 长篇续写时上下文容易遗忘
- 多轮生成后文风不稳定

## 适用用户

- 小说原作者：希望在控制成本的前提下做连载续写和内容补全
- 同人创作者：希望在保留原著设定和风格的前提下生成衍生内容

## 核心能力

- 参考文本风格分析：提取叙事节奏、句段结构、词汇偏好、修辞倾向
- 世界观与角色设定抽取：生成结构化世界观和角色信息卡
- 分层 RAG 检索：通过摘要到正文映射提升长文本上下文召回效率
- 章节大纲生成：根据剧情简述与设定动态生成详细大纲
- 正文流式生成：支持基于前文上下文的章节续写
- 文本校验与后续扩展：预留剧情推演和一致性校验能力

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
├── docs/
├── dictionaries/
├── tests/
├── requirements.txt
└── README.md
```

说明：

- `style_imitation_code/`：核心代码
- `docs/`：技术文档
- `tests/`：接口测试与本地测试 GUI
- `dictionaries/`：词库与预留配置目录

以下目录属于运行期数据，不建议上传到公开仓库：

- `reference_novels/`
- `text_style_imitation/`
- `novel_projects/`
- `text_testing_code/`

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

项目根目录已提供可公开上传的配置模板：[.env.example](/D:/StyleSync-Novel/.env.example)。

建议先复制一份：

```powershell
Copy-Item .env.example .env
```

然后再填写你自己的真实密钥。`.env` 不应上传到 GitHub。

至少包含：

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

## 测试

项目当前提供两种测试方式：

### 1. 命令行运行 `pytest`

```powershell
pytest tests
```

当前已补充的测试文件：

- `tests/test_chat_api.py`
- `tests/test_workflow_api.py`
- `tests/test_project_api.py`

这些测试主要验证：

- 接口参数校验是否生效
- 任务接口返回结构是否稳定
- 项目创建、章节读写等基础行为是否正常

### 2. 本地图形界面测试面板

为了避免逐个手动运行测试文件，项目提供了一个轻量 GUI：

```powershell
python tests/0_test_runner_gui.py
```

功能包括：

- 勾选运行指定测试文件
- 一键运行全部测试
- 查看测试输出
- 中途终止当前测试

## 当前实现状态

已完成的主流程：

- 参考文本统计与风格特征提取
- 关键词库、世界观、角色信息抽取
- 分层 RAG 检索库构建
- 大纲生成与正文流式生成
- 任务终止能力：支持“终止最近任务”和“终止全部任务”

规划中的下一阶段能力：

- 剧情方向自动推演
- 跨章节事实一致性校验
- 文风偏移量化监测
- 角色状态时间线与版本控制

## 当前限制

- 当前主要面向本地运行，不是线上托管产品
- 超长文本处理仍受本地算力和 API 窗口限制影响
- 生成质量仍依赖参考文本质量、提示词设计与召回效果
- 测试仍以接口层和最小回归为主，尚未覆盖完整端到端生成链路

## 仓库说明

这个仓库更适合公开展示“代码、文档、测试骨架和产品思路”，而不是上传全部运行数据。

建议公开保留：

- `style_imitation_code/`
- `docs/`
- `tests/`
- `.env.example`
- `requirements.txt`
- `README.md`

建议忽略：

- `.env`
- 原著文本与生成结果
- 本地模型缓存
- 虚拟环境
- 临时脚本与个人调试残留
- `cs.py`

## 反馈与后续

如果你愿意测试这个项目，最有价值的反馈包括：

- 哪个功能最有价值
- 哪个步骤最难理解
- 生成结果最不满意的地方
- 是否愿意继续使用，为什么

## 文档导航

- GitHub 首页说明：当前文档
- 技术文档：[docs/technical-design.md](docs/technical-design.md)
- 旧版详细说明：[功能说明文档.txt](功能说明文档.txt)
# StyleSync-Novel 系统说明文档

## 一、 项目概述
本项目是一个基于大语言模型（Large Language Model）与检索增强生成（RAG）技术的自动化小说续写与风格模仿系统。系统通过本地自然语言处理算法与大模型API的协同工作，旨在解决长文本生成过程中常见的角色设定偏离、上下文记忆遗忘以及行文风格不一致等工程问题。项目主要服务于同人小说衍生创作与原创小说连载辅助生成。

## 二、 技术架构


本系统采用前后端分离与多进程任务调度的架构设计，核心技术栈如下：
* **后端路由与并发调度**：使用 FastAPI 构建接口服务，采用 `asyncio` 提供进程级别的并发锁控制（通过 Semaphore 分离计算密集型任务与网络IO密集型任务）。
* **自然语言处理与向量库**：集成 Jieba 进行本地中文分词与词性分析；使用 `BAAI/bge-m3` 模型进行文本向量化编码；集成 FAISS (Facebook AI Similarity Search) 构建本地离线向量数据库，实现高维空间相似度检索。
* **大语言模型接口**：接入 DeepSeek V3（标准对话模型）与 DeepSeek R1（深度推理模型），系统底层兼容标准的 Server-Sent Events (SSE) 流式输出协议。
* **版本与存储控制**：依赖本地文件系统（I/O）进行物理目录级的状态管理，所有生成设定均以纯文本或 Markdown 格式落盘，并使用 Git 进行代码版本迭代控制。

## 三、 核心工作流与已实现功能
目前系统已完整实现功能一至功能五的闭环执行逻辑：

### 1. 文本特征与物理指标提取
* **统计分析**：通过本地 Python 脚本读取全量参考文本，计算段落长度方差、长短句分布、标点符号密度、词性分布以及基础词汇丰富度（对数 Type-Token Ratio, TTR）。
* **深层特征**：对原文样本进行长度切片并输入大模型，提取其叙事节奏、视角倾向、心理描写途径及修辞手法特征，生成系统级文风约束文件（`features.md`）。

### 2. 词库清洗与设定实体提取
* **高频词过滤**：利用动态算法（基于文本长度的立方根与TTR对数因子）限制高频词提取上限，避免长文本导致的计算资源溢出。
* **设定信息抽离**：针对提取的核心实体，在全量文本中执行高相关度检索。将检索返回的片段交由大模型处理，生成结构化的世界观设定（`world_settings.md`）与独立的角色信息卡（存储于 `character_profiles/` 目录）。

### 3. 剧情压缩与分层检索库构建


* **动态切分与摘要**：通过正则表达式识别章节节点，按固定阈值（默认10000字）将原著切分为物理文本块。提取每个文本块的核心实体，生成包含基础信息的局部伪摘要。
* **层级关联映射**：将局部伪摘要进行向量化处理并存入 FAISS 索引，同时建立摘要至原始物理长文本块的 JSON 映射关系（`chunks.json`）。在后续生成时，计算向量相似度召回摘要，进而映射出对应数万字的精确前文背景。

### 4. 章节大纲与流式正文生成
* **动态约束注入**：在生成新章节大纲前，系统读取用户输入的剧情简述，通过字符串匹配算法动态筛选并仅加载相关的角色信息卡，降低大模型上下文窗口的参数冗余度。
* **流式异步生成**：依据前置生成的世界观设定、章节大纲及前文检索上下文，组装最终的系统级与用户级提示词（Prompt）。调用大模型 API 执行正文生成，前端接收 SSE 数据流并进行实时页面交互渲染与本地文件追加写入。

## 四、 物理目录与工程结构
系统依赖预设的绝对路径结构进行数据流转与持久化存储：
<pre>
StyleSync-Novel/                   # 项目根目录
│
# 【静态代码仓库结构】 (Git 追踪部分) 
├── style_imitation_code/          # 核心代码引擎大本营
│   ├── api/                       # 后端接口路由与任务管理
│   │   ├── config.py / models.py / tasks.py # 配置、数据模型与并发任务管道
│   │   ├── routecore.py           # 核心对话流与嵌入高速接口
│   │   ├── routeproject.py        # 项目层级数据读写与沙箱隔离
│   │   └── routeworkflow.py       # 自动化流水线生命周期调度
│   ├── core/                      # 底层核心封装工具包
│   │   ├── _core_config.py        # 底层路径与环境变量声明
│   │   ├── _core_llm.py           # LLM 同步/流式网络请求底层
│   │   ├── _core_rag.py           # FAISS 向量检索与代理编码机制
│   │   └── _core_utils.py         # 包含 smart_read_text 的防灾文本解析器
│   ├── frontend/                  # 前端静态资源目录
│   │   └── index.html / app.js / style.css 
│   ├── scripts/                   # 业务自动化独立执行脚本 (f0-f7)
│   │   ├── f0_local_vector_indexer.py
│   │   └── f1a_... 到 f5b_... 等
│   ├── tools/                     # 工具箱脚本目录
│   ├── main.py                    # FastAPI 主程序入口与服务挂载点
│   ├── cs.py                      # 内部测试/占位脚本
│   ├── test_api.py                # 硅基流动等三方 API 连通性测试脚本
│   └── 0_readmd.txt               # 局部补充说明文档
├── .gitignore                     # Git 忽略规则配置
├── README.md                      # 项目基础开源说明
├── requirements.txt               # Python 环境依赖清单
├── 功能说明文档.txt               # 系统详细说明文档
│
# 【动态运行生成结构】 (代码执行后自动生成)
├── reference_novels/              # 输入层：外部参考小说原著文本存储区
├── text_style_imitation/          # 数据层：全局文风特征文档与 RAG 索引存储区
├── novel_projects/                # 业务层：具体创作项目沙箱与分层 RAG 库
├── dictionaries/                  # 字典库（配置声明，未来扩展预留）
└── text_testing_code/             # 测试代码区（配置声明，未来扩展预留）
</pre>
## 五、 部署与运行环境配置
本系统的环境搭建需满足 Python 3.9 及以上语言版本要求。

### 1. 配置环境变量
将系统代码拉取至本地环境后，在根目录层级创建 `.env` 配置文件，声明大语言模型调用凭证：
```text
DEEPSEEK_API_KEY=在此处填入有效的API密钥
```

### 2. 构建虚拟环境与安装依赖
在系统终端（Terminal）中执行以下指令，隔离项目运行环境并配置必要的第三方代码库：
```bash
python -m venv venv

# 激活虚拟环境 (Windows环境)
venv\Scripts\activate
# 激活虚拟环境 (Linux/macOS环境)
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 启动后端服务
在已激活虚拟环境的终端中，运行主入口文件启动 FastAPI 服务：
```bash
python style_imitation_code/main.py
```
服务启动后，本地进程默认监听 `0.0.0.0:8000` 端口。前端静态资源及接口调用均由该根路由提供支撑服务。

## 六、 待实现功能与系统优化规划
根据工程需求说明，以下功能模块与高阶运算逻辑已完成理论设计，属于下一阶段的开发排期目标：

1. **功能六（剧情方向自动化推演）**：计划开发遍历历史前文摘要数据集的查询算法，定向提取处于休眠状态的线索实体（如未消耗的关键道具或隐退角色）。结合大语言模型推演多分支可能的剧情走向。
2. **功能七（跨维度文本事实校验）**：计划引入生成后的闭环验证逻辑。提取新生成文本的动事实体并进行向量比对，拦截违背既定世界观设定或物理逻辑的异常输出数据。
3. **算法权重与版本控制优化**：计划在词汇提取阶段引入 TF-IDF 与 TextRank 算法。通过与开源双语语料库（如 ECDICT）对比，筛除低价值数据，并为高价值词汇分配浮点数学权重。同时计划对角色信息卡建立带章节锚点的时间线版本控制机制。
main
