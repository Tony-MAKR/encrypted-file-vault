import type { InputHTMLAttributes } from 'react'

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function FormField({ label, hint, id, name, ...props }: FormFieldProps) {
  const inputId = id ?? name ?? label

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <input id={inputId} name={name} {...props} />
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  )
}
