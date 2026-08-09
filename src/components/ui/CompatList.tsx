import { Fragment, type HTMLAttributes, type KeyboardEvent, type ReactNode } from 'react'
import { Spin } from 'antd'

type ListLocale = { emptyText?: ReactNode }
type RowKey<T> = keyof T | ((item: T, index: number) => string | number)

type CompatListProps<T> = Omit<HTMLAttributes<HTMLDivElement>, 'children' | 'loading'> & {
  className?: string
  dataSource?: readonly T[]
  loading?: boolean
  locale?: ListLocale
  renderItem: (item: T, index: number) => ReactNode
  rowKey?: RowKey<T>
  size?: 'small' | 'large' | 'default'
}

type CompatListItemProps = HTMLAttributes<HTMLLIElement> & { actions?: ReactNode[] }

type CompatListItemMetaProps = {
  avatar?: ReactNode
  title?: ReactNode
  description?: ReactNode
}

function rowIdentity<T>(item: T, index: number, rowKey?: RowKey<T>) {
  if (typeof rowKey === 'function') return rowKey(item, index)
  if (rowKey && item && typeof item === 'object') return String((item as Record<PropertyKey, unknown>)[rowKey as PropertyKey])
  return index
}

function CompatListBase<T>({ className = '', dataSource = [], loading = false, locale, renderItem, rowKey, size = 'default', ...rest }: CompatListProps<T>) {
  const classes = ['ant-list', 'compat-list', size === 'small' ? 'ant-list-sm' : '', size === 'large' ? 'ant-list-lg' : '', className].filter(Boolean).join(' ')
  return (
    <div {...rest} className={classes} aria-busy={loading || undefined}>
      {loading && dataSource.length === 0 ? (
        <div className="ant-list-empty-text compat-list-empty" role="status" aria-live="polite">
          <span aria-hidden="true"><Spin size="small" /></span> <span>正在加载…</span>
        </div>
      ) : dataSource.length ? (
        <ul className="ant-list-items compat-list-items">
          {dataSource.map((item, index) => <Fragment key={rowIdentity(item, index, rowKey)}>{renderItem(item, index)}</Fragment>)}
        </ul>
      ) : (
        <div className="ant-list-empty-text compat-list-empty">{locale?.emptyText ?? '暂无数据'}</div>
      )}
    </div>
  )
}

function CompatListItem({ actions, className = '', onClick, onKeyDown, role, tabIndex, children, ...rest }: CompatListItemProps) {
  const interactive = Boolean(onClick)
  const handleKeyDown = (event: KeyboardEvent<HTMLLIElement>) => {
    onKeyDown?.(event)
    if (!event.defaultPrevented && interactive && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault()
      event.currentTarget.click()
    }
  }
  return (
    <li
      {...rest}
      className={`ant-list-item compat-list-item ${className}`.trim()}
      role={role ?? (interactive ? 'button' : undefined)}
      tabIndex={tabIndex ?? (interactive ? 0 : undefined)}
      onClick={onClick}
      onKeyDown={interactive || onKeyDown ? handleKeyDown : undefined}
    >
      {children}
      {!!actions?.length && <ul className="ant-list-item-action compat-list-actions">{actions.map((action, index) => <li key={index}>{action}</li>)}</ul>}
    </li>
  )
}

function CompatListItemMeta({ avatar, title, description }: CompatListItemMetaProps) {
  return (
    <div className="ant-list-item-meta compat-list-meta">
      {avatar && <div className="ant-list-item-meta-avatar">{avatar}</div>}
      <div className="ant-list-item-meta-content">
        {title != null && <h4 className="ant-list-item-meta-title">{title}</h4>}
        {description != null && <div className="ant-list-item-meta-description">{description}</div>}
      </div>
    </div>
  )
}

const CompatListItemWithMeta = Object.assign(CompatListItem, { Meta: CompatListItemMeta })

export const CompatList = Object.assign(CompatListBase, { Item: CompatListItemWithMeta })
