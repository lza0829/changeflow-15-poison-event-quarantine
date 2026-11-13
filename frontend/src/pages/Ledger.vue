<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/ledger') })

function dispClass(d) {
  if (d === 'applied') return 'ok'
  if (d.startsWith('quarantine_poison')) return 'danger'
  if (d === 'quarantine_gap') return 'warn'
  return ''
}
</script>
<template>
  <div class="page">
    <h1>变更账本</h1>
    <p class="muted">
      每次 Apply 写入的事件处置记录（与报告同源）。毒丸处置
      <code>quarantine_poison*</code> 与缺口 <code>quarantine_gap</code> 分开标注；
      毒丸在任何策略下都不会出现 applied。
    </p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>流</th><th>run</th><th>seq</th><th>op</th><th>entity</th><th>disposition</th><th>event_ts</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.stream_id }}</td>
            <td>{{ r.run_id }}</td>
            <td>{{ r.seq }}</td>
            <td>{{ r.op }}</td>
            <td>{{ r.entity_key || '（空）' }}</td>
            <td><span class="tag" :class="dispClass(r.disposition)">{{ r.disposition }}</span></td>
            <td>{{ r.event_ts || '（空）' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
