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
  borderRadius: 10,
  borderRadiusLG: 14,
  controlHeight: 36,
  ...uiTypographyToken,
}

export function AppThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUIStore((state) => state.theme)
  const dark = theme === 'dark'

  return (
    <ConfigProvider
      locale={zhCN}
      componentSize="middle"
      theme={{
        algorithm: dark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: {
          ...sharedToken,
          colorBgBase: dark ? '#0d1117' : '#ffffff',
          colorBgContainer: dark ? '#141a21' : '#ffffff',
          colorBgElevated: dark ? '#1f2329' : '#ffffff',
          colorTextBase: dark ? '#eceef1' : '#161a1d',
          colorBorder: dark ? '#2b3138' : '#e6e8eb',
        },
        components: {
          Button: { fontWeight: UI_CONTROL_FONT_WEIGHT },
          Card: { paddingLG: 20 },
          Layout: {
            bodyBg: dark ? '#15191e' : '#f7f8fa',
            headerBg: dark ? '#1d2228' : '#ffffff',
            siderBg: dark ? '#1d2228' : '#ffffff',
          },
          Modal: { borderRadiusLG: 16 },
        },
      }}
    >
      <AntApp className="agentmate-antd-app">{children}</AntApp>
    </ConfigProvider>
  )
}
