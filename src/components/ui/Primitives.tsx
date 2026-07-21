import { Button as AntButton, Checkbox as AntCheckbox, Input as AntInput, Select as AntSelect, Slider as AntSlider } from 'antd'
import type { ButtonProps, InputProps, SelectProps } from 'antd'
import {
  Children,
  forwardRef,
  isValidElement,
  type ButtonHTMLAttributes,
  type ChangeEvent,
  type ForwardedRef,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

function assignRef<T>(ref: ForwardedRef<T>, value: T | null) {
  if (typeof ref === 'function') ref(value)
  else if (ref) ref.current = value
}

type NativeButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> & {
  type?: ButtonHTMLAttributes<HTMLButtonElement>['type']
}

/** Native-compatible Ant button used during the WorkBuddy skin migration. */
export const WbButton = forwardRef<HTMLButtonElement, NativeButtonProps>(function WbButton(
  { type = 'button', className = '', ...props },
  ref,
) {
  const visualType: ButtonProps['type'] = className.includes('btn-dark') ? 'primary' : 'default'
  const danger = /(^|\s)(danger|danger-b)(\s|$)/.test(className)
  return (
    <AntButton
      ref={ref}
      {...(props as ButtonProps)}
      htmlType={type}
      type={visualType}
      danger={danger}
      className={className}
    />
  )
})

/**
 * Ant Input keeps the native event/ref contract used by existing stores.
 * File/range/checkbox controls remain native because their Ant counterparts have
 * different value contracts and are migrated explicitly at their call sites.
 */
export const WbInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function WbInput(
  { type = 'text', ...props },
  ref,
) {
  if (type === 'file') {
    return <input ref={ref} type={type} {...props} />
  }
  if (type === 'checkbox' || type === 'radio') {
    const { checked, defaultChecked, onChange, className, disabled } = props
    return (
      <AntCheckbox
        checked={checked}
        defaultChecked={defaultChecked}
        disabled={disabled}
        className={className}
        aria-label={props['aria-label']}
        onChange={(event) => onChange?.(event as unknown as ChangeEvent<HTMLInputElement>)}
      />
    )
  }
  if (type === 'range') {
    const { value, defaultValue, min, max, step, onChange, className, disabled } = props
    return (
      <AntSlider
        value={value == null ? undefined : Number(value)}
        defaultValue={defaultValue == null ? undefined : Number(defaultValue)}
        min={min == null ? undefined : Number(min)}
        max={max == null ? undefined : Number(max)}
        step={step == null ? undefined : Number(step)}
        disabled={disabled}
        className={className}
        aria-label={props['aria-label']}
        onChange={(next) => onChange?.({ target: { value: String(next), valueAsNumber: next } } as ChangeEvent<HTMLInputElement>)}
      />
    )
  }
  return <AntInput ref={(instance) => assignRef(ref, instance?.input ?? null)} type={type} {...(props as InputProps)} />
})

export const WbTextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function WbTextArea(props, ref) {
    return (
      <AntInput.TextArea
        ref={(instance) => assignRef(ref, instance?.resizableTextArea?.textArea ?? null)}
        {...props}
      />
    )
  },
)

/** Native select event compatibility over Ant Select. */
export function WbSelect({ children, onChange, value, defaultValue, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const options: NonNullable<SelectProps['options']> = Children.toArray(children)
    .filter(isValidElement)
    .map((child) => {
      const option = child.props as { value?: string | number; children?: unknown; disabled?: boolean }
      return { value: option.value ?? '', label: option.children as string, disabled: option.disabled }
    })

  return (
    <AntSelect
      {...(props as SelectProps)}
      value={value as string | number | undefined}
      defaultValue={defaultValue as string | number | undefined}
      options={options}
      onChange={(next) => onChange?.({ target: { value: next } } as ChangeEvent<HTMLSelectElement>)}
    />
  )
}
