<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
const streams = ref([])
const streamId = ref(1)
const last = ref(null)
const runs = ref([])
const err = ref('')
const busy = ref(false)
async function refreshRuns() {
  runs.value = await getJSON('/api/runs')
}
async function runApply() {
  busy.value = true
  err.value = ''
  try {
    last.value = await postJSON('/api/apply', { stream_id: streamId.value })
    streams.value = await getJSON('/api/streams')
    await refreshRuns()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}
function statusClass(s) {
  if (s === 'succeeded') return 'ok'
  if (s === 'stopped_poison') return 'danger'
  return 'warn'
}
function statusLabel(s) {
  return { succeeded: '完成', partial: '缺口停', stopped_poison: '毒丸停', failed: '失败' }[s] || s
}
onMounted(async () => {
  streams.value = await getJSON('/api/streams')
  if (streams.value.length) streamId.value = streams.value[0].id
  await refreshRuns()
})
</script>
<template>
  <div class="page">
    <h1>应用台</h1>
    <p class="muted">按游标连续序应用；毒丸自动识别并按<a href="#/settings">设置页</a>策略分流，缺口默认停并进隔离区。</p>
    <div class="row-actions panel">
      <label>流
        <select v-model.number="streamId">
          <option v-for="s in streams" :key="s.id" :value="s.id">{{ s.id }} · {{ s.name }}（游标 {{ s.apply_cursor }}）</option>
        </select>
      </label>
      <button :disabled="busy" @click="runApply">{{ busy ? '应用中…' : '执行 Apply' }}</button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="last">
      <h3>最近一次</h3>
      <p>
        run #{{ last.id }} ·
        <span class="tag" :class="statusClass(last.status)">{{ statusLabel(last.status) }}</span>
        · loaded {{ last.loaded_count }} / applied {{ last.applied_count }} /
        quarantined {{ last.quarantined_count }} / skipped {{ last.skipped_count }}
        · cursor {{ last.cursor_before }} → {{ last.cursor_after }}
      </p>
      <div v-if="last.report && last.report.counts" class="compare-grid">
        <div class="mini-tile">
          <div class="hero-num">{{ last.report.poison_in_fixture }}</div>
          <div class="muted">夹具毒丸数</div>
        </div>
        <div class="mini-tile">
          <div class="hero-num">{{ last.report.counts.quarantined_poison }}</div>
          <div class="muted">毒丸隔离</div>
        </div>
        <div class="mini-tile">
          <div class="hero-num">{{ last.report.counts.quarantined_gap }}</div>
          <div class="muted">缺口隔离</div>
        </div>
        <div class="mini-tile">
          <div class="hero-num">{{ last.report.counts.applied }}</div>
          <div class="muted">applied</div>
        </div>
      </div>
      <p v-if="last.report && last.report.poison_policy" class="muted">
        毒丸策略：<code>{{ last.report.poison_policy_label }}（{{ last.report.poison_policy }}）</code>
        <template v-if="last.report.stopped_on_poison"> · 停在毒丸 seq，游标未越过</template>
      </p>
      <pre class="mono">{{ JSON.stringify(last.report, null, 2) }}</pre>
    </div>
    <div class="panel">
      <h3>历史 Runs</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>流</th><th>状态</th><th>loaded</th><th>applied</th><th>毒丸隔离</th><th>缺口隔离</th><th>skipped</th><th>cursor</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.stream_id }}</td>
            <td><span class="tag" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
            <td>{{ r.loaded_count }}</td>
            <td>{{ r.applied_count }}</td>
            <td>{{ r.report && r.report.counts ? r.report.counts.quarantined_poison : '—' }}</td>
            <td>{{ r.report && r.report.counts ? r.report.counts.quarantined_gap : '—' }}</td>
            <td>{{ r.skipped_count }}</td>
            <td>{{ r.cursor_before }}→{{ r.cursor_after }}</td>
            <td>{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.compare-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 10px 0;
}
.mini-tile {
  border: 1px solid var(--border, #444);
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}
.mini-tile .hero-num {
  font-size: 24px;
  font-weight: 700;
}
</style>
