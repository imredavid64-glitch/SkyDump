import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [
      react(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg'],
        manifest: {
          name: 'SkyDump AI',
          short_name: 'SkyDump',
          description: 'Satellite waste dumping detection and monitoring',
          theme_color: '#020617',
          background_color: '#020617',
          display: 'standalone',
          orientation: 'portrait-primary',
          scope: '/',
          start_url: '/',
          icons: [
            {
              src: '/pwa-192.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any maskable'
            },
            {
              src: '/pwa-512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any maskable'
            }
          ],
          categories: ['utilities', 'science', 'education'],
          screenshots: [],
          shortcuts: [
            {
              name: 'Live Map',
              short_name: 'Map',
              description: 'View live satellite monitoring map',
              url: '/#map',
              icons: [{ src: '/pwa-192.png', sizes: '192x192' }]
            },
            {
              name: 'Report Dumping',
              short_name: 'Report',
              description: 'Report suspected illegal dumping',
              url: '/#report',
              icons: [{ src: '/pwa-192.png', sizes: '192x192' }]
            }
          ]
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2,geojson,json}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/tiles\.maps\.eox\.at\/.*/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'satellite-tiles',
                expiration: {
                  maxEntries: 1000,
                  maxAgeSeconds: 60 * 60 * 24 * 30
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /^https:\/\/server\.arcgisonline\.com\/.*/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'esri-satellite-tiles',
                expiration: {
                  maxEntries: 1000,
                  maxAgeSeconds: 60 * 60 * 24 * 30
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /^https:\/\/cartodb-basemaps-.*/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'cartodb-tiles',
                expiration: {
                  maxEntries: 500,
                  maxAgeSeconds: 60 * 60 * 24 * 30
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /^https:\/\/.*\.tile\.openstreetmap\.org\/.*/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'osm-tiles',
                expiration: {
                  maxEntries: 500,
                  maxAgeSeconds: 60 * 60 * 24 * 30
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /^https:\/\/api\.skydump\.ai\/.*/,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'api-cache',
                expiration: {
                  maxEntries: 200,
                  maxAgeSeconds: 60 * 60 * 24
                },
                networkTimeoutSeconds: 10
              }
            },
            {
              urlPattern: /^http:\/\/localhost:8000\/api\/.*/,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'local-api-cache',
                expiration: {
                  maxEntries: 200,
                  maxAgeSeconds: 60 * 60 * 24
                },
                networkTimeoutSeconds: 10
              }
            },
            {
              urlPattern: /^https:\/\/unpkg\.com\/.*/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'cdn-assets',
                expiration: {
                  maxEntries: 100,
                  maxAgeSeconds: 60 * 60 * 24 * 365
                },
                cacheableResponse: { statuses: [0, 200] }
              }
            }
          ],
          navigateFallback: '/index.html',
          navigateFallbackAllowlist: [/^\/$/],
          cleanupOutdatedCaches: true,
          skipWaiting: true,
          clientsClaim: true
        }
      })
    ],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor': ['react', 'react-dom', 'axios', 'html2canvas', 'jspdf'],
            'leaflet': ['leaflet', 'react-leaflet'],
            'charts': ['recharts'],
          }
        }
      }
    },
    define: {
      'process.env': env
    }
  }
})