import { Modal } from 'antd'
import type { ReactNode } from 'react'

interface AntModalBridgeProps {
  children: ReactNode
  onClose: () => void
  closeOnMask?: boolean
  keyboard?: boolean
  zIndex?: number
}

/**
 * Ant Design owns the portal, mask, focus trap, Escape handling and stacking.
 * The inner WorkBuddy modal class is intentionally retained as the product skin
 * while individual form controls move to Ant primitives.
 */
export function AntModalBridge({
  children,
  onClose,
  closeOnMask = true,
  keyboard = true,
  zIndex,
}: AntModalBridgeProps) {
  return (
    <Modal
      open
      centered
      footer={null}
      closable={false}
      mask={{ closable: closeOnMask }}
      keyboard={keyboard}
      onCancel={onClose}
      width="auto"
      zIndex={zIndex == null ? undefined : zIndex < 1000 ? 1000 + zIndex : zIndex}
      destroyOnHidden
      className="wb-ant-modal-bridge"
    >
      {children}
    </Modal>
  )
}
