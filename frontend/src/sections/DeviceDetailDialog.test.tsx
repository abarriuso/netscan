import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DeviceDetailHost from './DeviceDetailDialog'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'

// jsdom does no layout, so this guards the markup that caused the overlap:
// a wrapping flex row whose triggers took a percentage height of the list,
// letting the 6th tab spill over the content below.
describe('device detail tabs', () => {
  it('lays the six tabs out on a grid with auto-height triggers', async () => {
    const pending = () => new Promise<never>(() => {})
    vi.spyOn(api, 'deviceProfile').mockImplementation(pending)
    vi.spyOn(api, 'deviceMetrics').mockImplementation(pending)
    vi.spyOn(api, 'deviceUptime').mockImplementation(pending)
    vi.spyOn(api, 'deviceTimeline').mockImplementation(pending)
    openDeviceDetail('aa:bb:cc:dd:ee:ff')
    render(<DeviceDetailHost />)

    const list = await screen.findByTestId('device-tabs')
    expect(list.className).toMatch(/\bgrid\b/)
    expect(list.className).not.toMatch(/flex-wrap/)
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(6)
    for (const tab of tabs) expect(tab.className).toMatch(/\bh-auto\b/)
  })
})
