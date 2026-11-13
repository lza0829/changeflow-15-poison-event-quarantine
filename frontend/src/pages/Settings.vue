<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, putJSON } from '../api'

const policy = ref('stop_on_poison')
const saved = ref('')
const err = ref('')
const busy = ref(false)

const POLICIES = [
  { value: 'stop_on_poison', label: '毒丸处停住', desc: '毒丸进隔离区即停；其后事件不应用，游标不越过毒丸位点。' },
  { value: 'quarantine_and_continue', label: '隔离毒丸后继续', desc: '毒丸进隔离区但绝不记 applied；游标越过毒丸，后续合法 seq 继续应用。' },
]

async function load() {
  const rows = await getJSON('/api/settings')
  const found = rows.find((r) => r.key === 'poison_policy')
  policy.value = found ? found.value : 'stop_on_poison'
  saved.value = policy.value
}

async function save() {
  busy.value = true
  err.value = ''
  try {
    const r = await putJSON('/api/settings/poison_policy', { value: policy.value })
    saved.value = r.value
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
<template>
  <div class="page">
    <h1>设置</h1>
    <p class="muted">毒丸分流策略保存在后端 settings，刷新页面或重启后仍生效；两种策略互斥。</p>
    <div class="panel">
      <h3>毒丸策略 poison_policy</h3>
      <div v-for="p in POLICIES" :key="p.value" class="policy-option" :class="{ active: policy === p.value }">
        <label>
          <input type="radio" name="poison_policy" :value="p.value" v-model="policy" />
          <strong>{{ p.label }}</strong>
          <code>{{ p.value }}</code>
        </label>
        <p class="muted">{{ p.desc }}</p>
      </div>
      <div class="row-actions">
        <button :disabled="busy || policy === saved" @click="save">
          {{ busy ? '保存中…' : '保存策略' }}
        </button>
        <span v-if="policy === saved" class="tag ok">当前已生效：{{ saved }}</span>
      </div>
      <p v-if="err" class="tag danger">{{ err }}</p>
    </div>
    <div class="panel">
      <h3>毒丸识别规则（自动，无需人工裁决）</h3>
      <table>
        <thead><tr><th>原因 code</th><th>触发条件</th></tr></thead>
        <tbody>
          <tr><td><code>poison_missing_entity_key</code></td><td>entity_key 缺失、空白或非字符串（无法定位 sink 行）</td></tr>
          <tr><td><code>poison_illegal_op</code></td><td>op 缺失或不在 upsert / delete 内</td></tr>
          <tr><td><code>poison_missing_required_field</code></td><td>upsert 事件 payload 为空对象或非对象（delete 空 payload 合法）</td></tr>
        </tbody>
      </table>
      <p class="muted">命中规则的事件进隔离区（reason 带 poison_ 前缀），任何策略下都不写 Sink、不记 applied。</p>
    </div>
  </div>
</template>
<style scoped>
.policy-option {
  border: 1px solid var(--border, #444);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.policy-option.active {
  border-color: var(--ok, #7fd99a);
}
.policy-option label {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
