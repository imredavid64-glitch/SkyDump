import { useState, useCallback, useEffect } from 'react'
import { MapView } from './components/MapView'
import { AnomalyList } from './components/AnomalyList'
import { AnalyticsPanel } from './components/AnalyticsPanel'
import { SpectralViewer } from './components/SpectralViewer'
import { Satellite, AlertTriangle, Layers, Download, Settings, RefreshCw, MapPin, Zap } from 'lucide-react'
import { get_all_features, filter_features_by_confidence, calculate_summary_stats, MOCK_SECTORS } from './data/mockDumpsites'

function Header({ selectedSector, onSectorChange, confidenceThreshold, onConfidenceChange, onExport, onRefresh, isLoading }) {
  const sectors = Object.entries(MOCK_SECTORS).map(([id, data]) => ({
    id,
    name: data.metadata.name,
    center: data.metadata.center
  }))

  return (
    <header className="fixed top-0 left-0 right-0 z-40 bg-slate-950/95 backdrop-blur-md border-b border-slate-800">
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
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-850/50 rounded-lg border border-slate-800">
            <MapPin className="w-4 h-4 text-slate-400" />
            <select
              value={selectedSector}
              onChange={(e) => onSectorChange(e.target.value)}
              className="bg-transparent text-slate-100 text-sm focus:outline-none cursor-pointer appearance-none"
            >
              {sectors.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-850/50 rounded-lg border border-slate-800 hidden sm:flex">
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
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-850/50 rounded-lg border border-slate-800 hidden md:flex">
            <span className="relative flex items-center gap-1.5">
              <span className="status-dot connected" />
              <span className="text-xs text-slate-300">Live Satellite</span>
            </span>
          </div>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="btn-secondary flex items-center gap-2"
            title="Refresh Data"
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

      <div className="px-4 pb-3 sm:hidden">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-850/50 rounded-lg border border-slate-800">
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

  useEffect(() => {
    const sectorData = get_all_features()
    setFeatures(sectorData)
  }, [selectedSector])

  const handleSectorChange = useCallback((sectorId) => {
    setSelectedSector(sectorId)
    const sectorData = MOCK_SECTORS[sectorId]
    if (sectorData) {
      setFeatures(sectorData.feature_collection.features)
      setSelectedFeature(null)
      setMapKey(k => k + 1)
    }
  }, [])

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
    await new Promise(r => setTimeout(r, 1000))
    setIsLoading(false)
  }, [])

  const handleFeatureSelect = useCallback((feature) => {
    setSelectedFeature(feature)
  }, [])

  const filteredFeatures = filter_features_by_confidence(features, confidenceThreshold)

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
      />

      <main className="h-full w-full relative">
        <MapView
          key={mapKey}
          features={filteredFeatures}
          selectedFeature={selectedFeature}
          onFeatureSelect={handleFeatureSelect}
          sectorCenter={MOCK_SECTORS[selectedSector]?.metadata?.center || [0, 0]}
        />

        <Sidebar
          features={features}
          confidenceThreshold={confidenceThreshold}
          onExport={handleExport}
          selectedFeature={selectedFeature}
          onFeatureSelect={handleFeatureSelect}
        />

        <RightPanel selectedFeature={selectedFeature} />

        <AnalyticsPanel features={filteredFeatures} className="fixed bottom-4 right-4 w-80 md:w-96 z-20" />
      </main>
    </div>
  )
}

export default App