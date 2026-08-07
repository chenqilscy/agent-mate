import { App as AntApp, ConfigProvider, theme as antTheme, type ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import type { ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { uiPalette, uiThemeColorToken } from '../../theme/palette'
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
  const mode = dark ? 'dark' : 'light'
  const palette = uiPalette[mode]

  return (
    <ConfigProvider
      locale={zhCN}
      componentSize="small"
      theme={{
        algorithm: dark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: {
          ...sharedToken,
          ...uiThemeColorToken(mode),
        },
        components: {
          Button: { fontWeight: UI_CONTROL_FONT_WEIGHT },
          Card: { paddingLG: 16 },
          Layout: {
            bodyBg: palette.page,
            headerBg: palette.header,
            siderBg: palette.sidebar,
          },
          Modal: { borderRadiusLG: 10 },
        },
      }}
    >
      <AntApp className="agentmate-antd-app">{children}</AntApp>
    </ConfigProvider>
  )
}
