import { useId, useState } from 'react'
import type { KeyboardEvent } from 'react'

interface TagsInputProps {
  label?: string
  value: string[]
  onChange: (tags: string[]) => void
  hint?: string
  maxTags?: number
}

export function TagsInput({
  label = '标签',
  value,
  onChange,
  hint,
  maxTags = 20,
}: TagsInputProps) {
  const inputId = useId()
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  const addTag = () => {
    const tag = draft.trim()
    if (!tag) {
      setDraft('')
      return
    }
    if (tag.length > 30) {
      setError('每个标签不能超过 30 个字符。')
      return
    }
    if (value.includes(tag)) {
      setDraft('')
      setError('')
      return
    }
    if (value.length >= maxTags) {
      setError(`标签最多 ${maxTags} 个。`)
      return
    }
    onChange([...value, tag])
    setDraft('')
    setError('')
  }

  const removeTag = (tag: string) => {
    onChange(value.filter((item) => item !== tag))
    setError('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addTag()
      return
    }
    if (event.key === 'Backspace' && !draft && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <div className="tags-input">
        {value.map((tag) => (
          <span className="tag-chip" key={tag}>
            {tag}
            <button
              type="button"
              aria-label={`移除标签 ${tag}`}
              onClick={() => removeTag(tag)}
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={inputId}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value)
            setError('')
          }}
          onKeyDown={handleKeyDown}
          onBlur={addTag}
          maxLength={30}
          placeholder={value.length === 0 ? '输入标签后按回车' : '继续添加…'}
        />
      </div>
      {error ? (
        <p className="form-field-error" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="field-hint">{hint}</p>
      )}
    </div>
  )
}
