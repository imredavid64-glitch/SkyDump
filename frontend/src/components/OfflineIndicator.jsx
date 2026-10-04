import { useState, useEffect } from 'react'
import { Wifi, WifiOff, AlertCircle, Download, RefreshCw } from 'lucide-react'

export function OfflineIndicator() {
  const [isOnline, setIsOnline] = useState(true)
  const [cacheStatus, setCacheStatus] = useState('checking')
  const [cachedSectors, setCachedSectors] = useState([])

  useEffect(() => {
    const updateOnlineStatus = () => {
      setIsOnline(navigator.onLine)
    }

    window.addEventListener('online', updateOnlineStatus)
    window.addEventListener('offline', updateOnlineStatus)
    setIsOnline(navigator.onLine)

    checkCacheStatus()

    return () => {
      window.removeEventListener('online', updateOnlineStatus)
      window.removeEventListener('offline', updateOnlineStatus)
    }
  }, [])

  const checkCacheStatus = async () => {
    try {
      if ('caches' in window) {
        const cacheNames = await caches.keys()
        const tileCaches = cacheNames.filter(name => 
          name.includes('tiles') || name.includes('satellite') || name.includes('osm')
        )
        
        let totalTiles = 0
        for (const cacheName of tileCaches) {
          const cache = await caches.open(cacheName)
          const keys = await cache.keys()
          totalTiles += keys.length
        }
        
        // Check for precomputed sector data
        const apiCache = cacheNames.find(name => name.includes('api'))
        let sectors = []
        if (apiCache) {
          const cache = await caches.open(apiCache)
          const keys = await cache.keys()
          sectors = keys
            .filter(req => req.url.includes('/mock-sites') || req.url.includes('/sectors'))
            .map(req => {
              try {
                const url = new URL(req.url)
                return url.searchParams.get('sector')
              } catch { return null }
            })
            .filter(Boolean)
        }
        
        setCachedSectors([...new Set(sectors)])
        setCacheStatus(totalTiles > 0 ? 'ready' : 'empty')
      }
    } catch (e) {
      setCacheStatus('error')
    }
  }

  const handleRefresh = () => {
    window.location.reload()
  }

  if (isOnline && cacheStatus === 'ready') {
    return null // Don't show when online and cached
  }

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-80 z-50 pointer-events-none">
      <div className={`pointer-events-auto animate-slide-up ${!isOnline ? 'bg-amber-900/95 border-amber-700' : 'bg-emerald-900/95 border-emerald-700'} backdrop-blur-sm border rounded-xl p-4 shadow-2xl`}>
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${!isOnline ? 'bg-amber-500/20' : 'bg-emerald-500/20'}`}>
            {!isOnline ? <WifiOff className="w-5 h-5 text-amber-400" /> : <Wifi className="w-5 h-5 text-emerald-400" />}
          </div>
          
          <div className="flex-1 min-w-0">
            {!isOnline ? (
              <>
                <p className="font-semibold text-slate-100">You're Offline</p>
                <p className="text-xs text-slate-400 mt-1">
                  Map tiles and data cached for offline use. Some features may be limited.
                </p>
              </>
            ) : cacheStatus === 'empty' ? (
              <>
                <p className="font-semibold text-slate-100">Building Offline Cache</p>
                <p className="text-xs text-slate-400 mt-1">
                  First visit detected. Map tiles are being cached for offline use.
                </p>
              </>
            ) : (
              <>
                <p className="font-semibold text-slate-100">Ready for Offline Use</p>
                <p className="text-xs text-slate-400 mt-1">
                  {cachedSectors.length > 0 
                    ? `Cached sectors: ${cachedSectors.join(', ')}` 
                    : 'Map tiles and sector data cached locally'}
                </p>
              </>
            )}
            
            {cachedSectors.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {cachedSectors.map(sector => (
                  <span key={sector} className="px-2 py-0.5 text-xs bg-slate-800 rounded text-slate-300 border border-slate-700">
                    {sector}
                  </span>
                ))}
              </div>
            )}
          </div>
          
          <div className="flex items-center gap-2 flex-shrink-0">
            {!isOnline && (
              <button
                onClick={handleRefresh}
                className="btn-secondary p-2 rounded-lg"
                title="Refresh when online"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function NetworkStatusProvider({ children }) {
  const [isOnline, setIsOnline] = useState(true)

  useEffect(() => {
    const updateOnlineStatus = () => setIsOnline(navigator.onLine)
    window.addEventListener('online', updateOnlineStatus)
    window.addEventListener('offline', updateOnlineStatus)
    setIsOnline(navigator.onLine)
    return () => {
      window.removeEventListener('online', updateOnlineStatus)
      window.removeEventListener('offline', updateOnlineStatus)
    }
  }, [])

  return (
    <NetworkStatusContext.Provider value={isOnline}>
      {children}
    </NetworkStatusContext.Provider>
  )
}

import { createContext, useContext } from 'react'

const NetworkStatusContext = createContext(true)

export function useNetworkStatus() {
  return useContext(NetworkStatusContext)
}