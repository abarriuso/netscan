import { describe, expect, it } from 'vitest'
import { translator } from './context'

describe('risk factor texts', () => {
  const es = translator('es')
  const en = translator('en')

  it('translates factors by id, including ids carrying a URL suffix', () => {
    expect(es('riskTitle', 'port-23', 'Telnet open')).toMatch(/^Telnet abierto/)
    expect(es('riskFix', 'port-23', 'Disable Telnet')).toBe('Desactiva Telnet; usa SSH.')
    expect(es('riskTitle', 'cert-expired-https://10.0.0.2:443/', 'Expired')).toBe('Certificado TLS caducado')
    expect(es('riskTitle', 'weak-tls-https://10.0.0.2:8443/', 'x')).toBe('Protocolo TLS obsoleto negociado')
  })

  it('keeps the backend text when there is no translation', () => {
    expect(es('riskTitle', 'finding-nuclei-cve-2024-1', 'nuclei: CVE-2024-1')).toBe('nuclei: CVE-2024-1')
    expect(es('riskTitle', 'something-new', 'Original')).toBe('Original')
    expect(en('riskTitle', 'port-23', 'Telnet open')).toBe('Telnet open')
  })

  it('does not confuse port-21 with port-2375', () => {
    expect(es('riskTitle', 'port-2375', 'x')).toMatch(/Docker/)
    expect(es('riskTitle', 'port-21', 'x')).toMatch(/FTP/)
  })
})
