import { createContext, useContext } from 'react'
import { LANGS, STRINGS, type Dict, type Key, type Lang } from './strings'

export const LANG_KEY = 'netscan_lang'

type Args<K extends Key> = Dict[K] extends (...args: infer A) => string ? A : []

/** Keys whose entry is plain text (no parameters). */
export type TextKey = { [K in Key]: Dict[K] extends string ? K : never }[Key]

export type Translate = <K extends Key>(key: K, ...args: Args<K>) => string

/** Starting language: a saved choice, otherwise the browser's (Spanish for
 *  "es*", English for anything else). */
export function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved && (LANGS as readonly string[]).includes(saved)) return saved as Lang
  } catch {
    /* storage disabled — fall back to the browser language */
  }
  return /^es\b/i.test(navigator.language || '') ? 'es' : 'en'
}

export function translator(lang: Lang): Translate {
  const dict = STRINGS[lang]
  return (key, ...args) => {
    const entry = dict[key] as string | ((...a: unknown[]) => string)
    return typeof entry === 'function' ? entry(...args) : entry
  }
}

export interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: Translate
  /** BCP 47 locale for dates and numbers in the current language. */
  locale: string
}

// English default, so a component rendered on its own (unit tests) works
// without a provider.
export const I18nContext = createContext<I18n>({
  lang: 'en',
  setLang: () => {},
  t: translator('en'),
  locale: STRINGS.en.locale,
})

export const useI18n = () => useContext(I18nContext)
