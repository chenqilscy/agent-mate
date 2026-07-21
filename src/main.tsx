import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/typography.css'
import './styles/icon-picker.css'
import './styles/tokens.css'
import './styles/app.css'
import './styles/antd.css'
import { App } from './App'
import { AppThemeProvider } from './components/ui/AppThemeProvider'
import { startAutomaticUpdateCheck } from './platform/updates'

startAutomaticUpdateCheck()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppThemeProvider>
      <App />
    </AppThemeProvider>
  </StrictMode>,
)
