<template>
  <n-modal
    :show="show"
    preset="card"
    :trap-focus="false"
    :auto-focus="false"
    :title="`Agent 技能编排详情 · ${skill?.name || ''}`"
    style="width: 760px; max-width: 95vw; border-radius: 14px"
    @update:show="$emit('update:show', $event)"
  >
    <div v-if="skill" class="skill-modal-content">
      <div class="skill-modal-header">
        <div class="skill-title-row">
          <div style="flex: 1">
            <div class="row-between">
              <div class="row" style="gap: 8px; align-items: center; flex-wrap: wrap">
                <span class="skill-name">{{ skill.name }}</span>
                <span class="tag-soft mono" style="font-size: 11px">{{ skill.id }}</span>
              </div>
              <span :class="skill.enabled ? 'status-badge-active' : 'status-badge-off'">
                {{ skill.enabled ? '已启用' : '已停用' }}
              </span>
            </div>
            <div v-if="hintSummary" class="skill-hint">{{ hintSummary }}</div>
            <div class="skill-desc">{{ skill.summary }}</div>
          </div>
        </div>
      </div>

      <div class="spec-grid">
        <div class="spec-item">
          <span class="spec-label">类型</span>
          <span class="spec-value">{{ kindLabel }}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">版本</span>
          <span class="spec-value mono">{{ skill.version }}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">启用状态</span>
          <span class="spec-value">{{ skill.enabled ? '启用' : '停用' }}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">目录标识</span>
          <span class="spec-value mono">{{ skill.id }}</span>
        </div>
      </div>

      <div class="section-block guardrail-box">
        <div class="guardrail-title">技能正文</div>
        <div class="guardrail-desc">
          目录只返回名称、类型、版本和摘要。完整工作流在对应 <code>SKILL.md</code> 中，请通过「预览 / 编辑」读取；核心 System Prompt 仍由 Harness 固定生成。
        </div>
      </div>
    </div>

    <template #footer>
      <div class="row-between" style="width: 100%">
        <span class="small tertiary mono">Agent Skills Orchestration · V1.0 Controlled Vault</span>
        <button class="btn btn-secondary btn-sm" @click="$emit('update:show', false)">关闭</button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NModal } from 'naive-ui'
import { skillKindLabel, skillSummary } from '../../agent/skillLabels'
import type { AgentSkillMetadata } from '../../api/types'

const props = defineProps<{
  show: boolean
  skill: AgentSkillMetadata | null
}>()

defineEmits<{
  (e: 'update:show', val: boolean): void
}>()

const hintSummary = computed(() => skillSummary(props.skill?.id))
const kindLabel = computed(() => skillKindLabel(props.skill?.kind))
</script>

<style scoped>
.skill-modal-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.skill-modal-header {
  padding: 14px 16px;
  background: var(--bg-elevated, #f4f8f8);
  border-radius: 12px;
  border: 1px solid var(--border-subtle, #e5e7eb);
}
.skill-title-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.skill-icon {
  font-size: 32px;
  line-height: 1;
}
.skill-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #111827);
}
.skill-builtin-badge {
  background: color-mix(in srgb, var(--accent-ai, #1f5947) 10%, transparent);
  color: var(--accent-ai, #1f5947);
  border-color: color-mix(in srgb, var(--accent-ai, #1f5947) 20%, transparent);
  font-size: 11px;
}
.status-badge-active,
.status-badge-off {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  font-weight: 600;
  white-space: nowrap;
}
.status-badge-active {
  color: var(--accent-success, #10b981);
}
.status-badge-off {
  color: var(--text-tertiary, #6b7280);
}
.skill-hint {
  font-size: 12px;
  color: var(--c-agent, #10b981);
  margin-top: 6px;
  font-weight: 600;
}
.skill-desc {
  font-size: 13px;
  color: var(--text-secondary, #6b7280);
  margin-top: 6px;
  line-height: 1.5;
}
.spec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
.spec-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-main, #ffffff);
}
.spec-label {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
}
.spec-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}
.text-ai {
  color: var(--accent-ai, #1f5947);
}
.section-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}
.trigger-box {
  padding: 10px 12px;
  background: var(--bg-elevated, #f4f8f8);
  border-radius: 8px;
  border: 1px solid var(--border-subtle, #e5e7eb);
}
.cmd-pill {
  padding: 2px 8px;
  border-radius: 5px;
  background: #0f172a;
  color: #38bdf8;
  font-size: 11.5px;
  font-weight: 600;
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 8px;
}
.tool-item-card {
  padding: 8px 10px;
  border: 1px solid var(--border-subtle, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-main, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tool-item-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--c-profiles, #b45309);
}
.tool-item-desc {
  color: var(--text-secondary, #6b7280);
  line-height: 1.4;
  font-size: 11px;
}
.pipeline-flow {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: var(--bg-elevated, #f4f8f8);
  border-radius: 8px;
  border: 1px solid var(--border-subtle, #e5e7eb);
}
.flow-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--bg-main, #ffffff);
  border: 1px solid var(--border-subtle, #e5e7eb);
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
}
.flow-step.highlight {
  background: color-mix(in srgb, var(--accent-ai, #1f5947) 8%, transparent);
  border-color: var(--accent-ai, #1f5947);
  color: var(--accent-ai, #1f5947);
}
.step-num {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent-ai, #1f5947);
  color: #ffffff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
}
.flow-arrow {
  color: var(--text-tertiary, #9ca3af);
  font-size: 12px;
}
.guardrail-box {
  background: color-mix(in srgb, var(--accent-ai, #1f5947) 5%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-ai, #1f5947) 20%, transparent);
  border-radius: 8px;
  padding: 10px 12px;
}
.guardrail-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-ai, #1f5947);
  margin-bottom: 4px;
}
.guardrail-desc {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
}
</style>
