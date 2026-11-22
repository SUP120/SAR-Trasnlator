import { useEffect, useRef, useState } from 'react'
import { getCachedEvent, getJob, submitAnalysis, type AnalysisSelection, type Job } from './api'

export function useAnalysis() {
  const active = useRef<AbortController>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [pending, setPending] = useState(false)
  const [source, setSource] = useState<AnalysisSelection['source'] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => () => active.current?.abort(), [])

  function dismiss() {
    active.current?.abort()
    active.current = null
    setPending(false)
    setSource(null)
    setJob(null)
    setError('')
  }

  async function submit(analysis: AnalysisSelection) {
    dismiss()
    const controller = new AbortController()
    active.current = controller
    setSource(analysis.source)
    setPending(true)
    try {
      const deadline = performance.now() + 165_000
      let current = await (analysis.source === 'cached'
        ? getCachedEvent(analysis.slug, controller.signal)
        : submitAnalysis(analysis, controller.signal))
      while (!controller.signal.aborted) {
        setJob(current)
        if (current.status !== 'queued' && current.status !== 'running') return
        if (performance.now() > deadline) throw new Error('The analysis timed out. Try a smaller area or shorter window.')
        await new Promise((resolve) => setTimeout(resolve, 650))
        controller.signal.throwIfAborted()
        current = await getJob(current.id, controller.signal)
      }
    } catch (problem) {
      if (!controller.signal.aborted) {
        setError(problem instanceof TypeError ? 'The analysis service could not be reached.'
          : problem instanceof Error ? problem.message : 'The request failed. Try again.')
      }
    } finally {
      if (active.current === controller) {
        active.current = null
        setPending(false)
      }
    }
  }

  return { job, pending, source, error, submit, dismiss }
}
