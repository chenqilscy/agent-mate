import { App as AntApp, ConfigProvider, theme as antTheme, type ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import type { ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'

const sharedToken: ThemeConfig['token'] = {
  colorPrimary: '#16b37a',
  colorInfo: '#1677ff',
  colorSuccess: '#16b37a',
  colorWarning: '#f0a020',
  colorError: '#e5484d',
  borderRadius: 10,
  borderRadiusLG: 14,
  controlHeight: 36,
  fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
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
          colorBgBase: dark ? '#15191e' : '#ffffff',
          colorBgContainer: dark ? '#1d2228' : '#ffffff',
          colorBgElevated: dark ? '#242a31' : '#ffffff',
          colorTextBase: dark ? '#f3f5f7' : '#161a1d',
          colorBorder: dark ? '#343b44' : '#e6e8eb',
        },
        components: {
          Button: { fontWeight: 600 },
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
