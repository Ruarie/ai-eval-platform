/**
 * Naive UI 按需注册。
 *
 * 之前 `app.use(naive)` 会引用整包默认导出，Rollup 无法摇树，vendor-naive 常驻
 * 1.4 MB（gzip 约 390 KB）。这里只注册模板里真正用到的组件；新增组件标签时必须
 * 同步加入下表，否则运行时会提示组件未解析。
 *
 * 说明：`useMessage` / `useDialog` 等函数式 API 从 'naive-ui' 直接 import 即可，
 * 与全局注册互不影响；对应的 Provider 组件已在下方注册。
 */
import {
  NAlert,
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NConfigProvider,
  NDialogProvider,
  NDrawer,
  NDrawerContent,
  NDropdown,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputGroup,
  NInputNumber,
  NMessageProvider,
  NModal,
  NPagination,
  NPopover,
  NProgress,
  NRadio,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSkeleton,
  NSlider,
  NSpace,
  NSpin,
  NSwitch,
  NUpload,
  NUploadDragger,
} from 'naive-ui'
import type { App, Component } from 'vue'

const components: Component[] = [
  NAlert,
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NConfigProvider,
  NDialogProvider,
  NDrawer,
  NDrawerContent,
  NDropdown,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputGroup,
  NInputNumber,
  NMessageProvider,
  NModal,
  NPagination,
  NPopover,
  NProgress,
  NRadio,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSkeleton,
  NSlider,
  NSpace,
  NSpin,
  NSwitch,
  NUpload,
  NUploadDragger,
]

export default {
  install(app: App) {
    for (const component of components) {
      if (component.name) app.component(component.name, component)
    }
  },
}
