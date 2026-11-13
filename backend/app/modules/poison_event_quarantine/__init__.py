"""poison_event_quarantine —— 毒丸识别与自动分流。

主链默认所有事件可解析、可应用；本切口补上“结构坏掉的毒丸”这一类输入的
自动识别与分流，避免两种假账：

- 把毒丸当普通缺口一停 → 后面的合法 seq 全堵死；
- 直接当成功跳过 → Sink 出现未经验证的假账。

毒丸规则（可复现，详见 app/engines/poison_rules.py）：
1. poison_missing_entity_key      缺实体键（entity_key 缺失/空白/非字符串）
2. poison_illegal_op              非法 op（不在 upsert/delete 内）
3. poison_missing_required_field  关键字段缺失（upsert 的 payload 为空/非对象）

两种互斥、可保存的策略（settings.poison_policy）：
- stop_on_poison：毒丸处停住。其后事件不应用，游标不越过毒丸位点；
- quarantine_and_continue：隔离毒丸后继续。游标可越过毒丸位点，
  但毒丸自身绝不记 applied、绝不进 Sink。

毒丸与缺口的区分（四处一致）：
- 隔离区 quarantine.reason 以 poison_ 前缀区分，另有派生列 kind；
- 账本 change_ledger.disposition 用 quarantine_poison* / quarantine_gap；
- Apply 报告 counts.quarantined_poison / quarantined_gap 分开计数；
- 毒丸在任何策略下都不写 sink_records、不写 applied_seqs。

注意：本切口是自动分流，不做人工三态死信裁决，也不复用缺口的
等待/跳过/停策略（gap_policy 与 poison_policy 是两个独立开关）。
整行 JSON 无法解析或 seq 缺失属于文件级损坏，解析器直接报错终止 run。
"""
