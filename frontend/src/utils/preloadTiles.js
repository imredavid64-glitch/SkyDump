// Preload utility for offline map caching
// Run this in browser console or as a script to pre-cache map tiles for sectors

const SECTORS = {
  'sector-7': { 
    name: 'Rotterdam Industrial Zone', 
    bbox: [4.2, 51.85, 4.5, 51.95],
    center: [4.35, 51.9],
    zoom: 12
  },
  'sector-12': { 
    name: 'Amazon River Basin', 
    bbox: [-55.5, -3.5, -55.0, -3.0],
    center: [-55.25, -3.25],
    zoom: 12
  },
  'sector-4': { 
    name: 'Congo Basin Forest Reserve', 
    bbox: [18.5, -1.5, 19.0, -1.0],
    center: [18.75, -1.25],
    zoom: 12
  }
}

const TILE_SERVERS = {
  satellite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  osm: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  ndvi: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/{z}/{x}/{y}.png',
  cartodb: 'https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png'
}

function bboxToTileRange(bbox, zoom) {
  // Convert bbox [minLon, minLat, maxLon, maxLat] to tile coordinates
  const [minLon, minLat, maxLon, maxLat] = bbox
  
  function lon2tile(lon, zoom) {
    return Math.floor((lon + 180) / 360 * Math.pow(2, zoom))
  }
  
  function lat2tile(lat, zoom) {
    return Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom))
  }
  
  const minX = lon2tile(minLon, zoom)
  const maxX = lon2tile(maxLon, zoom)
  const minY = lat2tile(maxLat, zoom) // Note: maxLat -> minY (inverted)
  const maxY = lat2tile(minLat, zoom)
  
  return { minX, maxX, minY, maxY }
}

async function preloadTilesForSector(sectorId, zoomLevels = [10, 11, 12, 13, 14]) {
  const sector = SECTORS[sectorId]
  if (!sector) throw new Error(`Unknown sector: ${sectorId}`)
  
  console.log(`Preloading tiles for ${sector.name}...`)
  
  const cacheNames = {
    satellite: 'esri-satellite-tiles',
    osm: 'osm-tiles',
    ndvi: 'satellite-tiles',
    cartodb: 'cartodb-tiles'
  }
  
  let totalTiles = 0
  
  for (const zoom of zoomLevels) {
    const { minX, maxX, minY, maxY } = bboxToTileRange(sector.bbox, zoom)
    const tilesInZoom = (maxX - minX + 1) * (maxY - minY + 1)
    totalTiles += tilesInZoom * Object.keys(TILE_SERVERS).length
    
    console.log(`  Zoom ${zoom}: ${tilesInZoom} tiles per layer`)
    
    // Preload each tile layer
    for (const [layerName, template] of Object.entries(TILE_SERVERS)) {
      const cache = await caches.open(cacheNames[layerName] || `tiles-${layerName}`)
      
      for (let x = minX; x <= maxX; x++) {
        for (let y = minY; y <= maxY; y++) {
          let url
          if (layerName === 'osm') {
            url = template.replace('{s}', ['a', 'b', 'c'][Math.floor(Math.random() * 3)])
              .replace('{z}', zoom).replace('{x}', x).replace('{y}', y)
          } else if (layerName === 'cartodb') {
            url = template.replace('{s}', ['a', 'b', 'c', 'd'][Math.floor(Math.random() * 4)])
              .replace('{z}', zoom).replace('{x}', x).replace('{y}', y).replace('{r}', '@2x')
          } else {
            url = template.replace('{z}', zoom).replace('{x}', x).replace('{y}', y)
          }
          
          try {
            const response = await fetch(url, { mode: 'cors', credentials: 'omit' })
            if (response.ok) {
              await cache.put(url, response.clone())
            }
          } catch (e) {
            // Silently fail for individual tiles
          }
        }
      }
    }
  }
  
  console.log(`Preload complete for ${sector.name}. Estimated ${totalTiles} tiles cached.`)
  return totalTiles
}

async function preloadAllSectors() {
  console.log('Starting preload for all sectors...')
  let total = 0
  for (const sectorId of Object.keys(SECTORS)) {
    try {
      total += await preloadTilesForSector(sectorId)
    } catch (e) {
      console.error(`Failed to preload ${sectorId}:`, e)
    }
  }
  console.log(`All sectors preloaded. Total tiles: ${total}`)
  return total
}

async function preloadAPICache() {
  console.log('Preloading API data...')
  const cache = await caches.open('api-cache')
  
  const endpoints = [
    '/api/mock-sites?sector=sector-7',
    '/api/mock-sites?sector=sector-12',
    '/api/mock-sites?sector=sector-4',
    '/api/sectors',
    '/api/precomputed',
    '/api/precomputed/sector-7',
    '/api/precomputed/sector-12',
    '/api/precomputed/sector-4'
  ]
  
  const baseUrl = window.location.origin.includes('localhost') ? 'http://localhost:8000' : 'https://api.skydump.ai'
  
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(`${baseUrl}${endpoint}`)
      if (response.ok) {
        await cache.put(`${baseUrl}${endpoint}`, response.clone())
        console.log(`  Cached: ${endpoint}`)
      }
    } catch (e) {
      console.warn(`Failed to cache ${endpoint}:`, e)
    }
  }
  
  console.log('API cache preload complete')
}

// Export for use in browser console
if (typeof window !== 'undefined') {
  window.SkyDumpPreload = {
    preloadTilesForSector,
    preloadAllSectors,
    preloadAPICache,
    SECTORS
  }
  console.log('SkyDumpPreload available. Run SkyDumpPreload.preloadAllSectors() to cache all sectors for offline use.')
}

// Also export for module usage
export { preloadTilesForSector, preloadAllSectors, preloadAPICache, SECTORS }