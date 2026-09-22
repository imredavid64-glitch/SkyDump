let seed = 42

function random() {
  seed = (seed * 1664525 + 1013904223) % 4294967296
  return seed / 4294967296
}

function cos(angle) {
  return Math.cos(angle)
}

function sin(angle) {
  return Math.sin(angle)
}

export function create_polygon_features(base_lon, base_lat, count, prefix) {
  const features = []
  
  for (let i = 0; i < count; i++) {
    const size = 0.001 + random() * 0.004
    const lon_offset = -0.02 + random() * 0.04
    const lat_offset = -0.02 + random() * 0.04
    
    const center_lon = base_lon + lon_offset
    const center_lat = base_lat + lat_offset
    
    const coords = []
    for (let j = 0; j < 8; j++) {
      const angle = j * (360 / 8) * Math.PI / 180
      const r = size * (0.8 + random() * 0.4)
      coords.push([center_lon + r * cos(angle), center_lat + r * sin(angle)])
    }
    coords.push(coords[0])
    
    const area_m2 = 5000 + random() * 195000
    const confidence = 0.65 + random() * 0.3
    const risk_score = Math.min(100, Math.round((area_m2 / 500000 * 0.4 + confidence * 0.3 + (0.2 + random() * 0.6) * 0.3) * 100))
    
    let threat
    if (risk_score >= 75) threat = 'Critical'
    else if (risk_score >= 50) threat = 'High'
    else if (risk_score >= 25) threat = 'Moderate'
    else threat = 'Low'
    
    features.push({
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [coords]
      },
      properties: {
        id: `${prefix}-${String(i + 1).padStart(3, '0')}`,
        area_m2: Math.round(area_m2 * 100) / 100,
        confidence: Math.round(confidence * 100) / 100,
        risk_score,
        threat_level: threat,
        estimated_tonnage: Math.round(area_m2 * 0.15 * 100) / 100,
        centroid: [center_lon, center_lat],
        detection_date: '2024-12-15',
        sensor: 'Sentinel-2 L2A'
      }
    })
  }
  
  return features
}