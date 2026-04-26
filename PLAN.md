# Recallo — GitHub 开源精简版

> 只为开源到 GitHub 而设计的精简方案。砍掉所有营销/品牌/推广,聚焦代码本身。

日期:2026-04-26

---

## 0. 一句话定位

**Recallo 是一个本地优先、专注论文阅读的浏览器 Agent**:浏览/解析论文,把每一篇看过的内容存进本地 SQLite,跨会话精确召回("上周看的那篇 RAG 综述里讲过什么?")。

---

## 1. 杂交策略

| 源项目 | 协议 | 借用方式 |
|---|---|---|
| browser-use | MIT | `pip install browser-use` |
| MinerU | Apache 2.0 + 商业阈值 | `pip install mineru`(失败时 trafilatura 降级) |
| browser-harness | MIT | 思想借鉴(原仅 ~600 行),V2 启用 |
| sqlite-vss | MIT | `pip install sqlite-vss` |
| trafilatura | Apache 2.0 | `pip install trafilatura` |
| stash / future-agi | — | V1 不用 |

**伪装(对外不暴露源项目)**:
- 核心概念命名:Episode / Memory Lane / Web Trace
- API:`Recallo()` 顶层对象 + `.explore() / .recall() / .replay()`
- CLI:`recallo ...`,不暴露 `browser-use` 子命令
- 日志前缀 `[recallo]`
- README 末尾 `## Standing on the Shoulders of Giants` 章节诚实归属

**License**:Apache 2.0(自家),THIRD_PARTY_LICENSES.md 完整收录所有借用项目。

---

## 2. V1 范围

### 必做
1. **Cross-Session Recall** — 第二次问能命中第一次的记忆
2. **Local-First Vault** — SQLite 单文件,域名黑名单,无任何上传
3. **Memory Replay 轻量** — CLI 列出历史 Episode,看时间线

### 不做
- TimeTravel Diff、Self-Healing、PaperGraph、团队协作
- Web UI(CLI 够了,要想做 V2 加 FastAPI)
- Docker / Postgres
- Electron / 浏览器扩展

---

## 3. 技术架构

```
recallo (CLI)
    │
    ▼
Mind Core (自写)
    │
    ├─→ Browser Cortex   (browser-use 包装)
    ├─→ Doc Ingestor     (MinerU + trafilatura 降级)
    └─→ Memory Lane      (SQLite + sqlite-vss)
                          ~/.recallo/memory.db
```

**主语言**:Python 3.11+
**存储**:SQLite + sqlite-vss(单文件)
**LLM**:BYOK,默认支持 OpenAI / Anthropic / Ollama
**安装**:`pip install recallo`

---

## 4. SQLite Schema(草稿)

```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,           -- uuid
    intent TEXT NOT NULL,          -- 用户原始 query
    summary TEXT,                  -- LLM 生成摘要
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    status TEXT                    -- ok / failed / partial
);

CREATE TABLE traces (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id),
    seq INTEGER,                   -- 在 episode 内的顺序
    action TEXT,                   -- navigate / click / extract
    url TEXT,
    selector TEXT,
    text_excerpt TEXT,             -- 抓到的内容摘录(限长)
    ts INTEGER
);

CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id),
    kind TEXT,                     -- paper / author / claim / ...
    content TEXT,                  -- 结构化事实文本
    source_url TEXT
);

CREATE VIRTUAL TABLE fact_vss USING vss0(
    embedding(1536)
);
-- 关联 facts.id ↔ fact_vss.rowid
```

---

## 5. 仓库结构

```
recallo/
├── README.md                      # 对外门面
├── LICENSE                        # Apache 2.0
├── THIRD_PARTY_LICENSES.md
├── pyproject.toml
├── recallo/
│   ├── __init__.py
│   ├── cli.py                     # `recallo ...` 命令
│   ├── core.py                    # Mind Core
│   ├── cortex.py                  # browser-use 包装
│   ├── ingestor.py                # MinerU + trafilatura
│   ├── memory.py                  # SQLite + vss
│   ├── schema.sql
│   └── safety.py                  # 域名黑名单 / 加密
├── tests/
│   ├── test_memory.py
│   ├── test_recall.py
│   └── fixtures/
└── examples/
    └── arxiv_paper_recall.py
```

---

## 6. 实施步骤(按"能 push 到 GitHub"切分)

### M1:能装能跑(2-3 天)
- [ ] `pyproject.toml` + `pip install -e .` 跑通
- [ ] CLI 骨架:`recallo --version`、`recallo explore "..."`
- [ ] SQLite schema 初始化
- [ ] browser-use 调通,抓一个 arxiv 摘要

### M2:能记能召回(3-5 天)
- [ ] Episode/Trace 写入
- [ ] embedding(OpenAI 或 sentence-transformers 本地)
- [ ] sqlite-vss 召回 top-k
- [ ] `recallo recall "..."` 命中历史

### M3:能给陌生人用(2 天)
- [ ] README + 一张 demo GIF
- [ ] LICENSE + THIRD_PARTY_LICENSES
- [ ] `examples/arxiv_paper_recall.py` 跑通端到端
- [ ] 加 `.env.example` + Ollama fallback
- [ ] push GitHub,设 public

### M4(可选):打磨
- [ ] 域名黑名单
- [ ] Memory Replay CLI 子命令(列时间线)
- [ ] MinerU 集成
- [ ] 测试覆盖到 60%+

总计:**1-2 周一个人**(不是 6 周——砍掉营销和 V2 特性后就这点工作量)。

---

## 7. README 顶部草稿(直接可用)

```markdown
# Recallo

> Give your browser agent a memory it can prove.
> Local-first browser agent with long-term memory, focused on paper reading.

[demo GIF 占位]

## What it does

Read papers once, recall them weeks later. Recallo browses arxiv (or any URL),
parses content, and stores everything in a local SQLite database. Next time you
ask "what did that Self-RAG paper say about retrieval?", it finds the answer
from your past sessions — no cloud, no re-prompting.

## Quick start

\`\`\`bash
pip install recallo
recallo explore "Summarize arxiv:2310.11511"
# ...weeks later...
recallo recall "what did that Self-RAG paper say about retrieval?"
\`\`\`

## Why local-first?

ChatGPT Atlas keeps your browsing memory on OpenAI's servers. Recallo keeps it
in `~/.recallo/memory.db` on your machine. You can inspect it, back it up,
delete it, share it — it's just a SQLite file.

## Stack
- [browser-use](https://github.com/browser-use/browser-use) for browser control
- [MinerU](https://github.com/opendatalab/MinerU) for document parsing
- SQLite + [sqlite-vss](https://github.com/asg017/sqlite-vss) for memory
- BYOK: OpenAI / Anthropic / Ollama

## Standing on the shoulders of giants

Recallo is built on:
- browser-use (MIT)
- MinerU (Apache 2.0)
- sqlite-vss (MIT)
- trafilatura (Apache 2.0)

See [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for full attribution.

## License

Apache 2.0
```

---

## 8. 立即要决定的 3 件事

1. **项目名定 Recallo 还是另选?**(只看 GitHub 是否撞名,其他不管)
2. **是否现在就开始写 M1 代码?**(我可以开 agent 直接写)
3. **是否要打 git init + 初始 commit?**(D:\2026project\webmind\ 现在还没 git)
