import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AnimatedNumber, GlassPanel, Meter, QualityBadge, Sparkbar } from './metrics'

describe('GlassPanel', () => {
  it('renders its title and children', () => {
    render(
      <GlassPanel title="Dispositivos">
        <p>contenido</p>
      </GlassPanel>,
    )
    expect(screen.getByRole('heading', { name: /Dispositivos/ })).toBeInTheDocument()
    expect(screen.getByText('contenido')).toBeInTheDocument()
  })

  it('shows the meta text when provided', () => {
    render(
      <GlassPanel title="Alertas" meta="3 recientes">
        <div />
      </GlassPanel>,
    )
    expect(screen.getByText('3 recientes')).toBeInTheDocument()
  })

  it('prefers `right` over `meta` when both are given', () => {
    render(
      <GlassPanel title="X" meta="meta-text" right={<button>añadir</button>}>
        <div />
      </GlassPanel>,
    )
    expect(screen.getByRole('button', { name: 'añadir' })).toBeInTheDocument()
    expect(screen.queryByText('meta-text')).not.toBeInTheDocument()
  })
})

describe('QualityBadge', () => {
  it('renders an em dash for a null score', () => {
    render(<QualityBadge score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders the numeric score when present', () => {
    render(<QualityBadge score={92} />)
    expect(screen.getByText('92')).toBeInTheDocument()
  })

  it('renders a zero score (not treated as missing)', () => {
    render(<QualityBadge score={0} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})

describe('Meter', () => {
  it('renders label and value text', () => {
    render(<Meter percent={40} label="CPU" value="40%" />)
    expect(screen.getByText('CPU')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('renders without a label row when none is given', () => {
    const { container } = render(<Meter percent={10} />)
    // The bar track is always present.
    expect(container.querySelector('.rounded-full')).toBeTruthy()
  })
})

describe('Sparkbar', () => {
  it('renders one bar per value, including nulls as gaps', () => {
    const { container } = render(<Sparkbar values={[1, 2, null, 4]} />)
    // Outer flex wrapper contains one child <div> per value.
    const wrapper = container.firstElementChild!
    expect(wrapper.children).toHaveLength(4)
  })
})

describe('AnimatedNumber', () => {
  it('renders prefix, value and suffix', () => {
    render(<AnimatedNumber value={5} prefix="~" suffix=" ms" />)
    // Initial render shows the value immediately (0-delta animation).
    expect(screen.getByText(/~/)).toBeInTheDocument()
    expect(screen.getByText(/ms/)).toBeInTheDocument()
  })
})
