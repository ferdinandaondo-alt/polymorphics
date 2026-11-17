import { useEffect, useState } from 'react'

// Load data on mount / when deps change. Keeps showing old data while reloading (no flicker).
export function useLoad(fn, deps = []) {
  const [state, set] = useState({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let stale = false
    set((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => { if (!stale) set({ data, error: null, loading: false }) })
      .catch((e) => { if (!stale) set({ data: null, error: e.message, loading: false }) })
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}
