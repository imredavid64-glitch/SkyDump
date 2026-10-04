import { useEffect, useState, useCallback } from 'react'
import { MOCK_SECTORS } from '../data/mockDumpsites'

const DEMO_SECTORS = {
  'sector-7': {
    name: 'Rotterdam Industrial Zone, Netherlands',
    description: 'Europe\'s largest port - industrial waste dumping in harbor zones',
    highlight: '7 sites detected, 2 Critical, 3 High threat'
  },
  'sector-12': {
    name: 'Amazon River Basin, Brazil',
    description: 'Rainforest clearing for illegal waste disposal near waterways',
    highlight: '6 sites detected, 1 Critical, 4 High threat'
  },
  'sector-4': {
    name: 'Congo Basin Forest Reserve, DRC',
    description: 'Protected forest reserve with mining waste contamination',
    highlight: '8 sites detected, 3 Critical, 2 High threat'
  }
}

export function useDemoMode() {
  const [demoMode, setDemoMode] = useState(false)
  const [demoStep, setDemoStep] = useState(0)
  const [demoSector, setDemoSector] = useState('sector-7')
  const [demoNarrative, setDemoNarrative] = useState('')
  const [autoPlay, setAutoPlay] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const demo = params.get('demo')
    const auto = params.get('auto')
    const sector = params.get('sector')

    if (demo === 'true' || demo === '1') {
      setDemoMode(true)
      setAutoPlay(auto === 'true' || auto === '1')
      if (sector && MOCK_SECTORS[sector]) {
        setDemoSector(sector)
      }
      startDemoSequence()
    }
  }, [])

  const startDemoSequence = useCallback(() => {
    const steps = [
      { step: 0, delay: 500, narrative: 'Welcome to SkyDump AI — satellite-powered illegal waste detection' },
      { step: 1, delay: 2500, narrative: 'Select a monitored sector from the dropdown — we\'ll use Rotterdam' },
      { step: 2, delay: 4000, narrative: 'Adjust AI confidence threshold to filter detections (70% default)' },
      { step: 3, delay: 5500, narrative: 'Click Refresh to run live multi-spectral analysis on Sentinel-2 data' },
      { step: 4, delay: 8000, narrative: 'Results appear on map and sidebar — click any site for spectral details' },
      { step: 5, delay: 11000, narrative: 'Export GeoJSON report for municipal enforcement teams' },
      { step: 6, delay: 13000, narrative: 'Try other sectors: Amazon rainforest or Congo Basin reserves' },
    ]

    steps.forEach(({ step, delay, narrative }) => {
      setTimeout(() => {
        setDemoStep(step)
        setDemoNarrative(narrative)
      }, delay)
    })
  }, [])

  const nextStep = useCallback(() => {
    setDemoStep(prev => Math.min(prev + 1, 6))
  }, [])

  const prevStep = useCallback(() => {
    setDemoStep(prev => Math.max(prev - 1, 0))
  }, [])

  const skipDemo = useCallback(() => {
    setDemoMode(false)
    setDemoStep(0)
    setDemoNarrative('')
    const url = new URL(window.location.href)
    url.searchParams.delete('demo')
    url.searchParams.delete('auto')
    url.searchParams.delete('sector')
    window.history.replaceState({}, '', url)
  }, [])

  const getCurrentSectorInfo = useCallback(() => {
    return DEMO_SECTORS[demoSector] || DEMO_SECTORS['sector-7']
  }, [demoSector])

  return {
    demoMode,
    demoStep,
    demoSector,
    demoNarrative,
    autoPlay,
    setDemoSector,
    nextStep,
    prevStep,
    skipDemo,
    getCurrentSectorInfo,
    DEMO_SECTORS
  }
}

export function getDemoShareUrl(sector = 'sector-7', auto = true) {
  const base = window.location.origin + window.location.pathname
  return `${base}?demo=true&auto=${auto}&sector=${sector}`
}