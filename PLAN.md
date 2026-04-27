# Recallo — Plan v0.3 (audit-aligned)

> Local-first browser agent with long-term memory, focused on paper reading.

基于 `SOURCES_AUDIT.md` 的实地源码审计后,清理掉的最终方案。
日期:2026-04-26

---

## 0. 一句话定位

**Recallo 是一个本地优先、专注论文阅读的浏览器 Agent**:浏览/解析 arxiv 论文,把内容沉淀进本地 SQLite,跨会话精确召回。`pip install recallo` 一行装完,记忆永远在你硬盘里。

---

## 1. 真实依赖清单(基于源码审计)

| 包 | 版本 | 用途 | 备注 |
|---|---|---|---|
| `browser-use` | **==0.12.6** | 浏览器自动化 | 必须 pin,0.12.x 内 API 改过 3 次 |
| `trafilatura` | >=1.6 | 网页/PDF 文本降级解析 | 80% 论文文本提取率 |
| `httpx` | >=0.27 | 调 mineru-api(用户后台启动) | |
| `click` | >=8.1 | CLI | browser-use 已带 |
| `sqlite-vec` | required | 向量召回 | M2 已接入(默认 1536 维) |
| `mineru` | optional extra | 高质量 PDF 解析 | **不 import,用户独立启动 `mineru-api`** |

**已砍**:
- ❌ stash(零测试 + 单作者 + 双部署成本)
- ❌ browser-harness(self-healing 是虚假宣传)
- ❌ future-agi(Python logging 够用)
- ❌ Postgres / pgvector / Docker(SQLite 替代)

---

## 2. 架构(单 Python 进程)

```
recallo (CLI)
    │
    ├─→ Mind Core
    │    ├─ Episode 编排
    │    ├─ Memory Lane(SQLite + sqlite-vec)
    │    └─ Domain Blacklist
    │
    ├─→ Browser Cortex
    │    └─ browser-use Agent + register_new_step_callback → Web Trace
    │
    └─→ Doc Ingestor
         ├─→ httpx → http://127.0.0.1:8000  (MinerU API,用户独立启动)
         └─→ trafilatura(降级)
              └─→ arxiv HTML 抽 abstract(最后兜底)
```

---

## 3. SQLite Schema

`recallo/schema.sql` 三张主表 + FTS5 索引(M1)+ 向量表(M2)。详见 schema.sql。

---

## 4. M1-M4 里程碑

| M | 交付 | 主要工作 |
|---|---|---|
| **M1** | ✅ `pip install -e .` 跑通 | pyproject、CLI 骨架、SQLite init、browser-use spike |
| **M2** | ✅ 能记能召回 | sqlite-vec、OpenAIEmbedder、register_done_callback 提取事实、语义+FTS5 双轨 |
| **M3** | 给陌生人用 | README + GIF、`pip install recallo`、Ollama fallback、demo |
| **M4** | 部分:Memory Replay ✅ | ~~Memory Replay CLI~~、MinerU 三层 fallback、测试 80% |

总计 **1-2 周一个开发者**。

---

## 5. 已锁死的关键决策

| 决策 | 来源 |
|---|---|
| 项目名 Recallo | 命名 agent 实地查证 |
| 主语言 Python 3.11+ | browser-use 强制 |
| 存储 SQLite 单文件 | 红队 + 安装门槛 |
| 垂直化论文阅读切入 | 竞品侦察 + 红队 |
| 协议 Apache 2.0 | 可商用 + 与依赖兼容 |
| browser-use 锁 0.12.6 | 实地源码审计 |
| MinerU 子进程 + HTTP 集成 | 实地源码审计(无 Python lib API) |
| stash 整个砍 | 实地源码审计(零测试 + 维护停滞) |
| 浏览器执行轨迹用 `register_new_step_callback` | 实地源码审计 |
| Windows 留默认 ProactorEventLoop | 实地 `recallo explore` 失败验证 |

---

## 6. 关键风险与对策

| 风险 | 对策 |
|---|---|
| browser-use 0.12.x 升级 break | 锁版本 + 测试覆盖 callback 签名 |
| Windows asyncio | 默认 ProactorEventLoop 即可,**不要**强制 Selector(那会让 browser-use 启不了 Chromium) |
| Chromium 路径检测失败 | README 写 `BROWSER_USE_BROWSER_PATH` 用法 |
| MinerU 模型下载 500MB-2GB 慢 | trafilatura 降级 + 国内 ModelScope 镜像 |
| 隐私(浏览内容被存) | 域名黑名单(银行/邮箱/医疗)+ 本地加密(可选) |
| 记忆污染(LLM 幻觉混入) | 只存原始 Trace,LLM 摘要单独标 source=llm |

---

## 7. 文件结构

```
webmind/
├── PLAN.md                       # 本文件
├── SOURCES_AUDIT.md              # 源码审计结论
├── README.md                     # 对外 README
├── LICENSE                       # Apache 2.0
├── THIRD_PARTY_LICENSES.md       # 依赖归属
├── pyproject.toml                # 包配置
├── recallo/
│   ├── __init__.py
│   ├── cli.py                    # `recallo ...` 入口
│   ├── core.py                   # Mind Core
│   ├── cortex.py                 # browser-use 包装
│   ├── ingestor.py               # MinerU/trafilatura 三层
│   ├── memory.py                 # SQLite + 召回
│   ├── safety.py                 # 域名黑名单
│   └── schema.sql
└── tests/
```
