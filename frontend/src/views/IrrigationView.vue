<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const zones = ref([])
const error = ref('')
const editingId = ref(null)
const filterStatus = ref('')

// 时长修订弹窗
const revise = reactive({
  open: false,
  cycleId: null,
  title: '',
  oldMin: null,
  newMin: null,
  reason: '',
  error: '',
  saving: false,
})

// 留痕记录弹窗
const revisions = reactive({
  open: false,
  cycleId: null,
  title: '',
  items: [],
  error: '',
  loading: false,
})

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  zoneId: '',
  startAt: localInputValue(),
  durationMin: 30,
  waterLiters: 100,
  status: 'scheduled',
})

// 编辑中轮灌的最新时长 / 修订条数（详情）
const editingRow = ref(null)

const statusLabel = {
  scheduled: '已排程',
  running: '进行中',
  done: '已完成',
  skipped: '已跳过',
}

function resetForm() {
  editingId.value = null
  editingRow.value = null
  form.zoneId = zones.value[0]?.id || ''
  form.startAt = localInputValue()
  form.durationMin = 30
  form.waterLiters = 100
  form.status = 'scheduled'
}

async function loadZones() {
  const { data } = await api.get('/zones/')
  zones.value = data.results || data
  if (!form.zoneId && zones.value.length) form.zoneId = zones.value[0].id
}

async function load() {
  error.value = ''
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/irrigation-cycles/', { params })
    list.value = data.results || data
  } catch {
    error.value = '加载轮灌计划失败'
  }
}

function edit(row) {
  editingId.value = row.id
  editingRow.value = row
  form.zoneId = row.zoneId
  form.startAt = localInputValue(new Date(row.startAt))
  form.durationMin = row.durationMin
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
  try {
    if (editingId.value) {
      await api.put(`/irrigation-cycles/${editingId.value}/`, payload)
    } else {
      await api.post('/irrigation-cycles/', payload)
    }
    resetForm()
    await load()
  } catch (e) {
    error.value = JSON.stringify(e.response?.data || '保存失败')
  }
}

async function remove(id) {
  if (!confirm('确认删除该轮灌记录？')) return
  await api.delete(`/irrigation-cycles/${id}/`)
  await load()
}

function rowTitle(row) {
  return `${row.greenhouseName} / ${row.zoneCode} · ${new Date(row.startAt).toLocaleString()}`
}

function openRevise(row) {
  revise.open = true
  revise.cycleId = row.id
  revise.title = rowTitle(row)
  revise.oldMin = row.durationMin
  revise.newMin = row.latestDurationMin ?? row.durationMin
  revise.reason = ''
  revise.error = ''
}

function closeRevise() {
  revise.open = false
  revise.cycleId = null
}

function rawApiError(e, fallback) {
  // 失败时展示接口返回原文
  const data = e.response?.data
  if (data === undefined || data === null) return e.message || fallback
  return typeof data === 'string' ? data : JSON.stringify(data)
}

async function submitRevise() {
  revise.error = ''
  revise.saving = true
  try {
    await api.post(`/irrigation-cycles/${revise.cycleId}/revise-duration/`, {
      newMin: Number(revise.newMin),
      reason: revise.reason,
    })
    closeRevise()
    await load()
  } catch (e) {
    revise.error = rawApiError(e, '修订失败')
  } finally {
    revise.saving = false
  }
}

async function openRevisions(row) {
  revisions.open = true
  revisions.cycleId = row.id
  revisions.title = rowTitle(row)
  revisions.items = []
  revisions.error = ''
  revisions.loading = true
  try {
    const { data } = await api.get(`/irrigation-cycles/${row.id}/revisions/`)
    revisions.items = data.results || data
  } catch (e) {
    revisions.error = rawApiError(e, '加载留痕失败')
  } finally {
    revisions.loading = false
  }
}

function closeRevisions() {
  revisions.open = false
  revisions.cycleId = null
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
        <p>按分区安排起灌时间、时长与水量；改时长必须填写原因并留下修订留痕</p>
      </div>
      <div class="actions">
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
      <h3 style="margin-top:0">{{ editingId ? '编辑轮灌' : '新建轮灌' }}</h3>
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
          <input
            v-model.number="form.durationMin"
            type="number"
            min="1"
            :disabled="!!editingId"
          />
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
      </div>
      <p v-if="editingRow" class="hint">
        当前时长 {{ editingRow.durationMin }} 分 · 最新时长 {{ editingRow.latestDurationMin ?? editingRow.durationMin }} 分
        · 修订留痕 {{ editingRow.revisionCount ?? 0 }} 条。编辑时不可无痕改时长，请点列表中的「改时长」。
      </p>
      <p v-if="error" class="error">{{ error }}</p>
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
            <td>
              <strong>{{ row.latestDurationMin ?? row.durationMin }} 分</strong>
              <span v-if="row.latestDurationMin !== undefined && row.latestDurationMin !== row.durationMin" class="muted">（留痕最新）</span>
            </td>
            <td>
              <span class="badge" :class="(row.revisionCount ?? 0) > 0 ? 'running' : 'idle'">
                {{ row.revisionCount ?? 0 }} 条
              </span>
            </td>
            <td>{{ row.waterLiters }} L</td>
            <td>
              <span class="badge" :class="row.status">{{ statusLabel[row.status] || row.status }}</span>
            </td>
            <td class="actions">
              <button class="btn" @click="openRevise(row)">改时长</button>
              <button class="btn ghost" @click="openRevisions(row)">留痕</button>
              <button class="btn ghost" @click="edit(row)">编辑</button>
              <button class="btn danger" @click="remove(row.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 改时长弹窗 -->
    <div v-if="revise.open" class="modal-mask" @click.self="closeRevise">
      <div class="modal panel">
        <h3 style="margin-top:0">修订轮灌时长</h3>
        <p class="muted">{{ revise.title }}</p>
        <div class="form-grid">
          <label>原分钟<input :value="revise.oldMin" type="number" disabled /></label>
          <label>新分钟<input v-model.number="revise.newMin" type="number" min="1" /></label>
          <label class="full">
            修订原因（去空白后至少 8 个字符）
            <textarea v-model="revise.reason" rows="3" placeholder="如：午后高温延长滴灌，避免作物缺水"></textarea>
          </label>
        </div>
        <p v-if="revise.error" class="error">接口返回：{{ revise.error }}</p>
        <div class="actions" style="margin-top:12px">
          <button class="btn" :disabled="revise.saving" @click="submitRevise">
            {{ revise.saving ? '提交中…' : '提交修订' }}
          </button>
          <button class="btn ghost" :disabled="revise.saving" @click="closeRevise">取消</button>
        </div>
      </div>
    </div>

    <!-- 留痕列表弹窗 -->
    <div v-if="revisions.open" class="modal-mask" @click.self="closeRevisions">
      <div class="modal panel">
        <h3 style="margin-top:0">时长修订留痕</h3>
        <p class="muted">{{ revisions.title }}</p>
        <p v-if="revisions.loading" class="muted">加载中…</p>
        <p v-else-if="revisions.error" class="error">接口返回：{{ revisions.error }}</p>
        <p v-else-if="!revisions.items.length" class="muted">暂无修订留痕，最新时长即当前时长。</p>
        <table v-else>
          <thead>
            <tr>
              <th>轮灌编号</th>
              <th>原分钟</th>
              <th>新分钟</th>
              <th>原因</th>
              <th>修订时刻</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in revisions.items" :key="r.id">
              <td>#{{ r.cycleId }}</td>
              <td>{{ r.oldMin }}</td>
              <td>{{ r.newMin }}</td>
              <td>{{ r.reason }}</td>
              <td>{{ new Date(r.revisedAt).toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
        <div class="actions" style="margin-top:12px">
          <button class="btn ghost" @click="closeRevisions">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>
