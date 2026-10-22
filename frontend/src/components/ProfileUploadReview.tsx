import React, { useState } from 'react'
import {
  Upload,
  FileText,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Loader2,
  FileQuestion,
  HelpCircle,
} from 'lucide-react'
import type {
  DocumentType,
  IngestionResponse,
  StudentProfileBase,
  StudentProfileRead,
} from '../types/api'
import { ingestDocument, confirmProfile } from '../lib/api'

interface ProfileUploadReviewProps {
  onProfileConfirmed: (profile: StudentProfileRead) => void
  confirmedProfile: StudentProfileRead | null
}

export const ProfileUploadReview: React.FC<ProfileUploadReviewProps> = ({
  onProfileConfirmed,
  confirmedProfile,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [docType, setDocType] = useState<DocumentType>('resume')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [preview, setPreview] = useState<IngestionResponse | null>(null)
  const [isConfirming, setIsConfirming] = useState<boolean>(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  // Editable candidate profile fields
  const [editableProfile, setEditableProfile] = useState<StudentProfileBase>({})

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      const ext = file.name.toLowerCase()
      if (!ext.endsWith('.pdf') && !ext.endsWith('.docx')) {
        setUploadError('Only .pdf and .docx files are supported.')
        setSelectedFile(null)
        return
      }
      setSelectedFile(file)
      setUploadError(null)
    }
  }

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return

    setIsUploading(true)
    setUploadError(null)
    setPreview(null)

    const result = await ingestDocument(selectedFile, docType)
    setIsUploading(false)

    if (result.error) {
      setUploadError(result.error)
      return
    }

    if (result.data) {
      setPreview(result.data)
      setEditableProfile(result.data.candidate_profile || {})
    }
  }

  const handleConfirm = async () => {
    setIsConfirming(true)
    setConfirmError(null)

    const result = await confirmProfile(editableProfile)
    setIsConfirming(false)

    if (result.error) {
      setConfirmError(result.error)
      return
    }

    if (result.data) {
      onProfileConfirmed(result.data)
    }
  }

  return (
    <section className="space-y-6">
      {/* Step 1 Card: Document Upload */}
      <div className="bg-surface-card rounded-2xl border border-surface-border p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border pb-4 mb-6">
          <div>
            <div className="flex items-center space-x-2">
              <span className="flex items-center justify-center w-6 h-6 rounded-full bg-brand-indigo text-white text-xs font-bold">
                1
              </span>
              <h2 className="text-base font-semibold text-brand-navy">
                Student Document Ingestion
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Upload your academic CV, resume, or transcript (.pdf or .docx up to 10 MiB)
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-xs font-medium text-slate-600">Doc Type:</span>
            <div className="inline-flex rounded-lg border border-surface-border p-1 bg-surface-warm">
              <button
                type="button"
                onClick={() => setDocType('resume')}
                className={`px-3 py-1 rounded text-xs font-medium transition ${
                  docType === 'resume'
                    ? 'bg-white text-brand-navy shadow-xs'
                    : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                Resume / CV
              </button>
              <button
                type="button"
                onClick={() => setDocType('transcript')}
                className={`px-3 py-1 rounded text-xs font-medium transition ${
                  docType === 'transcript'
                    ? 'bg-white text-brand-navy shadow-xs'
                    : 'text-slate-500 hover:text-brand-navy'
                }`}
              >
                Transcript
              </button>
            </div>
          </div>
        </div>

        <form onSubmit={handleIngest} className="space-y-4">
          <div className="border-2 border-dashed border-surface-border hover:border-brand-indigo/50 rounded-xl p-6 text-center transition cursor-pointer bg-surface-warm/40">
            <label htmlFor="document-upload" className="cursor-pointer block">
              <Upload className="mx-auto h-8 w-8 text-brand-indigo/70 mb-2" />
              <span className="text-sm font-medium text-brand-navy block">
                {selectedFile ? selectedFile.name : 'Select PDF or DOCX document'}
              </span>
              <span className="text-xs text-slate-400 block mt-1">
                {selectedFile
                  ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB • Click to replace`
                  : 'Files are parsed locally and securely; no data is retained without confirmation'}
              </span>
              <input
                id="document-upload"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleFileChange}
                disabled={isUploading}
                className="sr-only"
              />
            </label>
          </div>

          {uploadError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start space-x-2">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-600" />
              <span>{uploadError}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!selectedFile || isUploading}
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-brand-navy text-white text-xs font-medium hover:bg-brand-navy/90 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-sm"
            >
              {isUploading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Extracting Profile...</span>
                </>
              ) : (
                <>
                  <FileText className="h-3.5 w-3.5" />
                  <span>Parse & Review Profile</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Step 2 Card: Candidate Profile Preview & Review */}
      {preview && (
        <div className="bg-surface-card rounded-2xl border border-surface-border p-6 shadow-sm space-y-6">
          <div className="border-b border-surface-border pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-brand-indigo text-white text-xs font-bold">
                  2
                </span>
                <h3 className="text-base font-semibold text-brand-navy">
                  Candidate Extraction Review & Verification
                </h3>
              </div>
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider ${
                  preview.status === 'success'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : preview.status === 'partial'
                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                    : 'bg-red-50 text-red-700 border border-red-200'
                }`}
              >
                {preview.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Verify and edit candidate attributes before persisting. Confirmed profiles are explicitly stored with an audit trail.
            </p>
          </div>

          {/* Warnings & Ingestion Issues */}
          {preview.warnings && preview.warnings.length > 0 && (
            <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 space-y-1">
              <div className="flex items-center space-x-1.5 font-semibold">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <span>Extraction Caveats & Notices:</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-amber-700 pl-1">
                {preview.warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Extraction Conflicts */}
          {preview.conflicts && preview.conflicts.length > 0 && (
            <div className="bg-red-50/60 border border-red-200 rounded-xl p-3 text-xs text-red-800 space-y-2">
              <div className="flex items-center space-x-1.5 font-semibold text-red-700">
                <ShieldAlert className="h-4 w-4" />
                <span>Conflicting Values Detected in Document:</span>
              </div>
              <div className="space-y-1">
                {preview.conflicts.map((conflict, idx) => (
                  <div key={idx} className="bg-white/80 p-2 rounded border border-red-200">
                    <div className="font-medium text-brand-navy">{conflict.field_name}</div>
                    <div className="text-slate-600 text-[11px] mt-0.5">{conflict.reason}</div>
                    <div className="text-[11px] text-red-600 mt-0.5">
                      Conflicting candidates: {conflict.conflicting_values.join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Missing Fields Banner */}
          {preview.missing_fields && preview.missing_fields.length > 0 && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-700 flex items-start space-x-2">
              <FileQuestion className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-slate-800">Unresolved / Missing Fields: </span>
                <span className="text-slate-600">
                  {preview.missing_fields.join(', ')}. You can fill these in manually below to improve scholarship matching.
                </span>
              </div>
            </div>
          )}

          {/* Editable Form Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Full Name
              </label>
              <input
                type="text"
                value={editableProfile.name || ''}
                onChange={(e) =>
                  setEditableProfile({ ...editableProfile, name: e.target.value })
                }
                placeholder="e.g. Jane Doe"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
              {preview.provenance['name'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['name'].excerpt}" ({Math.round(preview.provenance['name'].confidence * 100)}% conf)
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Degree / Program
              </label>
              <input
                type="text"
                value={editableProfile.degree_program || ''}
                onChange={(e) =>
                  setEditableProfile({ ...editableProfile, degree_program: e.target.value })
                }
                placeholder="e.g. B.Tech Computer Science"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
              {preview.provenance['degree_program'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['degree_program'].excerpt}"
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Field of Study
              </label>
              <input
                type="text"
                value={editableProfile.field_of_study || ''}
                onChange={(e) =>
                  setEditableProfile({ ...editableProfile, field_of_study: e.target.value })
                }
                placeholder="e.g. Computer Science & AI"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
              {preview.provenance['field_of_study'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['field_of_study'].excerpt}"
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Current Institution
              </label>
              <input
                type="text"
                value={editableProfile.institution || ''}
                onChange={(e) =>
                  setEditableProfile({ ...editableProfile, institution: e.target.value })
                }
                placeholder="e.g. Stanford University"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
              {preview.provenance['institution'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['institution'].excerpt}"
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Academic Score / GPA
              </label>
              <div className="flex space-x-2">
                <input
                  type="number"
                  step="0.01"
                  value={editableProfile.academic_score?.score ?? ''}
                  onChange={(e) => {
                    const val = e.target.value === '' ? 0 : parseFloat(e.target.value)
                    setEditableProfile({
                      ...editableProfile,
                      academic_score: {
                        score: val,
                        scale: editableProfile.academic_score?.scale || 4.0,
                      },
                    })
                  }}
                  placeholder="Score (e.g. 3.8)"
                  className="w-2/3 text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
                />
                <input
                  type="number"
                  step="0.1"
                  value={editableProfile.academic_score?.scale ?? ''}
                  onChange={(e) => {
                    const val = e.target.value === '' ? 4.0 : parseFloat(e.target.value)
                    setEditableProfile({
                      ...editableProfile,
                      academic_score: {
                        score: editableProfile.academic_score?.score || 0,
                        scale: val,
                      },
                    })
                  }}
                  placeholder="Scale (e.g. 4.0)"
                  className="w-1/3 text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
                />
              </div>
              {preview.provenance['academic_score'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['academic_score'].excerpt}"
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Country / Citizenship
              </label>
              <input
                type="text"
                value={editableProfile.country || ''}
                onChange={(e) =>
                  setEditableProfile({ ...editableProfile, country: e.target.value })
                }
                placeholder="e.g. India or Germany"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
              {preview.provenance['country'] && (
                <p className="text-[10px] text-slate-400 mt-0.5 italic">
                  Extracted from: "{preview.provenance['country'].excerpt}"
                </p>
              )}
            </div>

            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Target Study Destinations (comma-separated)
              </label>
              <input
                type="text"
                value={(editableProfile.target_destinations || []).join(', ')}
                onChange={(e) => {
                  const destinations = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                  setEditableProfile({ ...editableProfile, target_destinations: destinations })
                }}
                placeholder="e.g. Germany, United Kingdom, Canada"
                className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo"
              />
            </div>
          </div>

          {/* Explicit Confirmation Boundary */}
          <div className="border-t border-surface-border pt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-2 text-xs text-slate-500">
              <HelpCircle className="h-4 w-4 text-brand-indigo" />
              <span>
                Profiles are stored in the database only upon explicit confirmation.
              </span>
            </div>

            {confirmError && (
              <span className="text-xs text-red-600">{confirmError}</span>
            )}

            <button
              type="button"
              onClick={handleConfirm}
              disabled={isConfirming}
              className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-5 py-2.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50 transition shadow-sm"
            >
              {isConfirming ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Persisting Profile...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Confirm & Save Profile</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Confirmed Profile Indicator */}
      {confirmedProfile && (
        <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs font-bold text-emerald-900">
                Profile Confirmed & Ready: {confirmedProfile.name || 'Unnamed Scholar'}
              </div>
              <div className="text-[11px] text-emerald-700 mt-0.5">
                ID: {confirmedProfile.id} • {confirmedProfile.degree_program || 'Degree N/A'} (
                {confirmedProfile.field_of_study || 'Field N/A'})
              </div>
            </div>
          </div>

          <span className="text-xs font-medium text-emerald-800 bg-emerald-100/60 px-2.5 py-1 rounded-full border border-emerald-200">
            Active for Research
          </span>
        </div>
      )}
    </section>
  )
}
