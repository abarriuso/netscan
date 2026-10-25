import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import Tour from './Tour'
import { startTour, TOUR_KEY, tourSeen } from '@/lib/tour'

// jsdom has no matchMedia: the tour then behaves as under reduced motion
// (text shown at once), which keeps these tests deterministic.

function next() {
  fireEvent.click(screen.getByRole('button', { name: /next|finish/i }))
}

describe('first-run tour', () => {
  it('is pending until finished or skipped', () => {
    expect(tourSeen()).toBe(false)
    startTour()
    localStorage.setItem(TOUR_KEY, 'done')
    expect(tourSeen()).toBe(true)
  })

  it('walks the steps, switching to each tab it explains', () => {
    const onNavigate = vi.fn()
    render(<Tour onNavigate={onNavigate} />)
    expect(screen.getByRole('heading', { name: 'Welcome to NetScan' })).toBeInTheDocument()
    expect(screen.getByText(/mission 01\/15/)).toBeInTheDocument()

    next() // scan
    next() // mode
    next() // tabs
    expect(onNavigate).not.toHaveBeenCalled()
    next() // live
    expect(onNavigate).toHaveBeenLastCalledWith('live')
    expect(screen.getByText(/mission 05\/15/)).toBeInTheDocument()
    next() // overview
    expect(onNavigate).toHaveBeenLastCalledWith('resumen')

    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByRole('heading', { name: /^Live/ })).toBeInTheDocument()
  })

  it('arrow keys move, Escape skips and remembers it', () => {
    render(<Tour onNavigate={() => {}} />)
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByRole('heading', { name: 'Run a scan' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByRole('heading', { name: 'Welcome to NetScan' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(localStorage.getItem(TOUR_KEY)).toBe('skipped')
  })

  it('ends with the scan call to action and marks the tour done', () => {
    const onStartScan = vi.fn()
    render(<Tour onNavigate={() => {}} onStartScan={onStartScan} />)
    for (let i = 0; i < 14; i++) next()
    expect(screen.getByRole('heading', { name: 'Tutorial complete' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /quick scan now/i }))
    expect(onStartScan).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(TOUR_KEY)).toBe('done')
  })
})
