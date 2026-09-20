'use client'

import React, { useEffect, useState } from 'react'

interface ConfirmModalProps {
  open: boolean
  title: string
  message: string | React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
  loading?: boolean
  requireTextMatch?: string
  inputPlaceholder?: string
}

export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  loading = false,
  requireTextMatch,
  inputPlaceholder
}: ConfirmModalProps) {
  const [input, setInput] = useState('')
  useEffect(() => { if (!open) setInput('') }, [open])

  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) {
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, loading, onCancel])

  if (!open) return null

  const confirmDisabled = loading || (requireTextMatch ? input !== (requireTextMatch || '') : false)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative max-w-md w-full bg-white border-[3px] border-signal-ink shadow-[6px_6px_0px_0px_rgba(25,32,28,1)]" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b-[3px] border-signal-ink bg-signal-lime flex items-center justify-between">
          <div className="text-sm font-mono font-bold uppercase tracking-wider text-signal-ink">{title}</div>
          <button onClick={onCancel} className="text-signal-ink hover:text-signal-terra transition-colors" aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" /></svg>
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-sm text-signal-ink">
            {message}
          </div>
          {typeof requireTextMatch === 'string' && (
            <div>
              <div className="text-xs font-mono font-bold uppercase text-signal-mist mb-1.5">Type <span className="text-signal-ink underline font-extrabold">{requireTextMatch}</span> to confirm</div>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="input w-full p-2"
                placeholder={inputPlaceholder || 'Type to confirm'}
              />
            </div>
          )}
          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button onClick={onCancel} disabled={loading} className="signal-button btn-secondary text-xs">{cancelLabel}</button>
            <button onClick={onConfirm} disabled={confirmDisabled} className="signal-button signal-button--danger text-xs">{confirmLabel}</button>
          </div>
        </div>
      </div>
    </div>
  )
}

