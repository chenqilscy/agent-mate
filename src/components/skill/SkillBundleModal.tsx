import { App as AntApp, Select } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import type { SkillBundle } from '../../lib/types'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useSkillStore } from '../../stores/skillStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { WbButton, WbInput, WbTextArea } from '../ui/Primitives'

const EMPTY_ID = '__new__'

export function SkillBundleModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { modal } = AntApp.useApp()
  const installed = useSkillStore((s) => s.installed)
  const [bundles, setBundles] = useState<SkillBundle[]>([])
  const [selectedId, setSelectedId] = useState(EMPTY_ID)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [skills, setSkills] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const selected = bundles.find((item) => item.id === selectedId)
  const installedBySlug = useMemo(
    () => new Map(installed.map((item) => [item.slug || item.key, item])),
    [installed],
  )
  const addOptions = installed
    .filter((item) => !skills.includes(item.slug || item.key))
    .map((item) => ({
      value: item.slug || item.key,
      label: `${item.name}${item.disabled ? '（已关闭）' : ''}`,
    }))

  const fill = (bundle?: SkillBundle) => {
    setSelectedId(bundle?.id ?? EMPTY_ID)
    setName(bundle?.name ?? '')
    setDescription(bundle?.description ?? '')
    setSkills(bundle?.skills ?? [])
  }

  useEffect(() => {
    if (!open) return
    let alive = true
    setBusy(true)
    Promise.all([api.listSkillBundles(), useSkillStore.getState().load()])
      .then(([result]) => {
        if (!alive) return
        setBundles(result.bundles)
        fill(result.bundles[0])
      })
      .catch(() => { if (alive) toast('读取技能组合失败') })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [open])

  if (!open) return null

  const save = async () => {
    if (!name.trim() || skills.length === 0 || busy) return
    setBusy(true)
    try {
      const body = { name: name.trim(), description: description.trim(), skills }
      const result = selected
        ? await api.updateSkillBundle(selected.id, body)
        : await api.createSkillBundle(body)
      const next = selected
        ? bundles.map((item) => item.id === result.bundle.id ? result.bundle : item)
        : [...bundles, result.bundle]
      setBundles(next)
      fill(result.bundle)
      toast(selected ? '技能组合已更新' : '技能组合已创建')
    } catch (error) {
      toast(error instanceof Error ? error.message : '保存技能组合失败')
    } finally {
      setBusy(false)
    }
  }

  const remove = () => {
    if (!selected || busy) return
    modal.confirm({
      title: `删除技能组合「${selected.name}」？`,
      content: '仅删除组合，不会卸载其中的技能。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setBusy(true)
        try {
          await api.deleteSkillBundle(selected.id)
          const next = bundles.filter((item) => item.id !== selected.id)
          setBundles(next)
          fill(next[0])
          toast('技能组合已删除')
        } catch (error) {
          toast(error instanceof Error ? error.message : '删除技能组合失败')
        } finally {
          setBusy(false)
        }
      },
    })
  }

  const useBundle = () => {
    if (!selected) return
    useLoadoutStore.getState().summonSkillBundle(selected.id)
    toast(`已选择本机技能组合「${selected.name}」· 新 Run 请从 Server Workspace 发起`)
    onClose()
  }

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= skills.length) return
    const next = [...skills]
    ;[next[index], next[target]] = [next[target], next[index]]
    setSkills(next)
  }

  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy} zIndex={165}>
      <div className="np-modal" style={{ width: 680 }} role="dialog" aria-modal="true" aria-label="技能组合">
        <div className="np-h">
          技能组合
          <WbButton className="np-x" onClick={onClose} disabled={busy}>×</WbButton>
        </div>
        <div className="np-body" style={{ display: 'grid', gridTemplateColumns: '190px minmax(0, 1fr)', gap: 18 }}>
          <div>
            <WbButton className="btn-dark" style={{ width: '100%', justifyContent: 'center' }} onClick={() => fill()}>
              ＋ 新建组合
            </WbButton>
            <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
              {bundles.map((bundle) => (
                <WbButton
                  key={bundle.id}
                  className={`btn-ghost ${selectedId === bundle.id ? 'on' : ''}`.trim()}
                  style={{ justifyContent: 'flex-start', overflow: 'hidden', textOverflow: 'ellipsis' }}
                  onClick={() => fill(bundle)}
                >
                  {bundle.name}
                </WbButton>
              ))}
              {!busy && bundles.length === 0 && (
                <div style={{ color: 'var(--text-3)', fontSize: 12.5, lineHeight: 1.6 }}>还没有组合。创建后可跨项目复用。</div>
              )}
            </div>
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="np-lbl">组合名称</div>
            <WbInput className="np-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="如：发布检查" maxLength={120} />
            <div className="np-lbl">说明</div>
            <WbTextArea className="np-ta" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="这个组合适合什么任务" maxLength={500} />
            <div className="np-lbl">技能顺序</div>
            <Select
              style={{ width: '100%' }}
              options={addOptions}
              value={undefined}
              placeholder={installed.length ? '添加一个已安装技能' : '请先安装技能'}
              disabled={!addOptions.length}
              onChange={(value) => {
                if (!value) return
                setSkills((current) => [...current, value])
              }}
            />
            <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
              {skills.map((slug, index) => {
                const skill = installedBySlug.get(slug)
                return (
                  <div className="pkc-row" key={slug} style={{ cursor: 'default', padding: '8px 10px' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="pn">{index + 1}. {skill?.name || slug}</div>
                      {!skill && <div className="pd">本机已缺失，运行时会跳过并报告</div>}
                    </div>
                    <WbButton className="btn-ghost" aria-label="上移" disabled={index === 0} onClick={() => move(index, -1)}>↑</WbButton>
                    <WbButton className="btn-ghost" aria-label="下移" disabled={index === skills.length - 1} onClick={() => move(index, 1)}>↓</WbButton>
                    <WbButton className="btn-ghost" onClick={() => setSkills((current) => current.filter((item) => item !== slug))}>移除</WbButton>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
        <div className="np-foot">
          {selected && <WbButton className="btn-ghost" disabled={busy} onClick={remove}>删除</WbButton>}
          <div style={{ flex: 1 }} />
          {selected && <WbButton className="btn-ghost" disabled={busy} onClick={useBundle}>选择为本机组合</WbButton>}
          <WbButton className="btn-dark" disabled={!name.trim() || skills.length === 0 || busy} onClick={() => { void save() }}>
            {selected ? '保存修改' : '创建组合'}
          </WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
