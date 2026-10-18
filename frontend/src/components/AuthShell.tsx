import type { ReactNode } from 'react'
import { BrandMark } from './BrandMark'

interface AuthShellProps {
  eyebrow: string
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
}

export function AuthShell({
  eyebrow,
  title,
  subtitle,
  children,
  footer,
}: AuthShellProps) {
  return (
    <div className="auth-page">
      <div className="auth-shell">
        <header className="auth-heading">
          <BrandMark />
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          {subtitle && <p className="lede">{subtitle}</p>}
        </header>
        <main className="auth-card">{children}</main>
        {footer && <div className="auth-footer">{footer}</div>}
      </div>
    </div>
  )
}
