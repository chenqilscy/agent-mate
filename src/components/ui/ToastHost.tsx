import { App } from 'antd'
import { useEffect } from 'react'
import { useToastStore } from '../../stores/toastStore'

export function ToastHost() {
  const { message: messageApi } = App.useApp()
  const { message, visible } = useToastStore()

  useEffect(() => {
    if (visible && message) {
      void messageApi.open({
        key: 'agentmate-global-toast',
        type: 'success',
        content: message,
        duration: 2,
        className: 'agentmate-ant-message',
      })
    }
  }, [message, messageApi, visible])

  return null
}
