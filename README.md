# 03-changeflow（变流）

Changeflow — CDC / 变更流落库：事件入账 → 序/缺口裁决 → 幂等应用到 sink → 游标提交与对账。

**不是** Feed 多源归并（Feedstitch），**不是** 作业依赖编排（Batchgate）。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5300 |
| API | http://localhost:10300 |

本地开发（可选）：

```bash
# backend
cd backend && pip install -r requirements.txt
set DATA_DIR=..\data
uvicorn app.main:app --reload --port 10300

# frontend
cd frontend && npm install && npm run dev
```

## 主链

配置变更流与夹具 → 触发 Apply → 按序应用 / 缺口隔离 → Sink + 游标 + 运行报告对账

## 种子说明

- **Orders CDC（clean）**：JSONL，seq 1→5 连续 upsert/delete，首跑应全部应用、游标推进到 5。
- **Inventory CDC（clean）**：JSONL，seq 1→3 连续 upsert，独立实体键，用于第二路流演示。
- **Orders CDC（含毒丸）**：JSONL，seq 1→9，其中 seq 3 / 5 / 7 是结构损坏的毒丸，毒丸之后仍有合法 seq 8、9，用于验证两种毒丸策略。

打开「应用台」选流跑一次，再看账本 / 隔离区 / Sink / 游标页计数是否与本次报告一致。

## 毒丸识别与分流（poison_event_quarantine）

夹具里混进结构坏掉的毒丸时，主链自动识别并分流，**不做人工三态死信裁决**，也不复用缺口的等待/跳过/停逻辑。

识别规则（命中即判毒丸，可同时命中多条，原因写入隔离区 `reason` 与账本 disposition）：

| 规则 code | 触发条件 |
| --- | --- |
| `poison_missing_entity_key` | `entity_key` 缺失、空白或非字符串——无法定位 sink 行 |
| `poison_illegal_op` | `op` 缺失或不在 `upsert` / `delete` 内（如 `merge`） |
| `poison_missing_required_field` | `upsert` 事件 `payload` 为空对象或非对象（delete 的空 payload 合法） |

两种互斥策略，在「设置」页切换，存入 `settings.poison_policy`，刷新/重启后仍生效：

- **毒丸处停住 `stop_on_poison`（默认）**：毒丸进隔离区，其后事件本 run 不应用，`apply_cursor` 停在毒丸前一个合法 seq，不越过毒丸位点。
- **隔离毒丸后继续 `quarantine_and_continue`**：毒丸进隔离区且绝不记 applied、绝不进 Sink；游标作为消费位点越过毒丸，后续合法 seq 正常应用。

毒丸与缺口全程分得开：隔离区按 `reason` 的 `poison_` 前缀派生 `kind=poison|gap`（支持 `?kind=` 过滤）；账本 disposition 为 `quarantine_poison` / `quarantine_poison_stop` / `quarantine_gap`；Apply 报告的 `counts.quarantined_poison` 与 `quarantined_gap` 分别计数。整行 JSON 无法解析或 seq 缺失/非整数属于文件级损坏，解析器直接报错终止 run，不进毒丸分流。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现，见题单）

当前仓库已实现「连续序幂等应用」主链与「毒丸识别与自动分流」（见上节）。其余缺口等待/跳过、乱序缓冲、事务整批、双 sink 部分失败等仍在 `backend/app/modules/*` 留空包，按题单逐题换主链路实现。
