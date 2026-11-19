<template>
  <n-modal
    :show="show"
    preset="card"
    title="开通新成员账号"
    style="width: 440px"
    @update:show="$emit('update:show', $event)"
  >
    <div class="user-form">
      <div class="field">
        <label class="field-label">用户名 <span class="req">*</span></label>
        <n-input
          v-model:value="form.username"
          placeholder="输入成员账号名称"
          :status="fieldErrors.username ? 'error' : undefined"
          @update:value="clearFieldError('username')"
        />
        <span v-if="fieldErrors.username" class="field-error">{{ fieldErrors.username }}</span>
      </div>

      <div class="field">
        <label class="field-label">初始密码 <span class="req">*</span></label>
        <n-input
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          placeholder="至少 8 位，包含字母与数字"
          :status="fieldErrors.password ? 'error' : undefined"
          @update:value="clearFieldError('password')"
        />
        <span v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</span>
      </div>

      <div class="field">
        <label class="field-label">显示名</label>
        <n-input v-model:value="form.displayName" placeholder="例如：张三（可留空）" />
      </div>

      <div class="field">
        <label class="field-label">角色权限</label>
        <n-input value="平台成员 (全员同权)" readonly disabled />
      </div>
    </div>

    <template #footer>
      <div style="display: flex; gap: 8px; justify-content: flex-end">
        <n-button @click="$emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="saving" @click="handleSave">确认开通</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { api } from '../../api/http'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'success'): void
}>()

const message = useMessage()
const saving = ref(false)
const form = ref({ username: '', password: '', displayName: '' })
const fieldErrors = ref<Record<string, string>>({})

watch(
  () => props.show,
  (val) => {
    if (val) {
      form.value = { username: '', password: '', displayName: '' }
      fieldErrors.value = {}
    }
  },
)

async function handleSave() {
  if (!form.value.username.trim()) {
    message.warning('请输入用户名')
    return
  }
  if (!form.value.password || form.value.password.length < 8) {
    message.warning('初始密码不能少于 8 位')
    return
  }

  saving.value = true
  fieldErrors.value = {}
  try {
    // 全员同权：服务端恒写 member，契约外字段会被 extra=forbid 拒绝，不能带 role。
    await api.users.create({
      username: form.value.username.trim(),
      password: form.value.password,
      display_name: form.value.displayName.trim() || undefined,
    })
    message.success('成员账号已开通')
    emit('update:show', false)
    emit('success')
  } catch (err: any) {
    const fields = err?.fields
    if (fields && typeof fields === 'object') {
      fieldErrors.value = fields
      message.error('请按提示修正标红项')
    } else {
      message.error(err?.message || '开通账号失败')
    }
  } finally {
    saving.value = false
  }
}

/** 用户开始修改某个字段时清掉它的错误，避免旧提示一直挂着。 */
function clearFieldError(key: string) {
  if (fieldErrors.value[key]) {
    const next = { ...fieldErrors.value }
    delete next[key]
    fieldErrors.value = next
  }
}
</script>

<style scoped>
.user-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
.field-label .req {
  color: var(--accent-error);
}
.field-error {
  font-size: 12px;
  color: var(--accent-error);
}
</style>
