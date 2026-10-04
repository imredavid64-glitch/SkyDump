import { useState, useRef, useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-side-by-side'
import { Maximize, Minimize, RotateCcw, Info } from 'lucide-react'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const LAYER_CONFIGS = {
  'Satellite (Before)': {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri'
  },
  'Satellite (After)': {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri'
  },
  'NDVI (Before)': {
    url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png',
    attribution: '© EOX / Sentinel-2',
    opacity: 0.7
  },
  'NDVI (After)': {
    url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png',
    attribution: '© EOX / Sentinel-2',
    opacity: 0.7
  },
  'False Color NIR (Before)': {
    url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png',
    attribution: '© EOX / Sentinel-2',
    opacity: 0.6
  },
  'False Color NIR (After)': {
    url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png',
    attribution: '© EOX / Sentinel-2',
    opacity: 0.6
  }
}

const COMPARISON_PAIRS = [
  { id: 'satellite', left: 'Satellite (Before)', right: 'Satellite (After)', label: 'Optical Imagery' },
  { id: 'ndvi', left: 'NDVI (Before)', right: 'NDVI (After)', label: 'Vegetation Health (NDVI)' },
  { id: 'nir', left: 'False Color NIR (Before)', right: 'False Color NIR (After)', label: 'Near-Infrared False Color' }
]

function SideBySideControl({ leftLayer, rightLayer }) {
  const map = useMap()
  useEffect(() => {
    if (!map || !leftLayer || !rightLayer) return
    const control = L.control.sideBySide(leftLayer, rightLayer)
    control.addTo(map)
    return () => control.remove()
  }, [map, leftLayer, rightLayer])
  return null
}

function ComparisonMap({ leftLayer, rightLayer, center, zoom, features, selectedFeature, onFeatureSelect }) {
  const leftLayerRef = useRef(null)
  const rightLayerRef = useRef(null)

  useEffect(() => {
    leftLayerRef.current = L.tileLayer(leftLayer.url, {
      attribution: leftLayer.attribution,
      opacity: leftLayer.opacity || 1,
      maxZoom: 19
    })
    rightLayerRef.current = L.tileLayer(rightLayer.url, {
      attribution: rightLayer.attribution,
      opacity: rightLayer.opacity || 1,
      maxZoom: 19
    })
  }, [leftLayer, rightLayer])

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom={true}
      className="h-full w-full"
      preferCanvas={true}
    >
      <SideBySideControl
        leftLayer={leftLayerRef.current}
        rightLayer={rightLayerRef.current}
      />
      <TileLayer
        url={leftLayer.url}
        attribution={leftLayer.attribution}
        opacity={leftLayer.opacity || 1}
        maxZoom={19}
      />
      {features.length > 0 && (
        <GeoJSONLayer
          features={features}
          selectedFeature={selectedFeature}
          onFeatureSelect={onFeatureSelect}
        />
      )}
    </MapContainer>
  )
}

function GeoJSONLayer({ features, selectedFeature, onFeatureSelect }) {
  const geojsonRef = useRef(null)
  const ThreatColors = {
    Critical: '#ef4444', High: '#f59e0b', Moderate: '#10b981', Low: '#64748b'
  }

  const getStyle = (feature) => {
    const threat = feature.properties.threat_level
    const color = ThreatColors[threat] || ThreatColors.Low
    const isSelected = selectedFeature?.properties?.id === feature.properties.id
    return {
      fillColor: color,
      weight: isSelected ? 3 : 2,
      opacity: isSelected ? 1 : 0.9,
      color: isSelected ? '#ffffff' : color,
      fillOpacity: isSelected ? 0.4 : 0.25,
      dashArray: isSelected ? '' : '5,5'
    }
  }

  return (
    <L.GeoJSON
      ref={geojsonRef}
      data={{ type: 'FeatureCollection', features }}
      style={getStyle}
      onEachFeature={(feature, layer) => {
        layer.on({
          click: (e) => {
            e.stopPropagation()
            onFeatureSelect(e.target.feature)
          }
        })
      }}
      pointToLayer={(feature, latlng) => {
        const threat = feature.properties.threat_level
        const color = ThreatColors[threat] || ThreatColors.Low
        return L.circleMarker(latlng, {
          radius: 8, fillColor: color, color: '#ffffff', weight: 2, opacity: 1, fillOpacity: 0.8
        })
      }}
    />
  )
}

export function ComparisonSlider({
  features,
  selectedFeature,
  onFeatureSelect,
  sectorCenter,
  sectorName,
  onClose
}) {
  const [pairIndex, setPairIndex] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showLegend, setShowLegend] = useState(true)

  const currentPair = COMPARISON_PAIRS[pairIndex]
  const leftConfig = LAYER_CONFIGS[currentPair.left]
  const rightConfig = LAYER_CONFIGS[currentPair.right]

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'ArrowRight') setPairIndex(p => (p + 1) % COMPARISON_PAIRS.length)
    if (e.key === 'ArrowLeft') setPairIndex(p => (p - 1 + COMPARISON_PAIRS.length) % COMPARISON_PAIRS.length)
    if (e.key === 'Escape') onClose?.()
    if (e.key === 'f' || e.key === 'F') setIsFullscreen(p => !p)
  }, [onClose])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const threatCounts = features.reduce((acc, f) => {
    acc[f.properties.threat_level] = (acc[f.properties.threat_level] || 0) + 1
    return acc
  }, {})

  return (
    <div className={`fixed inset-0 z-50 bg-slate-950 flex flex-col ${isFullscreen ? 'fullscreen' : ''}`}>
      <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-10 pointer-events-none">
        <div className="flex items-center gap-3 pointer-events-auto">
          <button
            onClick={onClose}
            className="btn-secondary p-2 rounded-xl"
            title="Close Comparison (Esc)"
          >
            <RotateCcw className="w-5 h-5" />
          </button>
          <div className="bg-slate-900/90 backdrop-blur px-4 py-2 rounded-xl border border-slate-700">
            <h2 className="font-semibold text-slate-100">{sectorName}</h2>
            <p className="text-xs text-slate-400">{currentPair.label}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 pointer-events-auto">
          <button
            onClick={() => setShowLegend(!showLegend)}
            className="btn-secondary p-2 rounded-xl"
            title="Toggle Legend"
          >
            <Info className="w-5 h-5" />
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="btn-secondary p-2 rounded-xl"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen (F)'}
          >
            {isFullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
          </button>
        </div>
      </div>

      <div className="flex-1 relative">
        <ComparisonMap
          leftLayer={leftConfig}
          rightLayer={rightConfig}
          center={sectorCenter}
          zoom={12}
          features={features}
          selectedFeature={selectedFeature}
          onFeatureSelect={onFeatureSelect}
        />
      </div>

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-4 pointer-events-auto z-10">
        <button
          onClick={() => setPairIndex(p => (p - 1 + COMPARISON_PAIRS.length) % COMPARISON_PAIRS.length)}
          className="btn-secondary p-3 rounded-xl"
          title="Previous Comparison (←)"
        >
          <RotateCcw className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 bg-slate-900/90 backdrop-blur px-4 py-2 rounded-xl border border-slate-700">
          {COMPARISON_PAIRS.map((pair, i) => (
            <button
              key={pair.id}
              onClick={() => setPairIndex(i)}
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                i === pairIndex
                  ? 'bg-emerald-500 text-slate-950 shadow-lg shadow-emerald-500/25'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'
              }`}
            >
              {pair.label.split(' ')[0]}
            </button>
          ))}
        </div>

        <button
          onClick={() => setPairIndex(p => (p + 1) % COMPARISON_PAIRS.length)}
          className="btn-secondary p-3 rounded-xl"
          title="Next Comparison (→)"
        >
          <RotateCcw className="w-5 h-5 transform rotate-180" />
        </button>
      </div>

      {showLegend && (
        <div className="absolute bottom-4 right-4 pointer-events-auto z-10">
          <div className="bg-slate-900/95 backdrop-blur p-4 rounded-xl border border-slate-700 min-w-[200px]">
            <h3 className="font-semibold text-slate-100 mb-3 flex items-center gap-2">
              <span className="w-3 h-3 rounded bg-gradient-to-r from-red-500 via-amber-500 to-emerald-500" />
              Threat Levels
            </h3>
            <div className="space-y-2">
              {Object.entries(threatCounts).map(([level, count]) => (
                <div key={level} className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded" style={{ backgroundColor: ThreatColors[level] || ThreatColors.Low }} />
                    <span className="text-slate-300 capitalize">{level}</span>
                  </span>
                  <span className="font-mono text-slate-100">{count} sites</span>
                </div>
              ))}
              {Object.keys(threatCounts).length === 0 && (
                <p className="text-slate-500 text-sm">No detections at current threshold</p>
              )}
            </div>
            <div className="mt-3 pt-3 border-t border-slate-800 text-xs text-slate-500">
              <p>← → Navigate | F Fullscreen | Esc Close</p>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .fullscreen { position: fixed; top: 0; left: 0; right: 0; bottom: 0; }
      `}</style>
    </div>
  )
}

export default ComparisonSlider