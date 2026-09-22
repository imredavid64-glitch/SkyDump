# SkyDump AI

> **Open-source satellite waste dumping detection and monitoring platform**  
> Powered by ESA Sentinel-2 Earth observation data via Microsoft Planetary Computer

[![CI](https://github.com/imredavid64-glitch/SkyDump/actions/workflows/ci.yml/badge.svg)](https://github.com/imredavid64-glitch/SkyDump/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/React-18-61dafb.svg)](https://reactjs.org/)

---

## 🎯 Overview

SkyDump AI detects illegal waste dumping sites by analyzing **temporal changes in Sentinel-2 satellite imagery**. The system computes NDVI (Normalized Difference Vegetation Index) differences between two time periods and identifies anomalies where vegetation has been cleared (`ΔNDVI < -0.35`) paired with synthetic material reflectance (`SWIR Band 11 > 0.25`).

### Key Features

| Feature | Description |
|---------|-------------|
| 🛰️ **Multi-temporal Analysis** | Compares Sentinel-2 L2A scenes across custom date ranges |
| 📊 **NDVI Change Detection** | ΔNDVI thresholding (-0.35) for vegetation loss detection |
| 🔍 **SWIR Material Classification** | Band 11 (1.6µm) thresholding for synthetic waste identification |
| 🗺️ **Interactive Web Map** | Leaflet-based visualization with layer switching (OSM, Satellite, NDVI, NIR) |
| 📈 **Risk Scoring** | 0-100 Environmental Risk Score based on area, confidence, water proximity |
| 📥 **GeoJSON Export** | One-click download for municipal enforcement integration |
| 🌐 **Offline-First** | 3 pre-loaded real-world sectors work without API keys |
| 🐳 **Docker Ready** | Single-command deployment with `docker-compose` |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SkyDump AI                               │
├─────────────────────────────┬───────────────────────────────────┤
│         Backend (FastAPI)   │      Frontend (React + Vite)      │
├─────────────────────────────┼───────────────────────────────────┤
│  • STAC Pipeline (pystac)   │  • MapView (react-leaflet)        │
│  • Anomaly Engine (OpenCV)  │  • AnomalyList (filterable cards) │
│  • Mock Data (3 sectors)    │  • SpectralViewer (recharts)      │
│  • REST API (/analyze-bbox) │  • AnalyticsPanel (charts)        │
└─────────────────────────────┴───────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Data Sources     │
                    ├───────────────────┤
                    │  Microsoft        │
                    │  Planetary        │
                    │  Computer STAC    │
                    │  (Sentinel-2 L2A) │
                    └───────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Or: Python 3.11+, Node 20+

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/imredavid64-glitch/SkyDump.git
cd SkyDump
docker-compose up -d
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

### Option 2: Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

---

## 📡 API Reference

### Health Check
```http
GET /health
```
```json
{ "status": "ok", "version": "1.0.0", "service": "SkyDump AI" }
```

### Analyze Bounding Box
```http
POST /api/analyze-bbox
Content-Type: application/json

{
  "bbox": [4.2, 51.85, 4.5, 51.95],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "confidence_threshold": 0.7
}
```
```json
{
  "features": [...],
  "summary": { "total_sites": 5, "total_area_m2": 125000, ... },
  "metadata": { "scene_t0": "...", "scene_t1": "...", "bbox": [...] }
}
```

### Get Mock Sites (Offline)
```http
GET /api/mock-sites?sector=sector-7
```
```http
GET /api/sectors
```

---

## 🗺️ Pre-loaded Sectors (Offline Mode)

| Sector | Location | Coordinates | Sites |
|--------|----------|-------------|-------|
| **Sector 7** | Rotterdam Industrial Zone, Netherlands | 51.9°N, 4.35°E | 7 |
| **Sector 12** | Amazon River Basin, Brazil | 3.25°S, 55.25°W | 6 |
| **Sector 4** | Congo Basin Forest Reserve, DRC | 1.25°S, 18.75°E | 8 |

Each sector includes realistic waste polygons with:
- GeoJSON geometry (Polygon)
- Area (m²), estimated tonnage
- Confidence score (65-95%)
- Risk score (0-100)
- Threat level: Critical / High / Moderate / Low

---

## 🔬 Detection Algorithm

```
Input: Two Sentinel-2 L2A scenes (t0, t1) for same bbox

1. Fetch Bands: B04 (Red, 10m), B08 (NIR, 10m), B11 (SWIR 1.6µm, 20m)
2. Resample all bands to 10m resolution
3. Compute NDVI_t0 = (NIR - Red) / (NIR + Red + ε)
4. Compute NDVI_t1 = (NIR - Red) / (NIR + Red + ε)
5. ΔNDVI = NDVI_t1 - NDVI_t0
6. Anomaly Mask = (ΔNDVI < -0.35) AND (SWIR11 > 0.25)
7. Contours → Polygons → GeoJSON Features
8. Risk Score = 0.4×Area_norm + 0.3×Confidence + 0.3×Proximity_to_Water
```

---

## 🌍 Deployment

### Vercel (Frontend)
1. Connect GitHub repo to Vercel
2. Set **Root Directory**: `frontend`
3. Build Command: `npm run build`
4. Output Directory: `dist`
5. Deploy → `https://skydump.vercel.app`

### Railway/Render/Fly.io (Backend)
```bash
# Railway example
railway login
railway init
railway up
```
Set environment variables from `backend/.env.example`

### Docker Production
```bash
docker-compose -f docker-compose.yml up -d --build
```

---

## 📁 Project Structure

```
skydump-ai/
├── .github/workflows/ci.yml      # GitHub Actions CI
├── backend/
│   ├── main.py                   # FastAPI app + endpoints
│   ├── config.py                 # Settings management
│   ├── stac_pipeline.py          # STAC search + band fetching
│   ├── anomaly_engine.py         # NDVI delta + contour extraction
│   ├── mock_data.py              # 3 real-world sector datasets
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Main layout + state
│   │   ├── main.jsx              # Entry point
│   │   ├── index.css             # Tailwind + custom styles
│   │   ├── components/
│   │   │   ├── MapView.jsx       # Leaflet map + layers
│   │   │   ├── AnomalyList.jsx   # Filterable site cards
│   │   │   ├── SpectralViewer.jsx # Recharts spectral curves
│   │   │   └── AnalyticsPanel.jsx # Charts + stats
│   │   └── data/
│   │       └── mockDumpsites.js  # Frontend mock data bridge
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── vercel.json
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   ├── nginx.conf
│   └── .env.example
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest -v

# Frontend tests
cd frontend
npm run lint
npm run build
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 🙏 Acknowledgments

- **Microsoft Planetary Computer** for free Sentinel-2 L2A access
- **ESA Copernicus** for Sentinel-2 mission data
- **pystac-client**, **rasterio**, **OpenCV** communities
- **Leaflet**, **React-Leaflet**, **Recharts** for visualization

---

## 📞 Support

- 🐛 [Issues](https://github.com/imredavid64-glitch/SkyDump/issues)
- 💬 [Discussions](https://github.com/imredavid64-glitch/SkyDump/discussions)
- 📧 [Email](mailto:dev@skydump.ai)

---

<p align="center">
  Made with 🛰️ for environmental protection
</p>