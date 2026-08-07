import { App as AntApp, ConfigProvider, theme as antTheme, type ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import type { ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { UI_CONTROL_FONT_WEIGHT, uiTypographyToken } from '../../theme/typography'

const sharedToken: ThemeConfig['token'] = {
  colorPrimary: '#16b37a',
  colorInfo: '#3b82f6',
  colorSuccess: '#16b37a',
  colorWarning: '#f59e0b',
  colorError: '#e5484d',
  borderRadius: 8,
  borderRadiusLG: 10,
  controlHeight: 32,
  ...uiTypographyToken,
}

export function AppThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUIStore((state) => state.theme)
  const dark = theme === 'dark'

  return (
    <ConfigProvider
      locale={zhCN}
      componentSize="small"
      theme={{
        algorithm: dark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: {
          ...sharedToken,
          colorBgBase: dark ? '#0f1420' : '#f4f6f8',
          colorBgContainer: dark ? '#161c2b' : '#ffffff',
          colorBgElevated: dark ? '#1b2334' : '#ffffff',
          colorTextBase: dark ? '#f2f4f7' : '#1d2939',
          colorBorder: dark ? '#2a3348' : '#e6e9ef',
        },
        components: {
          Button: { fontWeight: UI_CONTROL_FONT_WEIGHT },
          Card: { paddingLG: 16 },
          Layout: {
            bodyBg: dark ? '#0f1420' : '#f4f6f8',
            headerBg: dark ? '#151b2a' : '#ffffff',
            siderBg: dark ? '#111827' : '#ffffff',
          },
          Modal: { borderRadiusLG: 10 },
        },
      }}
    >
      <AntApp className="agentmate-antd-app">{children}</AntApp>
    </ConfigProvider>
  )
}
