import { useEffect, useRef, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, LayersControl, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapPin, Eye, EyeOff, Layers } from 'lucide-react'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const ThreatColors = {
  Critical: '#ef4444',
  High: '#f59e0b',
  Moderate: '#10b981',
  Low: '#64748b'
}

const ThreatColorDark = {
  Critical: '#7f1d1d',
  High: '#78350f',
  Moderate: '#064e3b',
  Low: '#1e293b'
}

function LayerSwitcher({ baseLayer, overlayLayers, onBaseLayerChange, onOverlayChange }) {
  return (
    <div className="layer-control absolute top-4 right-4 z-10">
      <LayersControl.BaseLayer>
        {Object.entries(baseLayer).map(([name, layer]) => (
          <label key={name} className="flex items-center gap-2 mb-1">
            <input
              type="radio"
              name="base-layer"
              checked={name === 'Satellite'}
              onChange={() => onBaseLayerChange(name)}
              className="w-4 h-4 accent-emerald-500"
            />
            <span className="text-sm text-slate-300">{name}</span>
          </label>
        ))}
      </LayersControl.BaseLayer>
      <LayersControl.Overlay>
        {Object.entries(overlayLayers).map(([name, layer]) => (
          <label key={name} className="flex items-center gap-2 mb-1">
            <input
              type="checkbox"
              checked={layer.visible}
              onChange={(e) => onOverlayChange(name, e.target.checked)}
              className="w-4 h-4 accent-emerald-500"
            />
            <span className="text-sm text-slate-300">{name}</span>
          </label>
        ))}
      </LayersControl.Overlay>
    </div>
  )
}

function FeaturePopup({ feature, selectedFeature, onSelect }) {
  const props = feature.properties
  const threatColor = ThreatColors[props.threat_level] || ThreatColors.Low
  const isSelected = selectedFeature?.properties?.id === props.id

  return (
    <div className={`custom-popup ${isSelected ? 'ring-2 ring-emerald-500' : ''}`}>
      <div className="p-3 min-w-[260px]">
        <div className="flex items-start justify-between mb-2">
          <div>
            <span className="font-mono text-xs text-emerald-400 mr-2">{props.id}</span>
            <span className={`threat-badge threat-${props.threat_level.toLowerCase()}`}>
              {props.threat_level}
            </span>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onSelect(feature); }}
            className="p-1 text-slate-400 hover:text-emerald-400 transition-colors"
            title="View details"
          >
            <MapPin className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs mb-2">
          <div>
            <span className="text-slate-500">Area:</span>
            <span className="font-mono text-slate-100 ml-1">{props.area_m2.toLocaleString()} m²</span>
          </div>
          <div>
            <span className="text-slate-500">Tonnage:</span>
            <span className="font-mono text-slate-100 ml-1">{props.estimated_tonnage.toFixed(1)} t</span>
          </div>
          <div>
            <span className="text-slate-500">Confidence:</span>
            <span className="font-mono text-emerald-400 ml-1">{(props.confidence * 100).toFixed(1)}%</span>
          </div>
          <div>
            <span className="text-slate-500">Risk:</span>
            <span className="font-mono text-amber-400 ml-1">{props.risk_score}/100</span>
          </div>
        </div>
        <div className="text-xs text-slate-500 font-mono">
          {props.centroid[1].toFixed(5)}, {props.centroid[0].toFixed(5)}
        </div>
      </div>
    </div>
  )
}

function MapLayers({ features, selectedFeature, onFeatureSelect, sectorCenter }) {
  const geojsonRef = useRef(null)
  const styleCache = useMemo(() => new Map(), [])

  const getStyle = (feature) => {
    const threat = feature.properties.threat_level
    const color = ThreatColors[threat] || ThreatColors.Low
    const isSelected = selectedFeature?.properties?.id === feature.properties.id
    
    const cacheKey = `${threat}-${isSelected}`
    if (styleCache.has(cacheKey)) return styleCache.get(cacheKey)
    
    const style = {
      fillColor: color,
      weight: isSelected ? 3 : 2,
      opacity: isSelected ? 1 : 0.9,
      color: isSelected ? '#ffffff' : color,
      fillOpacity: isSelected ? 0.4 : 0.25,
      dashArray: isSelected ? '' : '5,5'
    }
    styleCache.set(cacheKey, style)
    return style
  }

  const highlightStyle = {
    weight: 3,
    color: '#ffffff',
    fillOpacity: 0.4
  }

  return (
    <GeoJSON
      ref={geojsonRef}
      data={{ type: 'FeatureCollection', features }}
      style={getStyle}
      onEachFeature={(feature, layer) => {
        layer.on({
          mouseover: (e) => {
            if (e.target.feature.properties.id !== selectedFeature?.properties?.id) {
              e.target.setStyle(highlightStyle)
              e.target.bringToFront()
            }
          },
          mouseout: (e) => {
            if (e.target.feature.properties.id !== selectedFeature?.properties?.id) {
              geojsonRef.current?.resetStyle(e.target)
            }
          },
          click: (e) => {
            e.stopPropagation()
            onFeatureSelect(e.target.feature)
          }
        })
        layer.bindPopup(
          <FeaturePopup
            feature={e.target.feature}
            selectedFeature={selectedFeature}
            onSelect={onFeatureSelect}
          />
        )
      }}
      pointToLayer={(feature, latlng) => {
        const threat = feature.properties.threat_level
        const color = ThreatColors[threat] || ThreatColors.Low
        return L.circleMarker(latlng, {
          radius: 8,
          fillColor: color,
          color: '#ffffff',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.8
        })
      }}
    />
  )
}

function MapAttribution() {
  const map = useMap()
  useEffect(() => {
    map.attributionControl.setPrefix('')
    map.attributionControl.addAttribution(
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | ' +
      '© <a href="https://www.esri.com">Esri</a> | ' +
      'Sentinel-2 data: <a href="https://planetarycomputer.microsoft.com">Microsoft Planetary Computer</a>'
    )
  }, [map])
  return null
}

export function MapView({ features, selectedFeature, onFeatureSelect, sectorCenter }) {
  const [baseLayer, setBaseLayer] = useState('Satellite')
  const [overlayVisibility, setOverlayVisibility] = useState({
    'NDVI Stress Index': true,
    'NIR False Color': false,
    'Detected Waste Sites': true
  })

  const baseLayers = useMemo(() => ({
    'OpenStreetMap': (
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution=""
        maxZoom={19}
      />
    ),
    'Satellite': (
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attribution=""
        maxZoom={19}
      />
    ),
    'Dark Matter': (
      <TileLayer
        url="https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png"
        attribution=""
        maxZoom={19}
      />
    )
  }), [])

  const overlayLayers = useMemo(() => ({
    'Detected Waste Sites': {
      visible: overlayVisibility['Detected Waste Sites'],
      layer: (
        <MapLayers
          features={features}
          selectedFeature={selectedFeature}
          onFeatureSelect={onFeatureSelect}
          sectorCenter={sectorCenter}
        />
      )
    },
    'NDVI Stress Index': {
      visible: overlayVisibility['NDVI Stress Index'],
      layer: (
        <TileLayer
          url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png"
          attribution=""
          opacity={0.6}
          maxZoom={14}
        />
      )
    },
    'NIR False Color': {
      visible: overlayVisibility['NIR False Color'],
      layer: (
        <TileLayer
          url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png"
          attribution=""
          opacity={0.5}
          maxZoom={14}
        />
      )
    }
  }), [features, selectedFeature, onFeatureSelect, sectorCenter, overlayVisibility])

  const handleBaseLayerChange = (name) => setBaseLayer(name)
  const handleOverlayChange = (name, visible) => {
    setOverlayVisibility(prev => ({ ...prev, [name]: visible }))
  }

  return (
    <MapContainer
      center={sectorCenter}
      zoom={12}
      scrollWheelZoom={true}
      className="h-full w-full"
      preferCanvas={true}
    >
      <TileLayer
        url={baseLayer === 'OpenStreetMap' 
          ? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          : baseLayer === 'Satellite'
            ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            : "https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png"
        }
        attribution=""
        maxZoom={19}
      />
      
      {overlayVisibility['NDVI Stress Index'] && (
        <TileLayer
          url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png"
          attribution=""
          opacity={0.5}
          maxZoom={14}
        />
      )}
      
      {overlayVisibility['NIR False Color'] && (
        <TileLayer
          url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png"
          attribution=""
          opacity={0.4}
          maxZoom={14}
        />
      )}

      <MapLayers
        features={features}
        selectedFeature={selectedFeature}
        onFeatureSelect={onFeatureSelect}
        sectorCenter={sectorCenter}
      />

      <MapAttribution />
      
      <div className="absolute bottom-4 left-4 z-10">
        <LayersControl position="bottomleft">
          <LayersControl.BaseLayer checked={baseLayer === 'OpenStreetMap'}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="" />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer checked={baseLayer === 'Satellite'}>
            <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" attribution="" />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer checked={baseLayer === 'Dark Matter'}>
            <TileLayer url="https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png" attribution="" />
          </LayersControl.BaseLayer>
          
          <LayersControl.Overlay checked={overlayVisibility['Detected Waste Sites']}>
            <MapLayers
              features={features}
              selectedFeature={selectedFeature}
              onFeatureSelect={onFeatureSelect}
              sectorCenter={sectorCenter}
            />
          </LayersControl.Overlay>
          <LayersControl.Overlay checked={overlayVisibility['NDVI Stress Index']}>
            <TileLayer url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png" opacity={0.5} maxZoom={14} attribution="" />
          </LayersControl.Overlay>
          <LayersControl.Overlay checked={overlayVisibility['NIR False Color']}>
            <TileLayer url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png" opacity={0.4} maxZoom={14} attribution="" />
          </LayersControl.Overlay>
        </LayersControl>
      </div>
    </MapContainer>
  )
}

import { useState, useMemo } from 'react'