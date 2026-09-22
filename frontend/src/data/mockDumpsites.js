import { create_polygon_features } from './createPolygons'

const SECTORS = {
  'sector-7': {
    name: 'Sector 7 - Rotterdam Industrial Zone',
    bbox: [4.2, 51.85, 4.5, 51.95],
    center: [4.35, 51.9],
    zoom: 12,
    prefix: 'RTM',
    count: 7
  },
  'sector-12': {
    name: 'Sector 12 - Amazon River Basin',
    bbox: [-55.5, -3.5, -55.0, -3.0],
    center: [-55.25, -3.25],
    zoom: 12,
    prefix: 'AMZ',
    count: 6
  },
  'sector-4': {
    name: 'Sector 4 - Congo Basin Forest Reserve',
    bbox: [18.5, -1.5, 19.0, -1.0],
    center: [18.75, -1.25],
    zoom: 12,
    prefix: 'CGO',
    count: 8
  }
}

export const MOCK_SECTORS = (() => {
  const result = {}
  for (const [id, config] of Object.entries(SECTORS)) {
    result[id] = {
      metadata: {
        name: config.name,
        bbox: config.bbox,
        center: config.center,
        zoom: config.zoom
      },
      feature_collection: {
        type: 'FeatureCollection',
        features: create_polygon_features(config.center[0], config.center[1], config.count, config.prefix)
      }
    }
  }
  return result
})()

export function get_mock_sectors() {
  return MOCK_SECTORS
}

export function get_sector_data(sector_id) {
  return MOCK_SECTORS[sector_id] || MOCK_SECTORS['sector-7']
}

export function get_all_features() {
  const all = []
  for (const sector of Object.values(MOCK_SECTORS)) {
    all.push(...sector.feature_collection.features)
  }
  return all
}

export function filter_features_by_confidence(features, threshold) {
  return features.filter(f => f.properties.confidence >= threshold)
}

export function calculate_summary_stats(features) {
  if (!features.length) {
    return {
      total_sites: 0,
      total_area_m2: 0,
      total_tonnage: 0,
      by_threat: { Critical: 0, High: 0, Moderate: 0, Low: 0 },
      avg_confidence: 0
    }
  }
  const total_area = features.reduce((sum, f) => sum + f.properties.area_m2, 0)
  const total_tonnage = features.reduce((sum, f) => sum + f.properties.estimated_tonnage, 0)
  const avg_conf = features.reduce((sum, f) => sum + f.properties.confidence, 0) / features.length
  const by_threat = { Critical: 0, High: 0, Moderate: 0, Low: 0 }
  for (const f of features) {
    by_threat[f.properties.threat_level]++
  }
  return {
    total_sites: features.length,
    total_area_m2: Math.round(total_area * 100) / 100,
    total_tonnage: Math.round(total_tonnage * 100) / 100,
    by_threat,
    avg_confidence: Math.round(avg_conf * 1000) / 1000
  }
}

export const mockDumpsites = get_all_features()