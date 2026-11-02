import type { GlobalThemeOverrides } from 'naive-ui'

// Naive UI 主题覆盖（设计规范 §8.4）：令牌优先，主色 = --accent-ai，精准对齐字阶与字体栈
// 深浅两套必须成对维护：只切 data-theme 而不切 Naive theme，弹窗/表格/输入框会留在浅色。
const fontFamily =
  '"Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif'
const fontFamilyMono =
  '"Cascadia Mono", "JetBrains Mono", "Sarasa Mono SC", "Microsoft YaHei UI", ui-monospace, monospace'

const typography: GlobalThemeOverrides['common'] = {
  fontFamily,
  fontFamilyMono,
  fontSize: '14px',
  fontSizeSmall: '13px',
  fontSizeMedium: '14px',
  fontSizeLarge: '16px',
  borderRadius: '6px',
  borderRadiusSmall: '4px',
}

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    ...typography,
    primaryColor: '#1f5947',
    primaryColorHover: '#174a3a',
    primaryColorPressed: '#143d30',
    primaryColorSuppl: '#e6f1ec',
    successColor: '#15803D',
    warningColor: '#B45309',
    errorColor: '#DC2626',
    infoColor: '#0F766E',
  },
}

/** 深色覆盖：色值与 styles/tokens.css 的 [data-theme='dark'] 对齐。 */
export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    ...typography,
    primaryColor: '#16977a',
    primaryColorHover: '#1fae8d',
    primaryColorPressed: '#127a63',
    primaryColorSuppl: '#16977a',
    successColor: '#34d399',
    warningColor: '#fbbf24',
    errorColor: '#f87171',
    infoColor: '#60a5fa',
    bodyColor: '#111827',
    cardColor: '#1f2937',
    modalColor: '#1f2937',
    popoverColor: '#1f2937',
    tableColor: '#1f2937',
    inputColor: '#111827',
    borderColor: '#374151',
    dividerColor: '#374151',
    textColorBase: '#f9fafb',
    textColor1: '#f9fafb',
    textColor2: '#9ca3af',
    textColor3: '#6b7280',
    hoverColor: 'rgba(255, 255, 255, 0.06)',
  },
}
