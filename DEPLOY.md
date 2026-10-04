# SkyDump AI - Deployment Guide

## Quick Deploy (5 minutes)

### 1. Frontend → Vercel

**Option A: Vercel CLI (Recommended)**
```bash
cd frontend
npm i -g vercel
vercel login
vercel --prod
# Set: Root Directory = frontend, Build Command = npm run build, Output = dist
```

**Option B: GitHub Integration**
1. Push to GitHub
2. Go to https://vercel.com/new
3. Import repository
4. Set Root Directory: `frontend`
5. Build Command: `npm run build`
6. Output Directory: `dist`
7. Add Environment Variable: `VITE_API_URL=https://your-backend-url.railway.app`
8. Deploy

---

### 2. Backend → Railway (or Render)

**Option A: Railway (Easiest with Docker)**
```bash
cd backend
railway login
railway init
# Select "Deploy from Dockerfile"
railway up
# Add env vars in Railway dashboard (see below)
```

**Option B: Render (Free tier)**
1. Go to https://dashboard.render.com/new/web-service
2. Connect GitHub repo
3. Root Directory: `backend`
4. Runtime: Docker
5. Add environment variables (see below)
6. Deploy

---

## Environment Variables

### Backend (Required)

| Variable | Value | Notes |
|----------|-------|-------|
| `DEBUG` | `false` | Production |
| `JWT_SECRET` | *generate 32+ char random* | `openssl rand -hex 32` |
| `ALLOWED_ORIGINS` | `["https://your-frontend.vercel.app"]` | **Must include Vercel URL** |
| `EXTRA_ALLOWED_ORIGINS` | (optional) | Comma-separated extra origins |
| `STAC_API_URL` | `https://planetarycomputer.microsoft.com/api/stac/v1` | |
| `SENTINEL2_COLLECTION` | `sentinel-2-l2a` | |
| `MAX_CLOUD_COVER` | `20` | |
| `NDVI_DELTA_THRESHOLD` | `-0.35` | |
| `SWIR_THRESHOLD` | `0.25` | |
| `MIN_CONTOUR_AREA` | `10000.0` | |

### Frontend (Required)

| Variable | Value | Notes |
|----------|-------|-------|
| `VITE_API_URL` | `https://your-backend.railway.app` | Backend URL |

---

## Post-Deploy Configuration

### 1. Update Backend CORS with Vercel URL
After frontend deploys, copy the Vercel URL (e.g., `https://skydump-ai.vercel.app`) and add to backend:
- Railway/Render Dashboard → Environment Variables
- `ALLOWED_ORIGINS` = `["https://your-vercel-url.vercel.app"]`
- Redeploy backend

### 2. Verify Deployment

```bash
# Health checks
curl https://your-backend.railway.app/health
curl https://your-frontend.vercel.app

# Test API
curl -X POST https://your-backend.railway.app/api/analyze-bbox \
  -H "Content-Type: application/json" \
  -d '{"bbox":[4.2,51.85,4.5,51.95],"start_date":"2024-01-01","end_date":"2024-12-31","confidence_threshold":0.7}'
```

### 3. Test Full Flow
1. Open frontend URL
2. Select sector (Rotterdam, Amazon, Congo)
3. Click "Report" → submit test report
4. Click "Export" → download GeoJSON
5. Switch to Dark/Light theme

---

## Demo Accounts (Auto-created)

| Role | Email | Password | Permissions |
|------|-------|----------|-------------|
| Admin | `admin@demo` | `demo123` | Full access |
| Analyst | `analyst@demo` | `demo123` | Read + Export |
| Viewer | `viewer@demo` | `demo123` | Read only |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CORS errors | Check `ALLOWED_ORIGINS` includes exact Vercel URL (no trailing slash) |
| API 500 errors | Check Railway/Render logs; verify `JWT_SECRET` is set |
| Map not loading | Verify `VITE_API_URL` in Vercel env vars |
| PDF export fails | Ensure `weasyprint` dependencies installed (in Dockerfile) |
| ML model not found | Checkpoint is dummy; threshold mode works without it |

---

## CI/CD (Optional)

The `.github/workflows/ci.yml` runs on every push:
- Backend: lint (ruff, black, pyright) + tests
- Frontend: lint (eslint, prettier) + build
- Docker build test on main branch

Enable in GitHub: Settings → Actions → Allow all actions