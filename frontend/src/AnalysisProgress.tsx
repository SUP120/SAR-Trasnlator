import { useEffect, useRef, useState } from 'react'
import { Check, Radar, Sparkles } from 'lucide-react'
import './analysis-progress.css'

type Step = { label: string; detail: string }

export function AnalysisProgress({ title, steps, current = 0, context, floating = false, ai = false }: {
  title: string; steps: readonly Step[]; current?: number; context?: string; floating?: boolean; ai?: boolean
}) {
  const start = useRef(performance.now())
  const [elapsed, setElapsed] = useState(0)
  const Icon = ai ? Sparkles : Radar
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(Math.floor((performance.now() - start.current) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return <section className={`analysis-progress${floating ? ' analysis-progress-floating' : ''}`} aria-label={title}>
    <div className="progress-head">
      <div className="progress-emblem" aria-hidden="true"><Icon size={20} strokeWidth={1.6} /></div>
      <div><h3>{title}</h3>{context && <p>{context}</p>}</div>
      {elapsed > 0 && <span className="progress-elapsed" aria-hidden="true">{elapsed}s</span>}
    </div>
    <div className="progress-indicator" aria-hidden="true"><i /></div>
    <ol className="progress-steps" aria-label="Processing steps">
      {steps.map((step, index) => <li key={step.label} aria-current={index === current ? 'step' : undefined} className={index < current ? 'progress-done' : ''}>
        <span className="progress-mark" aria-hidden="true">{index < current && <Check size={12} />}</span><span>{step.label}</span>
      </li>)}
    </ol>
    <p className="progress-detail" role="status">{steps[current]?.detail}</p>
  </section>
}
