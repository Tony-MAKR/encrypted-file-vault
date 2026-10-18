export function BrandMark({ small = false }: { small?: boolean }) {
  return (
    <div
      className={`brand-mark${small ? ' brand-mark-small' : ''}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" role="presentation">
        <path d="M7 10V7a5 5 0 0 1 10 0v3" />
        <rect x="4" y="10" width="16" height="11" rx="2" />
        <path d="M12 14v3" />
      </svg>
    </div>
  )
}
