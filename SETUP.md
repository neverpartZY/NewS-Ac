# 运行配置与 API Key 说明

本文档是「跑起来需要什么」的唯一权威清单。所有真实 key / 私密配置**不入库**（见 `.gitignore`），
用 `.example` 占位 + 本地复制的方式启用。

---

## 一、API Key（写在 `.env`）

复制 `.env.example` → `.env`，按需填写。**✅=必需，⭕=可选（缺了该功能降级跳过），❌=不用**。

| 变量 | 用途 | 必需 | 获取方式 |
|---|---|:---:|---|
| `SERPER_API_KEY` | 新闻搜索（中英文主力） | ✅ | https://serper.dev（免费 2500 次/月） |
| `DEEPSEEK_API_KEY` | LLM：相关性判断 / 加工 / 撰写 / 去重仲裁 | ✅ | https://platform.deepseek.com |
| `SILICONFLOW_API_KEY` | embedding 语义去重（bge-m3） | ✅ | https://siliconflow.cn |
| `TAVILY_API_KEY` | 海外第二引擎（news 模式） | ⭕ | https://tavily.com（免费 1000 credit/月） |
| `WEIXINZS_API_KEY` | 公众号采集（weixinzs.org） | ⭕ | 旧 `mp-article-subscription` skill 的 `api_key.txt`（`sk-live` 开头） |
| `RESEND_API_KEY` | 邮件推送 | ⭕ | https://resend.com |
| `FROM_EMAIL` | 邮件发件人 | ⭕ | 如 `日报 <daily@greenplastic.ai>` |
| `REDFOX_API_KEY` | 红狐（爆款榜，**本系统不采集**） | ❌ | — |
| `WECHAT_MP_APPID` | 公众号草稿箱（走白名单服务器中转，非直连） | ⭕ | 微信公众平台后台 |
| `WECHAT_MP_SECRET` | 同上 | ⭕ | 微信公众平台后台 |
| `WECHAT_MP_THUMB_MEDIA_ID` | 草稿封面图 media_id（需先经 material 上传） | ⭕ | 微信公众平台 |
| `IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY` | IMA 知识库（走 ima-mcp MCP，非裸 HTTP） | ⭕ | 腾讯 IMA 开放平台 |

**LLM / Embedding 可覆盖项**：`LLM_API_KEY`（优先于 `DEEPSEEK_API_KEY`）、`LLM_BASE_URL`（默认 `https://api.deepseek.com/v1`）、
`LLM_MODEL`（默认 `deepseek-chat`）、`EMBED_MODEL`（默认 `BAAI/bge-m3`）。

> **key 读取顺序**：脚本优先读环境变量，兜底读 Windows 注册表 `HKCU\Environment`（Linux 上自动降级为只读环境变量）。
> 公众号 key 另有兜底：读 `mp-article-subscription/api_key.txt`（`.openclaw/skills`、`.workbuddy/skills`、项目同级 4 个位置）。

---

## 二、配置文件（`config/`）

| 文件 | 说明 | 是否入库 |
|---|---|:---:|
| `collection_config.json` | 62 条关键词任务矩阵 + 硬噪声/降噪/信号/区域词表 | ✅ |
| `sources_config.json` | 32 个行业源站 | ✅ |
| `price_config.json` | 13 个价格品种（名称/查询词/合理区间） | ✅ |
| `perplexity_config.json` | 14 条海外英文查询 | ✅ |
| `report_config.json` | 板块映射 + 信号优先级 | ✅ |
| `webhook_groups.json` | 企业微信 webhook 地址（**含 key，不入库**） | ❌ 从 `.example` 复制 |
| `email_recipients.json` | 邮件收件人（**PII，不入库**） | ❌ 从 `.example` 复制 |

---

## 三、本地启动步骤

```powershell
# 1. 克隆
git clone https://github.com/neverpartZY/NewS-Ac.git
cd NewS-Ac

# 2. 装 Python 3.9+ 与依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Linux: .venv/bin/pip

# 3. 配置 key
copy .env.example .env                           # Linux: cp .env.example .env
#   编辑 .env 填入 SERPER / DEEPSEEK / SILICONFLOW 等 key

# 4.（可选）推送通道配置
copy config\webhook_groups.example.json config\webhook_groups.json
copy config\email_recipients.example.json config\email_recipients.json

# 5. 自检 + 跑
.venv\Scripts\python.exe main.py --dry-run        # 只采集打印，验证 key/网络/依赖
.venv\Scripts\python.exe main.py --no-push        # 完整跑一轮（不推送），看 reports/ 成品
.venv\Scripts\python.exe main.py --once           # 正式（含推送）
.venv\Scripts\python.exe -m pytest -q             # 跑单测
```

---

## 四、推送四路各自的前置

| 通道 | 实现 | 前置 |
|---|---|---|
| 邮件 | Resend HTTP | `RESEND_API_KEY` + `FROM_EMAIL` + `config/email_recipients.json` |
| 企业微信 | 群机器人 webhook | `config/webhook_groups.json` |
| IMA 知识库 | ima-mcp MCP 连接器（Claude Code 会话内） | ima-mcp 连接器 connected |
| 公众号草稿箱 | `gjb-wechat-draft` skill + 白名单服务器 `43.128.140.186`（SSH） | SSH 私钥 + 各公众号 IP 白名单 |

每路独立可插拔：缺 key/前置未就绪 → 打印告警跳过，不阻塞其它路。

---

## 五、定时运行（服务器）

见 `README.md` 的「迁移到服务器」章节：`run.sh` + cron，日报日期/时效已固定北京时间（`config.TZ_OFFSET=UTC+8`）。
