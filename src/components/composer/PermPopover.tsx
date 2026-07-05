import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

// Permission mode (spec 5.3). Default = sandbox-only; toggling full access is the
// real semantic behind the prototype's switch (越界操作触发授权 lands with tools).
export function PermPopover() {
  const perm = useSettingsStore((s) => s.perm)
  const setPerm = useSettingsStore((s) => s.setPerm)
  const full = perm === '完全访问权限'
  return (
    <>
      <div className="perm-desc">
        当前为默认权限，所有操作都会在安全沙箱约束内进行，超出范围会请求你的允许。
      </div>
      <div className="perm-tg">
        允许完全访问
        <span
          className={`sw ${full ? 'on' : ''}`.trim()}
          onClick={() => {
            const next = full ? '默认权限' : '完全访问权限'
            setPerm(next)
            toast('已切换 · ' + next)
          }}
        />
      </div>
    </>
  )
}
