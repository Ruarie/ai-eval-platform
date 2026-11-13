<template>
      <n-drawer :show="show" :width="width" placement="right" @update:show="emit('update:show', $event)">
        <n-drawer-content title="数据集自动合成向导" closable>
          <div class="drawer-step-bar">
            <div class="step-badge" :class="{ active: aiGen.step === 1, done: aiGen.step === 2 }">
              <span class="step-idx">1</span>
              <span>合成模式与参数配置</span>
            </div>
            <span class="step-divider-line"></span>
            <div class="step-badge" :class="{ active: aiGen.step === 2 }">
              <span class="step-idx">2</span>
              <span>候选样本审核与导入</span>
            </div>
          </div>

          <div v-show="aiGen.step === 1" class="drawer-body">
            <div class="field">
              <label class="field-label">合成模式</label>
              <div class="tab-pill-group">
                <button class="tab-pill" :class="{ active: aiGen.mode === 'scene' }" @click="aiGen.mode = 'scene'">业务场景定向合成</button>
                <button class="tab-pill" :class="{ active: aiGen.mode === 'seed' }" @click="aiGen.mode = 'seed'">已有样本扩写</button>
                <button class="tab-pill" :class="{ active: aiGen.mode === 'doc' }" @click="aiGen.mode = 'doc'">需求文档/OpenAPI 提取</button>
              </div>
            </div>

            <div v-show="aiGen.mode === 'scene'">
              <div class="field">
                <label class="field-label">业务场景预设</label>
                <n-select v-model:value="aiGen.preset" :options="presetOptions" @update:value="onPresetChange" />
              </div>
              <div class="field">
                <label class="field-label">评估目标与边界描述 (Instruction) <span class="req">*</span></label>
                <n-input v-model:value="aiGen.instruction" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" placeholder="详述测试重点、边界限制或关注的能力维度..." />
              </div>
            </div>

            <div v-show="aiGen.mode === 'seed'">
              <div class="field">
                <label class="field-label">选择种子样本</label>
                <n-select v-model:value="aiGen.seedSample" :options="seedOptions" placeholder="选择一条已有样本作为扩展基准" />
              </div>
              <div class="field">
                <label class="field-label">扩写维度</label>
                <n-checkbox-group v-model:value="aiGen.dims">
                  <div class="row wrap" style="gap: 16px">
                    <n-checkbox value="synonym">同义改写</n-checkbox>
                    <n-checkbox value="constraint">前置约束增加</n-checkbox>
                    <n-checkbox value="boundary">边界异常提问</n-checkbox>
                  </div>
                </n-checkbox-group>
              </div>
            </div>

            <div v-show="aiGen.mode === 'doc'">
              <div class="field">
                <label class="field-label">需求文档 / OpenAPI 接口定义</label>
                <n-input v-model:value="aiGen.docText" class="mono" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" placeholder="粘贴接口定义或需求文本，系统将自动抽取测试问答对及上下文..." />
              </div>
            </div>

            <div class="divider-title">运行参数与生成规模</div>
            <div class="form-row-3">
              <div class="field">
                <label class="field-label">生成规模 (<b class="mono">{{ aiGen.rowCount }}</b> 行)</label>
                <n-slider v-model:value="aiGen.rowCount" :min="3" :max="25" :step="1" />
              </div>
              <div class="field">
                <label class="field-label">推理模型</label>
                <n-select
                  v-model:value="aiGen.model"
                  :options="[
                    { label: 'gpt-4.1 (推荐)', value: 'gpt-4.1' },
                    { label: 'claude-sonnet-4.5', value: 'claude-sonnet-4.5' },
                    { label: 'o4 (深度推理)', value: 'o4' },
                  ]"
                />
              </div>
              <div class="field">
                <label class="field-label">发散度 Temperature</label>
                <n-select
                  v-model:value="aiGen.temperature"
                  :options="[
                    { label: '0.2 (严谨收敛)', value: 0.2 },
                    { label: '0.5 (标准)', value: 0.5 },
                    { label: '0.8 (发散)', value: 0.8 },
                  ]"
                />
              </div>
            </div>

            <div class="field">
              <label class="field-label">生成字段目标</label>
              <div class="row wrap" style="gap: 16px; font-size: 13.5px">
                <n-checkbox v-model:checked="aiGen.genRef">标准答案 Reference</n-checkbox>
                <n-checkbox v-model:checked="aiGen.genCtx">注入上下文 Context</n-checkbox>
                <n-checkbox v-model:checked="aiGen.genTags">业务标签 Tags</n-checkbox>
              </div>
            </div>
          </div>

          <div v-show="aiGen.step === 2" class="drawer-body">
            <div class="row-between mb8">
              <span class="bold" style="font-size: 13.5px">候选项列表 (共 {{ aiGen.candidates.length }} 条，可就地微调)</span>
              <button class="link-btn" @click="toggleAllCandidates">全选 / 全不选</button>
            </div>
            <div class="preview-box custom-scroll">
              <table class="nordic-table preview-table">
                <thead>
                  <tr>
                    <th class="th-chk" style="width: 40px" title="全选 / 全不选" @click.stop="toggleAllCandidates">
                      <div class="clean-chk-box" :class="{ checked: aiAllSelected }">
                        <svg v-if="aiAllSelected" class="chk-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                    </th>
                    <th style="min-width: 180px">测试问句</th>
                    <th style="min-width: 200px">标准参考答案</th>
                    <th style="width: 80px">难度</th>
                    <th style="width: 50px">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(cand, ci) in aiGen.candidates" :key="ci">
                    <td class="td-chk" @click.stop="cand.selected = !cand.selected">
                      <div class="clean-chk-box" :class="{ checked: cand.selected }">
                        <svg v-if="cand.selected" class="chk-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                    </td>
                    <td><input v-model="cand.q" class="inline-input-clean" /></td>
                    <td><input v-model="cand.r" class="inline-input-clean" /></td>
                    <td><span class="diff-badge diff-中等">{{ cand.difficulty }}</span></td>
                    <td><button class="link-btn danger" @click="aiGen.candidates.splice(ci, 1)">移除</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <template #footer>
            <div class="drawer-footer-row">
              <n-button v-if="aiGen.step === 2" @click="aiGen.step = 1">← 返回调整参数</n-button>
              <span v-else></span>
              <div class="row" style="gap: 8px">
                <n-button @click="aiGen.show = false">取消</n-button>
                <n-button v-if="aiGen.step === 1" type="primary" :loading="aiGen.generating" @click="runAiGenerate">
                  {{ aiGen.generating ? '正在推理合成中…' : '生成候选样本 →' }}
                </n-button>
                <n-button v-else type="primary" :disabled="aiSelectedCount === 0" @click="commitCandidates">
                  采纳导入数据集 ({{ aiSelectedCount }} 条)
                </n-button>
              </div>
            </div>
          </template>
        </n-drawer-content>
      </n-drawer>
</template>

<script setup lang="ts">
/** 数据集自动合成向导：场景/种子/文档三种模式生成候选，确认后交给页面追加。 */
import { computed, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'

import { api } from '../../api/http'

type AiGenMode = 'scene' | 'seed' | 'doc'

interface SeedRow { q: string; r: string }
interface AiCandidate {
  selected: boolean
  q: string
  r: string
  c: string
  tags: string
  difficulty: string
}

const props = defineProps<{
  show: boolean
  width: number | string
  datasetId: string | null
  seedRows: SeedRow[]
  normalizeRow: (row: Record<string, unknown>) => {
    q: string; r: string; c: string; tags: string; difficulty: string
  }
}>()

const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'committed', candidates: AiCandidate[]): void
}>()

const message = useMessage()

const AI_PRESETS = [
  { name: '跨境收银与外币结算', desc: '涵盖外卡快捷支付、汇损换算、3DS 安全验证与跨境退款' },
  { name: '风控拦截与账户锁定', desc: '密码连续输错锁定、人脸识别解锁、高危 IP 拦截与大额转账审批' },
  { name: '退款售后与争议仲裁', desc: '退款时效 1-3 工作日、手续费返还规则、部分退款及银联争议处理' },
  { name: '发票与税务合规', desc: '增值税专用发票邮寄、电子发票 24h 发送、红字冲销及抬头修改' },
]

const aiGen = ref({
  show: false,
  step: 1 as 1 | 2,
  mode: 'scene' as AiGenMode,
  preset: AI_PRESETS[0].desc,
  instruction: AI_PRESETS[0].desc,
  seedSample: '',
  dims: ['synonym', 'constraint', 'boundary'] as string[],
  docText: '',
  rowCount: 8,
  model: 'gpt-4.1',
  temperature: 0.5,
  genRef: true,
  genCtx: true,
  genTags: true,
  generating: false,
  candidates: [] as AiCandidate[],
})

const presetOptions = computed(() => AI_PRESETS.map(p => ({ label: `${p.name} · ${p.desc}`, value: p.desc })))

const seedOptions = computed(() =>
  props.seedRows
    .filter(row => row.q.trim())
    .slice(0, 10)
    .map(row => ({
      label: `${row.q} => ${row.r}`.slice(0, 60),
      value: `${row.q} => ${row.r}`,
    })),
)

// 打开抽屉时回到第一步，并默认选中第一条种子样本
watch(() => props.show, (visible) => {
  if (!visible) return
  aiGen.value.step = 1
  if (!aiGen.value.seedSample && seedOptions.value.length) aiGen.value.seedSample = seedOptions.value[0].value
})

const aiSelectedCount = computed(() => aiGen.value.candidates.filter(c => c.selected).length)
const aiAllSelected = computed(() => aiGen.value.candidates.length > 0 && aiSelectedCount.value === aiGen.value.candidates.length)

function onPresetChange(val: string) {
  aiGen.value.instruction = val
}

async function runAiGenerate() {
  if (!props.datasetId || aiGen.value.generating) return
  const form = aiGen.value
  if (form.mode === 'scene' && !form.instruction.trim()) {
    message.warning('请填写场景描述')
    return
  }
  if (form.mode === 'seed' && !form.seedSample) {
    message.warning('请选择种子样本')
    return
  }
  if (form.mode === 'doc' && !form.docText.trim()) {
    message.warning('请粘贴需求文档文本')
    return
  }
  form.generating = true
  try {
    let candidates: AiCandidate[] = []
    if (api.isMock()) {
      await new Promise(resolve => setTimeout(resolve, 400))
      candidates = Array.from({ length: form.rowCount }, (_, i) => ({
        selected: true,
        q: `如何处理跨境交易退款中的汇损问题？（样本 #${i + 1}）`,
        r: form.genRef ? '根据平台协议，外币订单按原路退回，退款汇率以交易发起时汇率为准。' : '',
        c: form.genCtx ? '跨境结算指引' : '',
        tags: form.genTags ? '外汇,退款' : '',
        difficulty: i % 3 === 0 ? '高' : i % 3 === 1 ? '中等' : '简单',
      }))
    } else {
      const result = await api.datasets.generateRows({
        dataset_id: props.datasetId,
        mode: form.mode,
        instruction: form.instruction.trim(),
        source_text: form.docText.trim(),
        seed: form.seedSample,
        max_count: form.rowCount,
        model: form.model,
        temperature: form.temperature,
      })
      candidates = result.map(row => {
        const editable = props.normalizeRow(row)
        return { selected: true, q: editable.q, r: editable.r, c: editable.c, tags: editable.tags, difficulty: editable.difficulty || '中等' }
      })
      if (!candidates.length) throw new Error('未返回候选数据')
    }
    form.candidates = candidates
    form.step = 2
  } catch (err: any) {
    message.error(err.message || '数据合成失败')
  } finally {
    form.generating = false
  }
}

function toggleAllCandidates() {
  const target = aiSelectedCount.value < aiGen.value.candidates.length
  aiGen.value.candidates.forEach(c => { c.selected = target })
}

function commitCandidates() {
  const selected = aiGen.value.candidates.filter(c => c.selected)
  if (!selected.length) return
  emit('committed', selected.map(c => ({ ...c })))
  emit('update:show', false)
}
</script>
