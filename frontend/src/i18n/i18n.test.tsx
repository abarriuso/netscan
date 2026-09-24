import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import I18nProvider from './I18nProvider'
import { LANG_KEY, detectLang, translator, useI18n } from './context'
import { STRINGS } from './strings'

function Probe() {
  const { t, lang, setLang } = useI18n()
  return (
    <>
      <span data-testid="tab">{t('tabDevices')}</span>
      <button onClick={() => setLang(lang === 'en' ? 'es' : 'en')}>{t('switchTo')}</button>
    </>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('i18n', () => {
  it('English and Spanish define the same keys', () => {
    expect(Object.keys(STRINGS.es).sort()).toEqual(Object.keys(STRINGS.en).sort())
  })

  it('follows the browser language when nothing is saved', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('es-ES')
    expect(detectLang()).toBe('es')
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-FR')
    expect(detectLang()).toBe('en')
  })

  it('prefers a saved choice over the browser', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('es-ES')
    localStorage.setItem(LANG_KEY, 'en')
    expect(detectLang()).toBe('en')
  })

  it('switches language, remembers it and updates <html lang>', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-GB')
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    )
    expect(screen.getByTestId('tab')).toHaveTextContent('Devices')
    fireEvent.click(screen.getByRole('button', { name: 'ES' }))
    expect(screen.getByTestId('tab')).toHaveTextContent('Dispositivos')
    expect(document.documentElement.lang).toBe('es')
    expect(localStorage.getItem(LANG_KEY)).toBe('es')
  })

  it('formats parameterised entries and falls back for unknown alert kinds', () => {
    const en = translator('en')
    const es = translator('es')
    expect(en('discovered', 3)).toBe('3 discovered')
    expect(es('discovered', 3)).toBe('3 descubiertos')
    expect(es('alertKind', 'device_down')).toBe('Dispositivo caído')
    expect(en('alertKind', 'something_new')).toBe('something_new')
    expect(es('toolPurpose', 'nmap', 'fallback')).toMatch(/versiones/)
    expect(es('toolPurpose', 'unknown-tool', 'fallback')).toBe('fallback')
  })
})
