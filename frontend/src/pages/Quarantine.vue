<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
const filter = ref('all')
const err = ref('')

async function load() {
  err.value = ''
  try {
    const qs = filter.value === 'all' ? '' : `?kind=${filter.value}`
    rows.value = await getJSON(`/api/quarantine${qs}`)
  } catch (e) {
    err.value = String(e.message || e)
  }
}
onMounted(load)
</script>
<template>
  <div class="page">
    <h1>隔离区</h1>
    <p class="muted">
      两类隔离分开记账：<span class="tag danger">毒丸 poison</span>
      事件结构损坏（reason 带 <code>poison_</code> 前缀）；
      <span class="tag warn">缺口 gap</span> 是 seq 不连续、事件本身合法。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="row-actions panel">
      <label>类型
        <select v-model="filter" @change="load">
          <option value="all">全部</option>
          <option value="poison">仅毒丸</option>
          <option value="gap">仅缺口</option>
        </select>
      </label>
      <button class="ghost" @click="load">刷新</button>
      <span class="muted">当前 {{ rows.length }} 条</span>
    </div>
    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>类型</th><th>流</th><th>run</th><th>seq</th><th>entity</th><th>reason</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td>
              <span class="tag" :class="r.kind === 'poison' ? 'danger' : 'warn'">
                {{ r.kind === 'poison' ? '毒丸' : '缺口' }}
              </span>
            </td>
            <td>{{ r.stream_id }}</td>
            <td>{{ r.run_id }}</td>
            <td>{{ r.seq }}</td>
            <td>{{ r.entity_key || '（空）' }}</td>
            <td><code>{{ r.reason }}</code></td>
            <td>{{ r.created_at }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="8" class="muted">暂无隔离记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
