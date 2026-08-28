# 塑料回收新闻采集 + AI 加工系统

多渠道采集「塑料回收」新闻 → AI 筛选/语义去重/加工 → 生成 3 份高质量日报 → 四路推送。

基于旧 `plastic-daily-report-skill` 重构：保留其打磨过的领域数据（词表/任务矩阵/源站/价格），
砍掉架构包袱（AFP 三层/覆盖率门禁/模板堆砌），把语义去重和报告质量两个薄弱环节升级。

## 四条硬要求

| 要求 | 实现 |
|---|---|
| 中文结果 | 中英双轨采集；英文标题 LLM 译成中文；日报正文强制中文 |
| 3 天以内 | `published_at >= now - 3天` 硬过滤；价格更严 = 2 天 |
| 塑料回收相关 | 硬噪声词（期货/涨停/乙二醇…）命中即丢 → LLM 主题相关性打分 |
| 语义去重 | URL 精确 + embedding 余弦（≥0.88 判重 / 0.72–0.88 LLM 仲裁 / <0.72 新内容）对「已收录列表」 |

## 环境要求

- Python **3.9+**（本机原只有 3.5，需装新版；已用 `uv` 建好 `.venv` 的 3.12 可直接用）
- 依赖：`requests`、`numpy`（见 `requirements.txt`）

## 安装

```powershell
# 方式一：已有 uv
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt pytest

# 方式二：常规
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest
```

复制 `.env.example` 为 `.env` 并填入密钥（见下「密钥」）。

## 运行

```powershell
.\.venv\Scripts\python.exe main.py --once        # 完整一轮：采集→过滤→去重→加工→生成→落库→推送
.\.venv\Scripts\python.exe main.py --dry-run     # 只采集打印，不落库不推送
.\.venv\Scripts\python.exe main.py --no-push     # 落库+生成日报，不推送
.\.venv\Scripts\python.exe main.py --full        # 跑全量 auto 任务（默认只跑 D1 高频）
.\.venv\Scripts\python.exe main.py --weekly      # 周报：从已收录列表取过去 7 天精选（不重新采集）
.\.venv\Scripts\python.exe main.py --monthly     # 月报：从已收录列表取过去 30 天汇总（不重新采集）
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 架构

```
main.py --once
  ├─ 采集   engines/*       Serper + Tavily + 公众号(weixinzs) + 价格 + 源站
  ├─ 过滤   filter.py       硬噪声词 → 时效(3天)/stale → LLM 相关性
  ├─ 去重   dedup.py        URL 精确 + embedding(bge-m3) 语义 + LLM 临界仲裁
  ├─ 加工   refine.py       逐条：中文标题/摘要/分类/细分/重要性/标签
  ├─ 生成   report.py       LLM 主编撰写 综合 / 化学循环 / 再生PET 三份日报
  ├─ 落库   storage.py      SQLite「已收录列表」+ embedding
  └─ 推送   push/*          邮件 / 企业微信 / IMA 知识库 / 公众号草稿箱
```

## 目录

```
config/      领域数据（从旧 skill 提取）：62 任务矩阵、噪声词、32 源站、13 价格品种…
references/  领域参考（维度总纲、关键词矩阵、源站/公众号清单、规则、JZL API）
pipeline/    流水线代码（engines/ filter dedup refine report storage push）
data/        SQLite 库 news.db（运行时生成）
reports/     生成的 3 份日报 markdown
```

## 密钥（`.env`）

| 类别 | 变量 | 说明 |
|---|---|---|
| 搜索 | `SERPER_API_KEY` / `TAVILY_API_KEY` | 已有 |
| LLM | `LLM_API_KEY`（或 `DEEPSEEK_API_KEY`）、`LLM_BASE_URL`、`LLM_MODEL` | 默认 DeepSeek `deepseek-chat` |
| Embedding | `SILICONFLOW_API_KEY`、`EMBED_MODEL` | 默认 `BAAI/bge-m3` |
| 公众号采集 | `WEIXINZS_API_KEY` | weixinzs.org（旧 mp-article-subscription 的 key） |
| 邮件 | `RESEND_API_KEY`、`FROM_EMAIL` | 收件人读 `config/email_recipients.json` |
| 企业微信 | `config/webhook_groups.json` 内 webhook | 已含 2 个群 |
| IMA 知识库 | `IMA_OPENAPI_CLIENTID/APIKEY` | 见下方「待补输入」 |
| 公众号草稿箱 | `WECHAT_MP_APPID/SECRET/THUMB_MEDIA_ID` | 只建草稿不发表 |

## 迁移到服务器（每日运行）

代码已做可移植处理：路径全用 `Path(__file__)` 相对定位、`winreg` 读 key 在 Linux 自动降级、
日报日期/时效统一按**北京时间**（`config.py` 的 `TZ_OFFSET=UTC+8`，服务器时区不影响日期正确性）、
依赖只有 `requests` + `numpy` 两个跨平台包。

### 1. 复制项目到服务器

```bash
# 排除 .venv（本机 uv 建的，服务器要重建）、data/reports/logs（运行时生成）
scp -r NewS-Ac 用户@服务器:/opt/   # 或 rsync --exclude=.venv --exclude=data --exclude=reports --exclude=logs
```

`.env` 含真实 key（已 gitignore），需一并带过去（或到服务器上新建）。

### 2. 装依赖

```bash
cd /opt/NewS-Ac
python3 -m venv .venv                       # 需 Python 3.9+
.venv/bin/pip install -r requirements.txt
```

### 3. 定时（cron）

`run.sh` 已封装好（自动用 `.venv/bin/python` + 追加日志到 `logs/`）。

```bash
chmod +x run.sh
crontab -e
```

时间按**北京时间 07:30** 换算（代码内部日期已固定北京时间，只影响几点触发）：

```cron
# 若服务器本身是中国时区：
30 7 * * * /opt/NewS-Ac/run.sh

# 若服务器是 UTC（07:30 北京 = 前一日 23:30 UTC）：
30 23 * * * /opt/NewS-Ac/run.sh

# 若 cron 支持 CRON_TZ（cronie/vixie-cron），可显式指定：
CRON_TZ=Asia/Shanghai
30 7 * * * /opt/NewS-Ac/run.sh --once                          # 每天 07:30 日报
30 8 * * 6 /opt/NewS-Ac/run.sh --weekly                        # 每周六 08:30 周报
30 9 28-31 * * [ "$(date -d tomorrow +%d)" = "01" ] && /opt/NewS-Ac/run.sh --monthly   # 月末 09:30 月报
```

### 4. （可选）systemd timer

比 cron 更规范、带重试/日志管理，需要时再配。

### 迁移后自检

```bash
cd /opt/NewS-Ac
.venv/bin/python main.py --dry-run     # 只采集打印，确认 key/网络/依赖 OK
.venv/bin/python main.py --no-push     # 完整跑一轮（不推送），看 reports/ 成品
.venv/bin/python main.py --once        # 正式（含推送）
```

## 待你后续补的输入

1. **IMA 知识库**：走 **ima-mcp MCP 连接器**（Claude Code 会话内执行），不在本 Python 程序内。
   `push/ima.py` 仅做交接提示，日报生成后在会话里手动调 ima-mcp 上传即可。
2. **公众号草稿箱**：走 `gjb-wechat-draft` skill（本地 `wechat-mp` 排版 → scp/SSH 到白名单服务器 `43.128.140.186` 建草稿）。
   本程序只生成 `publish_meta.json` 交接文件并输出 scp/ssh 指令，AppSecret 只在服务器上。
3. **公众号采集 key**：`WEIXINZS_API_KEY`（或指定其它商业 API 供应商）。
4. **Embedding**：`SILICONFLOW_API_KEY`（语义去重必需，缺省时退化为仅 URL 去重）。
5. **主 LLM**：默认 DeepSeek `deepseek-chat`，如需其它模型改 `.env` 的 `LLM_BASE_URL`/`LLM_MODEL`。

## 阈值调优

`config.py` 顶部集中：`FRESH_DAYS`(3)、`PRICE_DAYS`(2)、`RELEVANCE_THRESHOLD`(0.7)、
`DEDUP_HIGH`(0.88)、`DEDUP_LOW`(0.72)。用真实数据核对去重准确率后回调。
