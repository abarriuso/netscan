import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { I18nContext, LANG_KEY, detectLang, translator } from './context'
import { STRINGS, type Lang } from './strings'

export default function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang)

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      localStorage.setItem(LANG_KEY, next)
    } catch {
      /* storage disabled — the choice lasts for this tab only */
    }
  }, [])

  const value = useMemo(
    () => ({ lang, setLang, t: translator(lang), locale: STRINGS[lang].locale }),
    [lang, setLang],
  )

  // Keep <html lang> in sync for screen readers and browser translation.
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
