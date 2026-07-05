import { toast } from '../../stores/toastStore'

// The ＋ menu (spec 4.2). The full hover cascade with sub-menus lands with the
// skills/connectors work in M5; M1 ships the root list wired to toasts.
const ROOT: [string, string, string][] = [
  ['file', '添加文件', 'M21 12.5l-8.5 8.5a5 5 0 01-7-7l9-9a3.5 3.5 0 015 5l-9 9a2 2 0 01-3-3l8-8'],
  ['ref', '引用对话中的文件', 'M16 8v5a3 3 0 006 0v-1a10 10 0 10-3.9 7.9'],
  ['mode', '模式', 'M4 7h16M4 12h10M4 17h7'],
  ['expert', '专家', 'M12 8a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6'],
  ['skillx', '技能', 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z'],
  ['connx', '连接器', 'M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2'],
]

export function PlusMenu({ onClose }: { onClose: () => void }) {
  return (
    <>
      {ROOT.map(([id, label, path]) => (
        <div
          key={id}
          className="pop-item px-root"
          onClick={() => { toast(label); onClose() }}
        >
          <span className="pi-ic">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={path} /></svg>
          </span>
          {label}
          <span className="arr">›</span>
        </div>
      ))}
    </>
  )
}
