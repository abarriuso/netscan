import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { acquireEventStream, backLines, streamState, subscribeBack } from '@/lib/eventStream'
import { frontLines, subscribeFront } from '@/lib/telemetry'
import type { FeedLine } from '@/types'

/** Keep the shared /ws/events connection open while the caller is mounted. */
export function useEventStreamConnection() {
  useEffect(() => acquireEventStream(), [])
}

export function useBackLines(): FeedLine[] {
  return useSyncExternalStore(subscribeBack, backLines, backLines)
}

export function useFrontLines(): FeedLine[] {
  return useSyncExternalStore(subscribeFront, frontLines, frontLines)
}

export function useStreamState() {
  return useSyncExternalStore(subscribeBack, streamState, streamState)
}

/** Backend + frontend lines merged in time order. */
export function useMergedFeed(): FeedLine[] {
  const back = useBackLines()
  const front = useFrontLines()
  return useMemo(() => {
    const out: FeedLine[] = []
    let i = 0
    let j = 0
    // Both inputs are already chronological: a linear merge, not a sort.
    while (i < back.length || j < front.length) {
      if (j >= front.length || (i < back.length && back[i].t <= front[j].t)) out.push(back[i++])
      else out.push(front[j++])
    }
    return out
  }, [back, front])
}

/** Latest backend line whose source is one of `sources` (header ticker). */
export function useLastBackLine(sources: string[], minLevel: 'debug' | 'info' = 'info'): FeedLine | null {
  const back = useBackLines()
  return useMemo(() => {
    for (let i = back.length - 1; i >= 0; i--) {
      const l = back[i]
      if (sources.includes(l.source) && (minLevel === 'debug' || l.level !== 'debug')) return l
    }
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [back, minLevel, sources.join(',')])
}
