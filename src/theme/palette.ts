import type { ThemeConfig } from 'antd'

export type UIThemeMode = 'light' | 'dark'

/**
 * Shared App/Console surface contract. CSS custom properties mirror these
 * values; keeping Ant Design on the same palette prevents component surfaces
 * from falling back to algorithm defaults between the two products.
 */
export const uiPalette = {
  light: {
    page: '#f4f6f8',
    container: '#ffffff',
    elevated: '#ffffff',
    input: '#ffffff',
    header: '#ffffff',
    sidebar: '#ffffff',
    text: '#1d2939',
    textSecondary: '#667085',
    textTertiary: '#667085',
    border: '#e6e9ef',
    borderSecondary: '#f2f4f7',
  },
  dark: {
    page: '#0f1420',
    container: '#161c2b',
    elevated: '#1b2334',
    input: '#111827',
    header: '#151b2a',
    sidebar: '#111827',
    text: '#f2f4f7',
    textSecondary: '#93a0b8',
    textTertiary: '#7d899f',
    border: '#2a3348',
    borderSecondary: '#232c40',
  },
} as const

export function uiThemeColorToken(mode: UIThemeMode): ThemeConfig['token'] {
  const palette = uiPalette[mode]
  return {
    colorBgBase: palette.page,
    colorBgLayout: palette.page,
    colorBgContainer: palette.container,
    colorBgElevated: palette.elevated,
    colorBgSpotlight: palette.elevated,
    colorTextBase: palette.text,
    colorText: palette.text,
    colorTextSecondary: palette.textSecondary,
    colorTextTertiary: palette.textTertiary,
    colorBorder: palette.border,
    colorBorderSecondary: palette.borderSecondary,
  }
}
