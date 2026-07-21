import { WbButton, WbInput, WbTextArea } from '../ui/Primitives'
import { useState } from 'react'
import { useExpertStore } from '../../stores/expertStore'
import { toast } from '../../stores/toastStore'
import type { CustomExpert } from '../../lib/types'
import { AntModalBridge } from '../ui/AntModalBridge'


// 创建自定义专家（我的专家 · WB-049）。套现有 .np-* 弹窗/表单类，天然继承暗色覆盖。
// persona（人格指令）是让专家「真生效」的字段：召唤时注入系统提示；留空则用能力介绍兜底。
export function CreateExpertModal({ open, onClose, onCreated }: {
  open: boolean
  onClose: () => void
  onCreated: (e: CustomExpert) => void
}) {
  const createExpert = useExpertStore((s) => s.create)
  const [avatar, setAvatar] = useState('🧑')
  const [name, setName] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [intro, setIntro] = useState('')
  const [persona, setPersona] = useState('')
  const [tags, setTags] = useState('')
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const reset = () => { setAvatar('🧑'); setName(''); setSubtitle(''); setIntro(''); setPersona(''); setTags('') }
  const close = () => { reset(); onClose() }

  const confirm = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      const e = await createExpert({
        name: name.trim(),
        subtitle: subtitle.trim(),
        avatar: avatar.trim() || '🧑',
        intro: intro.trim(),
        persona: persona.trim(),
        tags: tags.split(/[,，\s]+/).map((t) => t.trim()).filter(Boolean),
      })
      toast('专家已创建 · ' + e.name)
      reset()
      onCreated(e)
    } catch {
      toast('创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AntModalBridge onClose={close} closeOnMask={!busy} zIndex={160}>
      <div className="np-modal" style={{ width: 480 }} role="dialog" aria-modal="true" aria-label="创建专家">
        <div className="np-h">创建专家<WbButton className="np-x" onClick={close}>×</WbButton></div>
        <div className="np-body">
          <div className="np-lbl">头像与名称</div>
          <div style={{ display: 'flex', gap: 10 }}>
            <WbInput className="np-input" style={{ width: 60, textAlign: 'center', flexShrink: 0 }} value={avatar} onChange={(e) => setAvatar(e.target.value)} maxLength={4} aria-label="头像 emoji" />
            <WbInput className="np-input" style={{ flex: 1 }} placeholder="专家名称，如「运营增长顾问」" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>

          <div className="np-lbl">职称 / 一句话身份</div>
          <WbInput className="np-input" placeholder="如：十年增长操盘手" value={subtitle} onChange={(e) => setSubtitle(e.target.value)} />

          <div className="np-lbl">能力介绍</div>
          <WbTextArea className="np-ta" placeholder="这个专家擅长什么、能帮用户解决什么问题（展示用）" value={intro} onChange={(e) => setIntro(e.target.value)} />

          <div className="np-lbl">人格指令<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>召唤时注入，决定它怎么回答</small></div>
          <WbTextArea className="np-ta" placeholder="以某专家身份作答的指令。如：以资深增长操盘手身份作答，先定位漏斗卡点，再给可执行动作，结论先行。留空则用上面的能力介绍。" value={persona} onChange={(e) => setPersona(e.target.value)} />

          <div className="np-lbl">标签<small style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>逗号分隔</small></div>
          <WbInput className="np-input" placeholder="增长, 漏斗诊断, 投放" value={tags} onChange={(e) => setTags(e.target.value)} />
        </div>
        <div className="np-foot">
          <div style={{ flex: 1 }} />
          <WbButton className="btn-ghost" onClick={close}>取消</WbButton>
          <WbButton className="btn-dark" disabled={!name.trim() || busy} onClick={confirm}>创建</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
