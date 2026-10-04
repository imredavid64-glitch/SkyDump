import { useState, useCallback, useEffect, Suspense, lazy } from 'react'
import { Satellite, AlertTriangle, Layers, Download, Settings, RefreshCw, MapPin, Zap, Flag, Plus, Sun, Moon, Wifi, WifiOff, Loader2, Maximize, RotateCcw, X, Share2 } from 'lucide-react'
import { get_all_features, filter_features_by_confidence, calculate_summary_stats, MOCK_SECTORS } from './data/mockDumpsites'
import { useAnalysisWebSocket } from './hooks/useAnalysisWebSocket'
import { useDemoMode } from './hooks/useDemoMode'
import { OfflineIndicator } from './components/OfflineIndicator'

// Lazy load heavy components
const MapView = lazy(() => import('./components/MapView').then(module => ({ default: module.MapView })))
const AnalyticsPanel = lazy(() => import('./components/AnalyticsPanel'))
const SpectralViewer = lazy(() => import('./components/SpectralViewer'))
const CitizenReport = lazy(() => import('./components/CitizenReport'))
const ComparisonSlider = lazy(() => import('./components/ComparisonSlider'))

function Header({ selectedSector, onSectorChange, confidenceThreshold, onConfidenceChange, onExport, onRefresh, isLoading, onReportClick, onComparisonClick, theme, onThemeToggle, demoMode, demoNarrative, demoStep, nextStep, prevStep, skipDemo, DEMO_SECTORS }) {
  const sectors = Object.entries(MOCK_SECTORS).map(([id, data]) => ({
    id,
    name: data.metadata.name,
    center: data.metadata.center
  }))

  return (
    <header className="fixed top-0 left-0 right-0 z-40" style={{ backgroundColor: 'var(--header-bg)', borderBottomColor: 'var(--border-color)' }}>
      <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center">
              <Satellite className="w-6 h-6 text-slate-950" />
            </div>
            <span className="absolute -bottom-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full border-2 border-slate-950 animate-pulse" title="Live" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100 tracking-tight">SkyDump AI</h1>
            <p className="text-xs text-slate-500">Illegal Satellite Waste Detection</p>
          </div>
        </div>

        <div className="flex items-center gap-4 flex-1 max-w-2xl mx-8">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <MapPin className="w-4 h-4 text-slate-400" />
            <select
              value={selectedSector}
              onChange={(e) => onSectorChange(e.target.value)}
              className="bg-transparent text-slate-100 text-sm focus:outline-none cursor-pointer appearance-none"
              style={{ color: 'var(--text-primary)' }}
            >
              {sectors.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border hidden sm:flex" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <Zap className="w-4 h-4 text-emerald-500" />
            <span className="text-xs text-slate-300">AI Confidence</span>
            <input
              type="range"
              min="30"
              max="95"
              value={Math.round(confidenceThreshold * 100)}
              onChange={(e) => onConfidenceChange(parseInt(e.target.value) / 100)}
              className="slider w-32"
              aria-label="Confidence threshold"
            />
            <span className="text-xs font-mono text-emerald-400 w-10 text-right">{Math.round(confidenceThreshold * 100)}%</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border hidden md:flex" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <span className="relative flex items-center gap-1.5">
              <span className="status-dot connected" />
              <span className="text-xs text-slate-300">Live Satellite</span>
            </span>
          </div>

          <button
            onClick={onComparisonClick}
            className="btn-secondary flex items-center gap-2 hidden sm:flex"
            title="Before/After Comparison Slider"
            style={{ backgroundColor: 'var(--btn-secondary-bg)', borderColor: 'var(--btn-secondary-border)' }}
          >
            <Maximize className="w-4 h-4" />
            <span>Compare</span>
          </button>

          <button
            onClick={onReportClick}
            className="btn-primary flex items-center gap-2 hidden sm:flex"
            title="Report Illegal Dumping"
          >
            <Flag className="w-4 h-4" />
            <span>Report</span>
          </button>

          <button
            onClick={onThemeToggle}
            className="btn-secondary flex items-center gap-2 hidden sm:flex"
            title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            style={{ backgroundColor: 'var(--btn-secondary-bg)', borderColor: 'var(--btn-secondary-border)' }}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            <span className="hidden sm:inline">{theme === 'dark' ? 'Light' : 'Dark'}</span>
          </button>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="btn-secondary flex items-center gap-2"
            title="Refresh Data"
            style={{ backgroundColor: 'var(--btn-secondary-bg)', borderColor: 'var(--btn-secondary-border)' }}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          <button
            onClick={onExport}
            className="btn-primary flex items-center gap-2"
            title="Export GeoJSON Report"
          >
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Export</span>
          </button>
        </div>
      </div>

      {demoMode && (
        <div className="fixed top-16 left-0 right-0 z-35 pointer-events-none px-4">
          <div className="max-w-4xl mx-auto pointer-events-auto">
            <div className="bg-gradient-to-r from-emerald-500/10 to-emerald-700/10 border border-emerald-500/30 rounded-xl p-4 animate-slide-down">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                    <Satellite className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div>
                    <p className="font-semibold text-slate-100">Guided Demo Mode</p>
                    <p className="text-xs text-slate-400">Step {demoStep + 1} of 7 — {demoNarrative}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={prevStep} disabled={demoStep === 0} className="btn-secondary p-1.5 rounded-lg" title="Previous">←</button>
                  <button onClick={nextStep} disabled={demoStep === 6} className="btn-primary p-1.5 rounded-lg" title="Next">→</button>
                  <button onClick={skipDemo} className="btn-secondary p-1.5 rounded-lg text-xs" title="Skip Demo">Skip</button>
                </div>
              </div>
              
              {demoStep < 6 && (
                <div className="flex items-center gap-4 text-xs text-slate-400">
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">1</span>
                    <span>Select Sector</span>
                  </div>
                  <div className="w-8 h-px bg-slate-700" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">2</span>
                    <span>Set Confidence</span>
                  </div>
                  <div className="w-8 h-px bg-slate-700" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">3</span>
                    <span>Run Analysis</span>
                  </div>
                  <div className="w-8 h-px bg-slate-700" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">4</span>
                    <span>Explore Results</span>
                  </div>
                  <div className="w-8 h-px bg-slate-700" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">5</span>
                    <span>Export Report</span>
                  </div>
                  <div className="w-8 h-px bg-slate-700" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center text-[10px] font-bold text-slate-400">6</span>
                    <span>Try Other Sectors</span>
                  </div>
                </div>
              )}
              
              {demoStep === 6 && (
                <div className="flex items-center gap-4 text-xs text-slate-400">
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center text-[10px] font-bold text-slate-950">✓</span>
                    <span className="text-emerald-400">Complete!</span>
                  </div>
                  <div className="w-8 h-px bg-emerald-500" />
                  <div className="flex items-center gap-1">
                    <span className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center text-[10px] font-bold text-slate-950">✓</span>
                    <span className="text-emerald-400">Share Demo</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="px-4 pb-3 sm:hidden">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Zap className="w-4 h-4 text-emerald-500" />
          <span className="text-xs text-slate-300">AI Confidence</span>
          <input
            type="range"
            min="30"
            max="95"
            value={Math.round(confidenceThreshold * 100)}
            onChange={(e) => onConfidenceChange(parseInt(e.target.value) / 100)}
            className="slider flex-1"
          />
          <span className="text-xs font-mono text-emerald-400 w-10 text-right">{Math.round(confidenceThreshold * 100)}%</span>
        </div>
      </div>
    </header>
  )
}

function Sidebar({ features, confidenceThreshold, onExport, selectedFeature, onFeatureSelect }) {
  const filtered = filter_features_by_confidence(features, confidenceThreshold)
  const summary = calculate_summary_stats(filtered)

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-80 bg-slate-950/95 backdrop-blur-md border-r border-slate-800 overflow-y-auto scrollbar-thin z-30 pt-20 md:pt-16">
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">Detected Sites</h2>
          <span className="text-xs text-slate-400">{filtered.length} / {features.length}</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {Object.entries(summary.by_threat).map(([level, count]) => (
            <div key={level} className={`threat-badge threat-${level.toLowerCase()}`}>
              {level}: {count}
            </div>
          ))}
        </div>

        <div className="space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto scrollbar-thin">
          {filtered.length === 0 ? (
            <div className="text-center py-8 text-slate-500">
              <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
              <p>No sites match current confidence threshold</p>
            </div>
          ) : (
            filtered.map((feature, index) => {
              const props = feature.properties
              const isSelected = selectedFeature?.properties?.id === props.id
              return (
                <button
                  key={props.id}
                  onClick={() => onFeatureSelect(feature)}
                  className={`w-full text-left p-3 rounded-lg transition-all ${
                    isSelected
                      ? 'bg-emerald-500/10 border border-emerald-500/30'
                      : 'bg-slate-850/50 border border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs text-emerald-400">{props.id}</span>
                        <span className={`threat-badge threat-${props.threat_level.toLowerCase()}`}>
                          {props.threat_level}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 font-mono mb-1">
                        {props.centroid[1].toFixed(4)}, {props.centroid[0].toFixed(4)}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-400">
                        <span>{props.area_m2.toLocaleString()} m²</span>
                        <span>{props.estimated_tonnage.toFixed(1)} t</span>
                        <span>{(props.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                    {isSelected && (
                      <div className="w-2 h-full bg-emerald-500 rounded-r-lg" />
                    )}
                  </div>
                </button>
              )
            })
          )}
        </div>

        <button
          onClick={onExport}
          className="w-full btn-primary justify-center mt-4"
        >
          <Download className="w-4 h-4 mr-2" />
          Export GeoJSON Report
        </button>
      </div>
    </aside>
  )
}

function RightPanel({ selectedFeature }) {
  if (!selectedFeature) {
    return (
      <aside className="fixed right-0 top-0 bottom-0 w-72 bg-slate-950/95 backdrop-blur-md border-l border-slate-800 overflow-y-auto scrollbar-thin z-30 pt-20 md:pt-16">
        <div className="p-4 text-center text-slate-500">
          <AlertTriangle className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p className="text-sm">Select a site from the list or map to view spectral analysis and details</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="fixed right-0 top-0 bottom-0 w-72 bg-slate-950/95 backdrop-blur-md border-l border-slate-800 overflow-y-auto scrollbar-thin z-30 pt-20 md:pt-16">
      <div className="p-4 space-y-4">
        <SpectralViewer feature={selectedFeature} />
        
        <div className="card">
          <h3 className="font-semibold text-slate-100 mb-3">Site Details</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-400">ID</dt>
              <dd className="font-mono text-emerald-400">{selectedFeature.properties.id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Coordinates</dt>
              <dd className="font-mono text-slate-300">
                {selectedFeature.properties.centroid[1].toFixed(5)}, {selectedFeature.properties.centroid[0].toFixed(5)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Area</dt>
              <dd className="font-mono text-slate-300">{selectedFeature.properties.area_m2.toLocaleString()} m²</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Est. Tonnage</dt>
              <dd className="font-mono text-slate-300">{selectedFeature.properties.estimated_tonnage.toFixed(1)} t</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Confidence</dt>
              <dd className="font-mono text-emerald-400">{(selectedFeature.properties.confidence * 100).toFixed(1)}%</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Risk Score</dt>
              <dd className="font-mono text-amber-400">{selectedFeature.properties.risk_score}/100</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Threat Level</dt>
              <dd className={`font-medium ${{
                Critical: 'text-red-400',
                High: 'text-amber-400',
                Moderate: 'text-emerald-400',
                Low: 'text-slate-400'
              }[selectedFeature.properties.threat_level]}`}>
                {selectedFeature.properties.threat_level}
              </dd>
            </div>
            <div className="flex justify-between border-t border-slate-800 pt-2">
              <dt className="text-slate-400">Detection Date</dt>
              <dd className="font-mono text-slate-300">{selectedFeature.properties.detection_date}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Sensor</dt>
              <dd className="font-mono text-slate-300">{selectedFeature.properties.sensor}</dd>
            </div>
          </dl>
        </div>
      </div>
    </aside>
  )
}

export function App() {
  const [selectedSector, setSelectedSector] = useState('sector-7')
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7)
  const [features, setFeatures] = useState([])
  const [selectedFeature, setSelectedFeature] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [mapKey, setMapKey] = useState(0)
  const [showReportModal, setShowReportModal] = useState(false)
  const [showComparison, setShowComparison] = useState(false)
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') || 'dark'
    }
    return 'dark'
  })
  const [analysisClientId, setAnalysisClientId] = useState<string | null>(null)

  const { progress, isConnected, error: wsError } = useAnalysisWebSocket(analysisClientId)
  const {
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
  } = useDemoMode()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }, [])

  useEffect(() => {
    const sectorData = get_all_features()
    setFeatures(sectorData)
  }, [selectedSector])

  // Sync demo sector with selected sector
  useEffect(() => {
    if (demoMode && demoSector !== selectedSector) {
      setSelectedSector(demoSector)
    }
  }, [demoMode, demoSector, selectedSector])

  const handleSectorChange = useCallback((sectorId) => {
    setSelectedSector(sectorId)
    if (demoMode) setDemoSector(sectorId)
    const sectorData = MOCK_SECTORS[sectorId]
    if (sectorData) {
      setFeatures(sectorData.feature_collection.features)
      setSelectedFeature(null)
      setMapKey(k => k + 1)
    }
  }, [demoMode, setDemoSector])

  const handleConfidenceChange = useCallback((threshold) => {
    setConfidenceThreshold(threshold)
  }, [])

  const handleExport = useCallback(() => {
    const filtered = filter_features_by_confidence(features, confidenceThreshold)
    const geojson = {
      type: 'FeatureCollection',
      features: filtered,
      metadata: {
        generated: new Date().toISOString(),
        confidenceThreshold,
        sector: selectedSector,
        totalFeatures: filtered.length
      }
    }
    const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `skydump-report-${selectedSector}-${Date.now()}.geojson`
    a.click()
    URL.revokeObjectURL(url)
  }, [features, confidenceThreshold, selectedSector])

  const handleRefresh = useCallback(async () => {
    setIsLoading(true)
    setAnalysisClientId(`analysis_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)
    await new Promise(r => setTimeout(r, 1000))
    setIsLoading(false)
  }, [])

  const handleFeatureSelect = useCallback((feature) => {
    setSelectedFeature(feature)
  }, [])

  const handleReportClick = useCallback(() => {
    setShowReportModal(true)
  }, [])

  const handleComparisonClick = useCallback(() => {
    setShowComparison(true)
  }, [])

  const handleComparisonClose = useCallback(() => {
    setShowComparison(false)
  }, [])

  const handleReportClose = useCallback(() => {
    setShowReportModal(false)
  }, [])

  const handleReportSubmit = useCallback((result) => {
    console.log('Citizen report submitted:', result)
    setShowReportModal(false)
  }, [])

  const filteredFeatures = filter_features_by_confidence(features, confidenceThreshold)
  const sectorInfo = MOCK_SECTORS[selectedSector]
  const sectorCenter = sectorInfo?.metadata?.center || [0, 0]
  const sectorName = sectorInfo?.metadata?.name || 'Unknown Sector'

return (
    <div className="h-screen w-screen overflow-hidden">
      <Header
        selectedSector={selectedSector}
        onSectorChange={handleSectorChange}
        confidenceThreshold={confidenceThreshold}
        onConfidenceChange={handleConfidenceChange}
        onExport={handleExport}
        onRefresh={handleRefresh}
        isLoading={isLoading}
        onReportClick={handleReportClick}
        onComparisonClick={handleComparisonClick}
        theme={theme}
        onThemeToggle={toggleTheme}
        demoMode={demoMode}
        demoNarrative={demoNarrative}
        demoStep={demoStep}
        nextStep={nextStep}
        prevStep={prevStep}
        skipDemo={skipDemo}
        DEMO_SECTORS={DEMO_SECTORS}
      />

      <main className="h-full w-full relative">
        {/* Live Analysis Progress Overlay */}
        {progress && (
          <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 w-full max-w-md px-4 pointer-events-none">
            <div className="bg-slate-900/95 backdrop-blur-sm border border-slate-700 rounded-xl shadow-2xl p-4 animate-slide-down">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
                  <span className="font-semibold text-slate-100">Live Analysis</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                  <span className="text-xs text-slate-400">{isConnected ? 'Live' : 'Disconnected'}</span>
                </div>
              </div>
              
              <div className="space-y-2">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-300">{progress.stage}</span>
                    <span className="font-mono text-emerald-400">{progress.progress}%</span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-emerald-500 transition-all duration-300 ease-out"
                      style={{ width: `${progress.progress}%` }}
                    />
                  </div>
                </div>
                
                <p className="text-sm text-slate-300 truncate">{progress.message}</p>
                
                {wsError && (
                  <p className="text-xs text-red-400 mt-2">{wsError}</p>
                )}
              </div>
            </div>
          </div>
        )}
        
        <Suspense fallback={<div className="absolute inset-0 flex items-center justify-center bg-slate-900/50"><div className="animate-spin rounded-full h-12 w-12 border-4 border-emerald-500 border-t-transparent" /></div>}>
          <MapView
            key={mapKey}
            features={filteredFeatures}
            selectedFeature={selectedFeature}
            onFeatureSelect={handleFeatureSelect}
            sectorCenter={MOCK_SECTORS[selectedSector]?.metadata?.center || [0, 0]}
          />
        </Suspense>

        <Sidebar
          features={features}
          confidenceThreshold={confidenceThreshold}
          onExport={handleExport}
          selectedFeature={selectedFeature}
          onFeatureSelect={handleFeatureSelect}
        />

        <RightPanel selectedFeature={selectedFeature} />

        <Suspense fallback={<div className="fixed bottom-4 right-4 w-80 md:w-96 z-20 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-2 border-emerald-500 border-t-transparent" /></div>}>
          <AnalyticsPanel features={filteredFeatures} className="fixed bottom-4 right-4 w-80 md:w-96 z-20" />
        </Suspense>
      </main>

      {showReportModal && (
        <Suspense fallback={<div className="fixed inset-0 flex items-center justify-center bg-black/80"><div className="animate-spin rounded-full h-12 w-12 border-4 border-emerald-500 border-t-transparent" /></div>}>
          <CitizenReport
            onClose={handleReportClose}
            onSubmit={handleReportSubmit}
          />
        </Suspense>
      )}

      {showComparison && (
        <Suspense fallback={<div className="fixed inset-0 flex items-center justify-center bg-black/80"><div className="animate-spin rounded-full h-12 w-12 border-4 border-emerald-500 border-t-transparent" /></div>}>
          <ComparisonSlider
            features={filteredFeatures}
            selectedFeature={selectedFeature}
            onFeatureSelect={handleFeatureSelect}
            sectorCenter={sectorCenter}
            sectorName={sectorName}
            onClose={handleComparisonClose}
          />
        </Suspense>
      )}

      <OfflineIndicator />
    </div>
  )
}

export default App