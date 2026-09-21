<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const zones = ref([])
const error = ref('')
const editingId = ref(null)
const filterStatus = ref('')
const auditCount = ref(0)
const originalDuration = ref(null)

const revisionsPanel = reactive({
  open: false,
  loading: false,
  cycleId: null,
  detail: null,
  items: [],
  error: '',
})

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  zoneId: '',
  startAt: localInputValue(),
  durationMin: 30,
  revisionReason: '',
  waterLiters: 100,
  status: 'scheduled',
})

const statusLabel = {
  scheduled: '已排程',
  running: '进行中',
  done: '已完成',
  skipped: '已跳过',
}

const durationChanged = computed(
  () => editingId.value !== null && Number(form.durationMin) !== originalDuration.value
)

function rawError(e, fallback = '请求失败') {
  // 失败时原样展示接口返回内容
  if (e.response?.data !== undefined && e.response.data !== null) {
    return JSON.stringify(e.response.data, null, 2)
  }
  return e.message || fallback
}

function resetForm() {
  editingId.value = null
  originalDuration.value = null
  form.zoneId = zones.value[0]?.id || ''
  form.startAt = localInputValue()
  form.durationMin = 30
  form.revisionReason = ''
  form.waterLiters = 100
  form.status = 'scheduled'
}

async function loadZones() {
  const { data } = await api.get('/zones/')
  zones.value = data.results || data
  if (!form.zoneId && zones.value.length) form.zoneId = zones.value[0].id
}

async function loadAuditCount() {
  try {
    const { data } = await api.get('/irrigation-cycles/duration-audit/')
    auditCount.value = data.cyclesWithRevisions
  } catch (e) {
    error.value = rawError(e, '稽核数加载失败')
  }
}

async function load() {
  error.value = ''
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/irrigation-cycles/', { params })
    list.value = data.results || data
    await loadAuditCount()
  } catch (e) {
    error.value = rawError(e, '加载轮灌计划失败')
  }
}

function edit(row) {
  editingId.value = row.id
  originalDuration.value = row.durationMin
  form.zoneId = row.zoneId
  form.startAt = localInputValue(new Date(row.startAt))
  form.durationMin = row.durationMin
  form.revisionReason = ''
  form.waterLiters = Number(row.waterLiters)
  form.status = row.status
}

async function save() {
  error.value = ''
  const payload = {
    zoneId: Number(form.zoneId),
    startAt: new Date(form.startAt).toISOString(),
    durationMin: form.durationMin,
    waterLiters: form.waterLiters,
    status: form.status,
  }
  // 时长与库中不同时必须携带修订原因，后端会同事务写留痕
  if (editingId.value && durationChanged.value) {
    payload.revisionReason = form.revisionReason
  }
  try {
    if (editingId.value) {
      await api.put(`/irrigation-cycles/${editingId.value}/`, payload)
    } else {
      await api.post('/irrigation-cycles/', payload)
    }
    resetForm()
    await load()
    if (revisionsPanel.open) await openRevisions(revisionsPanel.cycleId)
  } catch (e) {
    error.value = rawError(e, '保存失败')
  }
}

async function remove(id) {
  if (!confirm('确认删除该轮灌记录？')) return
  try {
    await api.delete(`/irrigation-cycles/${id}/`)
    await load()
  } catch (e) {
    error.value = rawError(e, '删除失败')
  }
}

async function openRevisions(cycleId) {
  revisionsPanel.open = true
  revisionsPanel.loading = true
  revisionsPanel.cycleId = cycleId
  revisionsPanel.detail = null
  revisionsPanel.items = []
  revisionsPanel.error = ''
  try {
    const [detailRes, revisionsRes] = await Promise.all([
      api.get(`/irrigation-cycles/${cycleId}/`),
      api.get(`/irrigation-cycles/${cycleId}/revisions/`),
    ])
    revisionsPanel.detail = detailRes.data
    revisionsPanel.items = revisionsRes.data.results || revisionsRes.data
  } catch (e) {
    revisionsPanel.error = rawError(e, '留痕加载失败')
  } finally {
    revisionsPanel.loading = false
  }
}

function closeRevisions() {
  revisionsPanel.open = false
  revisionsPanel.cycleId = null
  revisionsPanel.detail = null
  revisionsPanel.items = []
  revisionsPanel.error = ''
}

onMounted(async () => {
  await loadZones()
  await load()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>轮灌计划</h1>
        <p>按分区安排起灌时间、时长与水量；时长修改强制留痕</p>
      </div>
      <div class="actions">
        <span class="badge done">有留痕轮灌条数：{{ auditCount }}</span>
        <select v-model="filterStatus" @change="load">
          <option value="">全部状态</option>
          <option value="scheduled">已排程</option>
          <option value="running">进行中</option>
          <option value="done">已完成</option>
          <option value="skipped">已跳过</option>
        </select>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">{{ editingId ? '编辑轮灌 #' + editingId : '新建轮灌' }}</h3>
      <div class="form-grid">
        <label>
          分区
          <select v-model="form.zoneId">
            <option v-for="z in zones" :key="z.id" :value="z.id">
              {{ z.greenhouseName }} / {{ z.zoneCode }}
            </option>
          </select>
        </label>
        <label>开始时间<input v-model="form.startAt" type="datetime-local" /></label>
        <label>
          时长(分钟)
          <input v-model.number="form.durationMin" type="number" min="1" />
          <small v-if="editingId" style="color:var(--earth-deep)">
            库中时长：{{ originalDuration }} 分；最新时长以最新留痕为准
          </small>
        </label>
        <label>水量(升)<input v-model.number="form.waterLiters" type="number" step="0.01" min="0" /></label>
        <label>
          状态
          <select v-model="form.status">
            <option value="scheduled">已排程</option>
            <option value="running">进行中</option>
            <option value="done">已完成</option>
            <option value="skipped">已跳过</option>
          </select>
        </label>
        <label v-if="durationChanged" class="full">
          修订原因（必填，去空白后至少 8 字）
          <input
            v-model="form.revisionReason"
            type="text"
            maxlength="500"
            placeholder="例如：天气转晴作物蒸腾增强，延长灌溉时长"
          />
          <small style="color:var(--danger)">
            新分钟须为正且与原分钟不同；时长与留痕同事务写入，缺留痕则 400 且时长保持原值。
          </small>
        </label>
      </div>
      <pre v-if="error" class="error raw">{{ error }}</pre>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="save">保存</button>
        <button v-if="editingId" class="btn ghost" @click="resetForm">取消编辑</button>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>开始</th>
            <th>温室/分区</th>
            <th>当前时长</th>
            <th>最新时长</th>
            <th>修订条数</th>
            <th>水量</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in list" :key="row.id">
            <td>{{ new Date(row.startAt).toLocaleString() }}</td>
            <td>{{ row.greenhouseName }} / {{ row.zoneCode }}</td>
            <td>{{ row.durationMin }} 分</td>
            <td>{{ row.latestDurationMin }} 分</td>
            <td>
              <button class="btn ghost" @click="openRevisions(row.id)">
                {{ row.revisionCount }} 条
              </button>
            </td>
            <td>{{ row.waterLiters }} L</td>
            <td>
              <span class="badge" :class="row.status">{{ statusLabel[row.status] || row.status }}</span>
            </td>
            <td class="actions">
              <button class="btn ghost" @click="edit(row)">编辑</button>
              <button class="btn danger" @click="remove(row.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="revisionsPanel.open" class="panel">
      <div class="actions" style="justify-content:space-between">
        <h3 style="margin:0">轮灌 #{{ revisionsPanel.cycleId }} 时长修订留痕</h3>
        <button class="btn ghost" @click="closeRevisions">关闭</button>
      </div>
      <p v-if="revisionsPanel.loading">留痕加载中…</p>
      <pre v-else-if="revisionsPanel.error" class="error raw">{{ revisionsPanel.error }}</pre>
      <template v-else-if="revisionsPanel.detail">
        <p style="margin:8px 0">
          轮灌编号：{{ revisionsPanel.detail.id }}
          ｜当前时长：{{ revisionsPanel.detail.durationMin }} 分
          ｜<strong>最新时长：{{ revisionsPanel.detail.latestDurationMin }} 分</strong>
          ｜修订条数：{{ revisionsPanel.detail.revisionCount }}
        </p>
        <table v-if="revisionsPanel.items.length">
          <thead>
            <tr>
              <th>原分钟</th>
              <th>新分钟</th>
              <th>原因</th>
              <th>修订时刻</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in revisionsPanel.items" :key="r.id">
              <td>{{ r.oldMin }}</td>
              <td>{{ r.newMin }}</td>
              <td>{{ r.reason }}</td>
              <td>{{ new Date(r.revisedAt).toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else style="color:var(--earth-deep)">暂无留痕，最新时长等于当前时长。</p>
      </template>
    </div>
  </div>
</template>
