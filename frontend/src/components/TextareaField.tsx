import type { TextareaHTMLAttributes } from 'react'

interface TextareaFieldProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  hint?: string
}

export function TextareaField({
  label,
  hint,
  id,
  name,
  ...props
}: TextareaFieldProps) {
  const inputId = id ?? name ?? label

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <textarea id={inputId} name={name} {...props} />
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  )
}
