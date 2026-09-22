import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

const THREAT_COLORS = {
  Critical: '#ef4444',
  High: '#f59e0b',
  Moderate: '#10b981',
  Low: '#64748b'
}

export function AnalyticsPanel({ features, className = '' }) {
  const threatCounts = features.reduce((acc, f) => {
    acc[f.properties.threat_level] = (acc[f.properties.threat_level] || 0) + 1
    return acc
  }, {})

  const threatData = Object.entries(threatCounts).map(([name, value]) => ({
    name,
    value,
    color: THREAT_COLORS[name] || THREAT_COLORS.Low
  }))

  const areaByThreat = features.reduce((acc, f) => {
    acc[f.properties.threat_level] = (acc[f.properties.threat_level] || 0) + f.properties.area_m2
    return acc
  }, {})

  const areaData = Object.entries(areaByThreat).map(([name, value]) => ({
    name,
    area: Math.round(value)
  }))

  if (features.length === 0) {
    return (
      <div className={`${className} card`}>
        <p className="text-center text-slate-500 py-8">No data to display</p>
      </div>
    )
  }

  return (
    <div className={`${className} card`}>
      <h3 className="font-semibold text-slate-100 mb-4">Analytics Summary</h3>
      
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={threatData}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={60}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                labelLine={false}
              >
                {threatData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value, name) => [value, name]}
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={areaData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis dataKey="name" type="category" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} width={60} />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px'
                }}
                formatter={(value) => [value.toLocaleString(), 'Area (m²)']}
              />
              <Bar dataKey="area" radius={[0, 4, 4, 0]}>
                {areaData.map((entry, index) => (
                  <Cell key={`bar-${index}`} fill={THREAT_COLORS[entry.name] || THREAT_COLORS.Low} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="space-y-2 text-sm">
        {threatData.map((entry) => (
          <div key={entry.name} className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded" style={{ backgroundColor: entry.color }} />
              <span className="text-slate-300 capitalize">{entry.name}</span>
            </span>
            <span className="font-mono text-slate-100">{entry.value} sites</span>
          </div>
        ))}
      </div>
    </div>
  )
}