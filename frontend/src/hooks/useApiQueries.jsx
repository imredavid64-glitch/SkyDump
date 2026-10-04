import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';

// Query Keys
export const queryKeys = {
  sectors: ['sectors'],
  sector: (id) => ['sector', id],
  analysis: (params) => ['analysis', params],
  mockSites: (sector) => ['mockSites', sector],
  timeseries: (sector) => ['timeseries', sector],
  precomputed: (sector) => ['precomputed', sector],
  citizenReports: ['citizenReports'],
  alerts: ['alerts'],
  models: ['models'],
};

// Sectors
export function useSectors() {
  return useQuery({
    queryKey: queryKeys.sectors,
    queryFn: () => api.get('/api/sectors').then(res => res.data),
  });
}

export function useSector(sectorId) {
  return useQuery({
    queryKey: queryKeys.sector(sectorId),
    queryFn: () => api.get(`/api/precomputed/${sectorId}`).then(res => res.data),
    enabled: !!sectorId,
  });
}

export function usePrecomputedTimeseries(sectorId) {
  return useQuery({
    queryKey: queryKeys.timeseries(sectorId),
    queryFn: () => api.get(`/api/precomputed/${sectorId}/timeseries`).then(res => res.data),
    enabled: !!sectorId,
  });
}

// Analysis
export function useAnalysis(params) {
  return useQuery({
    queryKey: queryKeys.analysis(params),
    queryFn: () => api.post('/api/analyze-bbox', params).then(res => res.data),
    enabled: !!params?.bbox,
  });
}

export function useAnalyzeBbox() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (params) => api.post('/api/analyze-bbox', params).then(res => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analysis'] });
    },
  });
}

// Mock Sites
export function useMockSites(sector, confidenceThreshold) {
  return useQuery({
    queryKey: queryKeys.mockSites(sector),
    queryFn: () => api.get('/api/mock-sites', { params: { sector } }).then(res => res.data),
    enabled: !!sector,
  });
}

// Citizen Reports
export function useCitizenReports() {
  return useQuery({
    queryKey: queryKeys.citizenReports,
    queryFn: () => api.get('/api/citizen/reports').then(res => res.data),
  });
}

export function useSubmitCitizenReport() {
  return useMutation({
    mutationFn: (data) => api.post('/api/citizen/report', data, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(res => res.data),
  });
}

// Alerts
export function useAlerts(status) {
  return useQuery({
    queryKey: [...queryKeys.alerts, status],
    queryFn: () => api.get('/api/authority/alerts', { params: { status } }).then(res => res.data),
  });
}

export function useCreateAlert() {
  return useMutation({
    mutationFn: (data) => api.post('/api/authority/alerts', data).then(res => res.data),
  });
}

// ML Models
export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: () => api.get('/api/ml/models').then(res => res.data),
  });
}

// Precomputed data
export function usePrecomputedIndex() {
  return useQuery({
    queryKey: ['precomputed', 'index'],
    queryFn: () => api.get('/api/precomputed').then(res => res.data),
  });
}

export function usePrecomputedSector(sectorId) {
  return useQuery({
    queryKey: queryKeys.precomputed(sectorId),
    queryFn: () => api.get(`/api/precomputed/${sectorId}`).then(res => res.data),
    enabled: !!sectorId,
  });
}

export function usePrecomputedTimeseries(sectorId) {
  return useQuery({
    queryKey: queryKeys.timeseries(sectorId),
    queryFn: () => api.get(`/api/precomputed/${sectorId}/timeseries`).then(res => res.data),
    enabled: !!sectorId,
  });
}