import { AlertTriangle, Download, MapPin, Filter } from 'lucide-react'

export function AnomalyList({ features, confidenceThreshold, onExport, selectedFeature, onFeatureSelect }) {
  const filtered = features.filter(f => f.properties.confidence >= confidenceThreshold)
  const summary = {
    total: filtered.length,
    critical: filtered.filter(f => f.properties.threat_level === 'Critical').length,
    high: filtered.filter(f => f.properties.threat_level === 'High').length,
    moderate: filtered.filter(f => f.properties.threat_level === 'Moderate').length,
    low: filtered.filter(f => f.properties.threat_level === 'Low').length,
    totalArea: filtered.reduce((sum, f) => sum + f.properties.area_m2, 0),
    totalTonnage: filtered.reduce((sum, f) => sum + f.properties.estimated_tonnage, 0)
  }

  const threatColors = {
    Critical: 'threat-critical',
    High: 'threat-high',
    Moderate: 'threat-moderate',
    Low: 'threat-low'
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-80 bg-slate-950/95 backdrop-blur-md border-r border-slate-800 overflow-y-auto scrollbar-thin z-30 pt-20 md:pt-16">
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-emerald-500" />
            Detected Sites
          </h2>
          <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
            {filtered.length} / {features.length}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <div className="threat-badge threat-critical">Critical: {summary.critical}</div>
          <div className="threat-badge threat-high">High: {summary.high}</div>
          <div className="threat-badge threat-moderate">Moderate: {summary.moderate}</div>
          <div className="threat-badge threat-low">Low: {summary.low}</div>
        </div>

        <div className="flex items-center gap-2 px-3 py-2 bg-slate-850/50 rounded-lg border border-slate-800">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="text-xs text-slate-300">Confidence ≥</span>
          <input
            type="range"
            min="30"
            max="95"
            value={Math.round(confidenceThreshold * 100)}
            onChange={(e) => {}}
            className="slider flex-1"
            disabled
          />
          <span className="text-xs font-mono text-emerald-400 w-10 text-right">{Math.round(confidenceThreshold * 100)}%</span>
        </div>

        <div className="space-y-2 max-h-[calc(100vh-320px)] overflow-y-auto scrollbar-thin">
          {filtered.length === 0 ? (
            <div className="text-center py-8 text-slate-500">
              <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No sites match current confidence threshold</p>
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
                        <span className={`threat-badge ${threatColors[props.threat_level]}`}>
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

        <div className="pt-4 border-t border-slate-800 text-xs text-slate-500 space-y-1">
          <div className="flex justify-between">
            <span>Total Area</span>
            <span className="font-mono text-slate-300">{summary.totalArea.toLocaleString()} m²</span>
          </div>
          <div className="flex justify-between">
            <span>Est. Tonnage</span>
            <span className="font-mono text-slate-300">{summary.totalTonnage.toFixed(1)} t</span>
          </div>
        </div>
      </div>
    </aside>
  )
}