import React, { useState, useRef, useEffect } from 'react'
import { Camera, MapPin, Image, Send, X, Loader2, CheckCircle, AlertCircle, MapPinPlus, Mic, MicOff } from 'lucide-react'

const THREAT_OPTIONS = [
  { value: 'critical', label: 'Critical - Active dumping visible', color: 'text-red-400' },
  { value: 'high', label: 'High - Large waste piles', color: 'text-amber-400' },
  { value: 'moderate', label: 'Moderate - Scattered debris', color: 'text-emerald-400' },
  { value: 'low', label: 'Low - Minor littering', color: 'text-slate-400' }
]

const WASTE_TYPES = [
  'Mixed waste',
  'Construction debris',
  'Hazardous materials',
  'Electronic waste',
  'Plastic waste',
  'Organic waste',
  'Medical waste',
  'Other'
]

export function CitizenReport({ onClose, onSubmit }) {
  const [step, setStep] = useState(1) // 1: location, 2: details, 3: media, 4: submit
  const [location, setLocation] = useState({ lat: null, lng: null, accuracy: null })
  const [watchingLocation, setWatchingLocation] = useState(false)
  const [threatLevel, setThreatLevel] = useState('moderate')
  const [wasteType, setWasteType] = useState('')
  const [description, setDescription] = useState('')
  const [photos, setPhotos] = useState([])
  const [audioBlob, setAudioBlob] = useState(null)
  const [recording, setRecording] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const mapRef = useRef(null)
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  
  // Step validation
  const canProceed = () => {
    switch (step) {
      case 1: return location.lat !== null
      case 2: return threatLevel && wasteType && description.trim().length >= 20
      case 3: return true // Media is optional
      case 4: return true
      default: return false
    }
  }
  
  // Geolocation
  const getCurrentLocation = () => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported')
      return
    }
    
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy
        })
        setWatchingLocation(true)
      },
      (err) => {
        setError('Failed to get location: ' + err.message)
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    )
  }
  
  const watchLocation = () => {
    if (!navigator.geolocation) return
    
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setLocation({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy
        })
      },
      (err) => console.warn('Location watch error:', err),
      { enableHighAccuracy: true, maximumAge: 5000 }
    )
    
    return () => navigator.geolocation.clearWatch(watchId)
  }
  
  useEffect(() => {
    if (watchingLocation) {
      return watchLocation()
    }
  }, [watchingLocation])
  
  // Camera
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'environment' } 
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
    } catch (err) {
      setError('Camera access denied: ' + err.message)
    }
  }
  
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }
  
  const capturePhoto = () => {
    if (!videoRef.current) return
    
    const canvas = document.createElement('canvas')
    canvas.width = videoRef.current.videoWidth
    canvas.height = videoRef.current.videoHeight
    const ctx = canvas.getContext('2d')
    ctx.drawImage(videoRef.current, 0, 0)
    
    canvas.toBlob((blob) => {
      const file = new File([blob], `report-${Date.now()}.jpg`, { type: 'image/jpeg' })
      setPhotos(prev => [...prev, file])
    }, 'image/jpeg', 0.9)
  }
  
  // Audio recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorderRef.current = new MediaRecorder(stream)
      audioChunksRef.current = []
      
      mediaRecorderRef.current.ondataavailable = (e) => {
        audioChunksRef.current.push(e.data)
      }
      
      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        setAudioBlob(blob)
        stream.getTracks().forEach(track => track.stop())
      }
      
      mediaRecorderRef.current.start()
      setRecording(true)
    } catch (err) {
      setError('Microphone access denied: ' + err.message)
    }
  }
  
  const stopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }
  
  // File handling
  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files)
    const validFiles = files.filter(f => f.type.startsWith('image/') && f.size < 10 * 1024 * 1024)
    setPhotos(prev => [...prev, ...validFiles])
  }
  
  const removePhoto = (index) => {
    setPhotos(prev => prev.filter((_, i) => i !== index))
  }
  
  // Submit
  const handleSubmit = async () => {
    if (!canProceed()) return
    
    setSubmitting(true)
    setError(null)
    
    try {
      // Prepare form data
      const formData = new FormData()
      formData.append('lat', location.lat.toString())
      formData.append('lng', location.lng.toString())
      formData.append('accuracy', location.accuracy?.toString() || '')
      formData.append('threat_level', threatLevel)
      formData.append('waste_type', wasteType)
      formData.append('description', description)
      
      photos.forEach((photo, i) => {
        formData.append(`photos`, photo)
      })
      
      if (audioBlob) {
        formData.append('audio', audioBlob, `report-${Date.now()}.webm`)
      }
      
      // Submit to API
      const response = await fetch('/api/citizen/report', {
        method: 'POST',
        body: formData
      })
      
      if (!response.ok) throw new Error('Submission failed')
      
      const result = await response.json()
      setSuccess(true)
      setTimeout(() => {
        onSubmit?.(result)
        onClose?.()
      }, 2000)
      
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }
  
  // Render steps
  const renderStep1 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-slate-100">Step 1: Location</h3>
      <p className="text-sm text-slate-400">Tap the map or use GPS to mark the dumping site</p>
      
      {error && (
        <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}
      
      <div className="relative h-64 rounded-lg overflow-hidden border border-slate-700">
        {/* Map placeholder - would use Leaflet/MapLibre */}
        <div className="absolute inset-0 bg-slate-800 flex items-center justify-center">
          <MapPin className="w-12 h-12 text-slate-600" />
        </div>
        {location.lat && (
          <div className="absolute bottom-2 left-2 right-2 bg-slate-900/90 px-3 py-2 rounded-t-lg text-xs">
            <div className="font-mono text-emerald-400">{location.lat.toFixed(6)}, {location.lng.toFixed(6)}</div>
            <div className="text-slate-500">Accuracy: ±{Math.round(location.accuracy || 0)}m</div>
          </div>
        )}
      </div>
      
      <div className="flex gap-2">
        <button
          onClick={getCurrentLocation}
          disabled={watchingLocation}
          className="flex-1 btn-primary flex items-center justify-center gap-2"
        >
          <MapPin className="w-4 h-4" />
          {watchingLocation ? 'Tracking GPS' : 'Use Current Location'}
        </button>
        <button
          onClick={() => { /* Open full map */ }}
          className="btn-secondary flex items-center justify-center gap-2"
        >
          <MapPinPlus className="w-4 h-4" />
          Pick on Map
        </button>
      </div>
    </div>
  )
  
  const renderStep2 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-slate-100">Step 2: Details</h3>
      
      <div>
        <label className="block text-sm text-slate-300 mb-2">Threat Level</label>
        <div className="grid grid-cols-2 gap-2">
          {THREAT_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setThreatLevel(opt.value)}
              className={`p-3 rounded-lg border-2 text-left transition-all ${
                threatLevel === opt.value
                  ? `border-emerald-500 bg-emerald-500/10`
                  : 'border-slate-700 hover:border-slate-600'
              }`}
            >
              <div className={`font-medium ${opt.color}`}>{opt.label.split(' - ')[0]}</div>
              <div className="text-xs text-slate-500 mt-1">{opt.label.split(' - ')[1]}</div>
            </button>
          ))}
        </div>
      </div>
      
      <div>
        <label className="block text-sm text-slate-300 mb-2">Waste Type</label>
        <select
          value={wasteType}
          onChange={(e) => setWasteType(e.target.value)}
          className="input"
        >
          <option value="">Select waste type</option>
          {WASTE_TYPES.map(type => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>
      
      <div>
        <label className="block text-sm text-slate-300 mb-2">
          Description <span className="text-emerald-400">({description.length}/500)</span>
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className="input resize-none"
          placeholder="Describe what you see: size, type of waste, any visible hazards, nearby water sources, etc."
          maxLength={500}
        />
      </div>
    </div>
  )
  
  const renderStep3 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-slate-100">Step 3: Evidence (Optional)</h3>
      <p className="text-sm text-slate-400">Add photos, audio notes, or take a picture now</p>
      
      {/* Camera */}
      <div className="border-2 border-dashed border-slate-700 rounded-lg p-4">
        <video
          ref={videoRef}
          className="w-full h-48 rounded-lg bg-slate-800"
          autoPlay
          playsInline
          muted
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={startCamera}
            className="btn-secondary flex-1 flex items-center justify-center gap-2"
          >
            <Camera className="w-4 h-4" />
            Open Camera
          </button>
          <button
            onClick={capturePhoto}
            disabled={!videoRef.current?.srcObject}
            className="btn-primary flex-1 flex items-center justify-center gap-2"
          >
            <Image className="w-4 h-4" />
            Capture
          </button>
        </div>
      </div>
      
      {/* File upload */}
      <div>
        <label className="block text-sm text-slate-300 mb-2">Or Upload Photos</label>
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={handleFileSelect}
          className="input file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-emerald-500/20 file:text-emerald-400 hover:file:bg-emerald-500/30"
        />
      </div>
      
      {/* Photo preview */}
      {photos.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {photos.map((photo, i) => (
            <div key={i} className="relative flex-shrink-0 w-24 h-24 rounded-lg overflow-hidden">
              <img 
                src={URL.createObjectURL(photo)} 
                alt={`Photo ${i+1}`}
                className="w-full h-full object-cover"
              />
              <button
                onClick={() => removePhoto(i)}
                className="absolute top-1 right-1 p-1 bg-red-500/90 text-white rounded-full hover:bg-red-500"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      
      {/* Audio recording */}
      <div className="border-t border-slate-700 pt-4">
        <label className="block text-sm text-slate-300 mb-2">Audio Note</label>
        <div className="flex items-center gap-3">
          <button
            onClick={recording ? stopRecording : startRecording}
            className={`p-3 rounded-lg flex items-center gap-2 transition-colors ${
              recording
                ? 'bg-red-500/20 text-red-400 animate-pulse'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {recording ? <Mic className="w-5 h-5" /> : <MicOff className="w-5 h-5" />}
            <span>{recording ? 'Recording...' : 'Record Audio Note'}</span>
          </button>
          
          {audioBlob && (
            <audio controls className="flex-1" src={URL.createObjectURL(audioBlob)} />
          )}
        </div>
      </div>
    </div>
  )
  
  const renderStep4 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-slate-100">Step 4: Review & Submit</h3>
      
      <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
        <div className="flex justify-between">
          <span className="text-slate-400">Location</span>
          <span className="font-mono text-slate-100">
            {location.lat?.toFixed(6)}, {location.lng?.toFixed(6)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Threat Level</span>
          <span className={`font-medium ${THREAT_OPTIONS.find(o => o.value === threatLevel)?.color}`}>
            {threatLevel}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Waste Type</span>
          <span className="font-mono text-slate-100">{wasteType || 'Not specified'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Photos</span>
          <span className="font-mono text-slate-100">{photos.length}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Audio</span>
          <span className="font-mono text-slate-100">{audioBlob ? 'Yes' : 'No'}</span>
        </div>
      </div>
      
      {error && (
        <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}
      
      {success && (
        <div className="p-4 bg-emerald-500/20 border border-emerald-500/30 rounded-lg text-center">
          <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-2" />
          <h4 className="font-semibold text-emerald-400">Report Submitted!</h4>
          <p className="text-sm text-slate-400">Thank you for helping keep our environment clean.</p>
        </div>
      )}
      
      <div className="flex gap-2 pt-2">
        <button
          onClick={() => setStep(3)}
          className="flex-1 btn-secondary"
        >
          Back
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting || !canProceed()}
          className="flex-1 btn-primary"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Submitting...
            </>
          ) : (
            <>
              <Send className="w-4 h-4 mr-2" />
              Submit Report
            </>
          )}
        </button>
      </div>
    </div>
  )
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80">
      <div className="bg-slate-950 rounded-2xl max-w-md w-full max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="sticky top-0 bg-slate-950/95 backdrop-blur-sm border-b border-slate-800 px-4 py-3 flex items-center justify-between z-10">
          <h2 className="font-semibold text-slate-100">Report Illegal Dumping</h2>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-4 space-y-2">
          {/* Progress indicator */}
          <div className="flex items-center justify-between mb-4">
            {[1, 2, 3, 4].map(s => (
              <div key={s} className="flex flex-col items-center">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all ${
                  s < step ? 'bg-emerald-500 text-slate-950' :
                  s === step ? 'bg-emerald-500 text-slate-950' :
                  'bg-slate-800 text-slate-500'
                }`}>
                  {s}
                </div>
                <span className="text-xs text-slate-500 mt-1">
                  {['Location', 'Details', 'Media', 'Submit'][s-1]}
                </span>
              </div>
            ))}
          </div>
          
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
          {step === 4 && renderStep4()}
        </div>
        
        {/* Navigation */}
        <div className="sticky bottom-0 bg-slate-950/95 backdrop-blur-sm border-t border-slate-800 px-4 py-3 flex justify-between">
          <button
            onClick={() => setStep(prev => Math.max(1, prev - 1))}
            disabled={step === 1}
            className="btn-secondary"
          >
            Back
          </button>
          <button
            onClick={() => setStep(prev => Math.min(4, prev + 1))}
            disabled={step === 4 || !canProceed()}
            className="btn-primary"
          >
            {step === 4 ? 'Submit' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  )
}