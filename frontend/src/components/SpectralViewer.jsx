import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const BAND_COLORS = {
  'B04 (Red)': '#ef4444',
  'B08 (NIR)': '#10b981',
  'B11 (SWIR)': '#f59e0b'
}

const SPECTRAL_BANDS = [
  { name: 'B01 (Coastal)', wavelength: 443, gsd: 60 },
  { name: 'B02 (Blue)', wavelength: 490, gsd: 10 },
  { name: 'B03 (Green)', wavelength: 560, gsd: 10 },
  { name: 'B04 (Red)', wavelength: 665, gsd: 10 },
  { name: 'B05 (Red Edge 1)', wavelength: 704, gsd: 20 },
  { name: 'B06 (Red Edge 2)', wavelength: 740, gsd: 20 },
  { name: 'B07 (Red Edge 3)', wavelength: 783, gsd: 20 },
  { name: 'B08 (NIR)', wavelength: 842, gsd: 10 },
  { name: 'B8A (Red Edge 4)', wavelength: 865, gsd: 20 },
  { name: 'B09 (Water Vapor)', wavelength: 945, gsd: 60 },
  { name: 'B11 (SWIR 1.6)', wavelength: 1610, gsd: 20 },
  { name: 'B12 (SWIR 2.2)', wavelength: 2190, gsd: 20 }
]

function generateSpectralCurve(feature) {
  const baseReflectance = 0.1 + Math.random() * 0.15
  const ndvi = (feature.properties?.confidence || 0.7) * 0.8 - 0.2
  
  return SPECTRAL_BANDS.map((band, i) => {
    let reflectance = baseReflectance
    
    if (band.name.includes('Red') && !band.name.includes('Edge')) {
      reflectance = baseReflectance * (1 - ndvi * 0.5)
    } else if (band.name.includes('NIR') || band.name.includes('Red Edge')) {
      reflectance = baseReflectance * (1 + ndvi * 1.5)
    } else if (band.name.includes('SWIR')) {
      reflectance = baseReflectance * (1 + (feature.properties?.risk_score || 50) / 100 * 0.8)
    } else if (band.name.includes('Green')) {
      reflectance = baseReflectance * 1.2
    } else if (band.name.includes('Blue') || band.name.includes('Coastal')) {
      reflectance = baseReflectance * 0.8
    }
    
    reflectance += (Math.random() - 0.5) * 0.02
    reflectance = Math.max(0, Math.min(1, reflectance))
    
    return {
      band: band.name,
      wavelength: band.wavelength,
      reflectance: Number(reflectance.toFixed(4)),
      gsd: band.gsd
    }
  })
}

export function SpectralViewer({ feature }) {
  const spectralData = generateSpectralCurve(feature)
  const keyBands = spectralData.filter(d => 
    d.band.includes('Red') || d.band.includes('NIR') || d.band.includes('SWIR') || d.band.includes('Green')
  )

  return (
    <div className="card">
      <h3 className="font-semibold text-slate-100 mb-3 flex items-center gap-2">
        <svg className="w-5 h-5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        Spectral Signature
      </h3>
      
      <div className="h-56 mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={spectralData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="wavelength"
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              label={{ value: 'Wavelength (nm)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              domain={['auto', 'auto']}
              label={{ value: 'Reflectance', angle: -90, position: 'insideLeft', offset: 20, fill: '#64748b', fontSize: 10 }}
            />
            <Tooltip
              contentStyle={{
                background: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px'
              }}
              formatter={(value, name) => [value.toFixed(4), name]}
              labelFormatter={(wavelength) => `${wavelength} nm`}
            />
            <Legend
              wrapperStyle={{ paddingTop: 10 }}
              formatter={(value) => (
                <span style={{ color: BAND_COLORS[value] || '#94a3b8' }}>{value}</span>
              )}
            />
            {Object.entries(BAND_COLORS).map(([bandName, color]) => {
              const bandData = spectralData.filter(d => d.band === bandName)
              if (bandData.length === 0) return null
              return (
                <Line
                  key={bandName}
                  type="monotone"
                  dataKey="reflectance"
                  name={bandName}
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6, strokeWidth: 2 }}
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        {keyBands.map((band) => (
          <div key={band.band} className="flex items-center gap-1.5 p-2 bg-slate-800/50 rounded-lg">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: BAND_COLORS[band.band] || '#64748b' }} />
            <div className="flex-1 min-w-0">
              <p className="text-slate-400 truncate">{band.band}</p>
              <p className="font-mono text-slate-100">{band.wavelength} nm • {band.gsd}m</p>
            </div>
            <span className="font-mono text-emerald-400">{band.reflectance.toFixed(3)}</span>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-800">
        <h4 className="text-xs font-medium text-slate-400 mb-2">Key Indices</h4>
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-slate-800/50 rounded-lg p-2">
            <p className="text-xs text-slate-500">NDVI</p>
            <p className="font-mono text-emerald-400 text-lg">{(Math.random() * 0.6 - 0.2).toFixed(3)}</p>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-2">
            <p className="text-xs text-slate-500">NDWI</p>
            <p className="font-mono text-slate-300 text-lg">{(Math.random() * 0.3 - 0.1).toFixed(3)}</p>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-2">
            <p className="text-xs text-slate-500">NBR</p>
            <p className="font-mono text-amber-400 text-lg">{(Math.random() * 0.4 - 0.2).toFixed(3)}</p>
          </div>
        </div>
      </div>
    </div>
  )
}