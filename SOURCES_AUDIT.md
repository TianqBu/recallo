# 源项目深度审计报告

4 个并行 Explore agent 实地通读 `D:\2026project\sources\` 下源码后的结论。
日期:2026-04-26

---

## 总览

| 项目 | 成熟度 | V1 决策 | V2 决策 | 关键发现 |
|---|---|---|---|---|
| **browser-use** | 3.5/5 | ✅ 锁 v0.12.6 | 持续锁 | 官方 `register_done_callback` 是捕获 Web Trace 的最佳路径 |
| **MinerU** | 4/5 ⭐ | ✅ 用,但子进程 + HTTP | 同 V1 | **没有 Python 库 API**,只有 CLI 和 FastAPI |
| **browser-harness** | 1/5 | ❌ 不依赖 | 借鉴重写 | "self-healing" 是虚假宣传,只是 agent 编辑 helpers.py |
| **stash** | 2.5/5 | ❌ 砍 | ❌ **依然砍** | 几乎不维护(1 commit),双倍部署成本 |

---

## 1. browser-use:能用,但要小心

**成熟度 3.5/5**:77 个测试覆盖核心路径,工程规范严格(Pydantic v2、async),但版本号还在 0.12.x,无 CHANGELOG,无稳定性承诺。

### 真实公开 API
```python
from browser_use import (
    Agent, Browser, BrowserSession, BrowserProfile,
    ChatOpenAI, ChatAnthropic, ChatOllama, ChatGoogle,
    Tools, ActionResult, AgentHistoryList,
)
```

### ⭐ 关键发现:Web Trace 捕获方式
官方一级 API `register_done_callback`(在 service.py 行 151-160 已冻结)就是我们要的:
```python
async def on_step_end(agent: Agent) -> None:
    output = agent.state.last_model_output
    results = agent.state.last_result or []
    # 直接拿到:思考链 / 动作 / 结果 / 截图
    await recallo_db.insert_trace(...)

agent = Agent(task=..., llm=..., register_done_callback=on_step_end)
```
**不需要 monkey-patch,不需要日志解析**。这是项目能干净集成的关键。

### TOP 3 雷区
1. **Windows asyncio**:必须 `WindowsSelectorEventLoopPolicy`,不然 Playwright/CDP 握手挂起
2. **Chromium 路径**:Windows 中文路径 + PATH 大小写敏感性会炸,需 `BROWSER_USE_BROWSER_PATH` 显式指定
3. **0.12.x 不稳定**:Agent.__init__ 参数在 v0.12 内已改 3 次。**必须 pin 到 ==0.12.6**

### 体积警告
pip 装上 ~250MB,首次运行下 Chromium 再 ~250MB,合计 **~600MB**(开源用户能接受,但要在 README 说清)。

---

## 2. MinerU:最成熟的依赖,但集成方式不一样

**成熟度 4/5** ⭐——本批次最成熟。但**集成方式与我们之前想的完全不同**。

### ⚠️ 最重要的修正
**MinerU 没有 `from mineru import parse_pdf` 这种 Python 库 API**。所有调用要么走 CLI 要么走它自带的 FastAPI server。

正确集成方式:
```bash
# 用户后台启动
mineru-api --host 127.0.0.1 --port 8000 --enable-vlm-preload true
```
```python
# Recallo 用 httpx 调本地 API
resp = httpx.post('http://127.0.0.1:8000/file_parse', files={'files': pdf_bytes})
```

这意味着 **Recallo 不是单进程**:Recallo + MinerU API + (浏览器 by browser-use)。

### License 红线
- 协议:**MinerU Open Source License**(基于 Apache 2.0 + 商业阈值)
- 阈值:MAU >1 亿 或 月收入 >$2000 万 才需商业 license
- 必做:在 README/UI 标注 *"PDF parsing powered by MinerU"*(义务)

### CPU-only 真的可行
- pipeline 后端纯 CPU 跑,准确度 85+(VLM 后端 95+ 但要 GPU)
- 模型权重:首次下载 500MB-2GB(`mineru-models-download` 一次性)
- 单页 PDF 解析:**10-30 秒**(预估,文档没标)
- 国内必须 `export MINERU_MODEL_SOURCE=modelscope`(走 ModelScope 镜像)

### 三层 fallback 推荐架构
```python
# recallo/ingestor.py
def ingest_pdf(path):
    try: return mineru_api_parse(path)         # 最高质量,本地服务
    except: pass
    try: return trafilatura.extract(url)        # 轻量,纯 Python
    except: pass
    return arxiv_html_abstract(arxiv_id)        # 最后兜底
```

`trafilatura`(Apache 2.0,~80% 论文文本提取率)是最佳轻量降级,2 行代码。

---

## 3. browser-harness:不要依赖

**成熟度 1/5**(实验性,~600 行,无 PyPI 发布)

### ⚠️ 最大的认知颠覆
**它的 "self-healing" 是虚假宣传**。
源码深读发现:
- daemon.py 只有"failed → retry once on stale session"(line 188-197)
- "skill 体系"(`domain-skills/*.md`)是**人工撰写**的 markdown 文档,不是 agent 动态生成
- 真正的"self-healing"是:agent(比如 Claude Code)自己**编辑 helpers.py 加新函数**

也就是说,browser-harness **没有失败 → LLM 重写 selector 的机制**。

### 其他致命问题
- PyPI 没发布,无法 `pip install`(GitHub release 只有源码)
- `/tmp/` 路径硬编码,Windows 直接挂
- `daemon.py` line 154 monkey-patch `cdp._event_registry.handle_event`(私有 API,版本一升就崩)
- 零真测试(test_*.py 都是浅 stub)

### V2 怎么办
**借鉴思想自己写 ~500-600 行**的 Heal Loop:
- 复用:Unix socket / Named Pipe 中继模式、CDP 透明传递、tab 管理逻辑
- 丢掉:editable install、cloud sync、profile sync
- 新加:失败检测层 + 历史成功路径召回 + LLM selector 修复

但 **V1 完全不需要这层**,我们 V1 就用 browser-use 自带的 `max_failures` 重试。

---

## 4. stash:V2 也不接,自己写 200 行 MCP server

**成熟度 2.5/5**——比想象的差。

### ⚠️ 维护停滞
- 最近只 1 个 commit(2026-04-26)
- 单一作者(alash3al),无团队
- **零测试文件**
- 版本 0.2.0,远未达 1.0

### MCP 实现确实不错
- 用官方 mark3labs/mcp-go SDK,不是自己造轮子
- 暴露 35 个 tools(remember / recall / consolidate / hypothesis / goal / ...)
- 数据模型足够丰富(episodes / facts / causal_links / patterns / hypotheses / goals / failures / contradictions)

### 但部署是灾难
- 双层架构:Recallo (Python+SQLite) + Stash (Go+Postgres) = 双倍运维
- 绑死 PostgreSQL + pgvector,无法换 SQLite
- 强制 OpenAI API(STASH_OPENAI_API_KEY),不能用本地 embedding
- 无法嵌入 Recallo 主进程,只能跨进程 SSE/stdio 调用

### V2 推荐方案:自写 ~200 行 Python MCP server
```python
from mcp.server import Server
import sqlite3

server = Server("recallo", "1.0.0")
db = sqlite3.connect("~/.recallo/memory.db")

@server.tool()
def remember(content: str, namespace: str = "/") -> dict: ...

@server.tool()
def recall(query: str, limit: int = 10) -> list: ...

@server.tool()
def query_facts(namespace: str = "/") -> list: ...
```

收益:
- 单一 Python 进程,无 Postgres / Go 二进制
- 与 Recallo 主代码共享依赖
- 用户可单独跑 server 也可嵌入式用
- ~1-2 天工作量

**stash 整个项目从 Recallo 蓝图里删除**。

---

## 5. 综合架构(基于实地审计)

```
┌──────────────────────────────────────────────────────┐
│  recallo CLI (Python single process)                 │
│  ┌────────────────────────────────────────────────┐  │
│  │  Mind Core                                      │  │
│  │  ├─ Episode 编排                                │  │
│  │  ├─ Memory Lane 召回(SQLite + sqlite-vss)      │  │
│  │  └─ Domain blacklist / 加密                     │  │
│  └────────────────────────────────────────────────┘  │
│              │                       │                │
│              ▼                       ▼                │
│  ┌────────────────────┐   ┌────────────────────┐    │
│  │  Browser Cortex     │   │  Doc Ingestor       │   │
│  │  browser-use Agent  │   │  httpx → MinerU API │   │
│  │  + done_callback    │   │  fallback:          │   │
│  │  → Web Trace        │   │  trafilatura        │   │
│  └────────────────────┘   └────────────────────┘    │
└──────────────────────────────────────────────────────┘
                                      │
                       后台子进程 ────┘
                       ┌──────────────────────┐
                       │ mineru-api server     │
                       │ 127.0.0.1:8000        │
                       │ (用户独立启动)         │
                       └──────────────────────┘

V2 可选:
  recallo-mcp-server (~200 行 Python)
  └── 暴露 SQLite 给外部 Claude/Cursor
```

**主进程依赖**(纯 pip):
```
browser-use==0.12.6
mineru>=3.1.4         # 仅作为 mineru-api 的来源
trafilatura>=1.6      # 降级解析
sqlite-vss            # 向量搜索
httpx                 # 调 mineru-api
mcp                   # V2 MCP server
```

**砍掉**(基于审计):
- ❌ stash(整个项目从蓝图删除)
- ❌ browser-harness(V2 才借鉴重写,V1 不依赖)
- ❌ future-agi(V2 也不必要,Python 内置 logging 够了)
- ❌ Docker / docker-compose(Recallo 自己不需要,MinerU 用户独立装)

---

## 6. V1 集成检查清单(基于深读)

- [ ] requirements 锁版本:`browser-use==0.12.6`,其他用 >= <
- [ ] Windows event loop 策略:CLI 入口 `if sys.platform == 'win32': asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())`
- [ ] 集成方式用 `register_done_callback`,**不要** monkey-patch
- [ ] MinerU 走子进程 + HTTP,**不要** `import mineru`
- [ ] 文档说明用户首次要 `mineru-models-download`(国内加 `export MINERU_MODEL_SOURCE=modelscope`)
- [ ] README 标注 "PDF parsing powered by MinerU"(MinerU 协议要求)
- [ ] THIRD_PARTY_LICENSES.md 列 browser-use(MIT)+ MinerU(MOSL)+ trafilatura(Apache 2.0)+ sqlite-vss(MIT)
- [ ] 三层 fallback:MinerU API → trafilatura → arxiv HTML
- [ ] Web Trace 捕获通过 callback(参考 cortex.py 骨架)
- [ ] Chromium 路径在 README 写清:`BROWSER_USE_BROWSER_PATH` 环境变量

---

## 7. 一句话拍板

**真正能信赖的只有 browser-use 和 MinerU 两个。其他 3 个项目要么是虚假宣传(browser-harness),要么是停滞维护(stash),Recallo 应该用 Python 主进程 + SQLite + 调 browser-use(库) + 调 MinerU(子进程)的极简架构,V1 总依赖 = 5 个 pip 包。**
