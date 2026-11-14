"use client";

import React, { useState, useEffect } from "react";
import { DocumentItem, IngestionStatusDetail, ChapterSummary } from "@/lib/types";
import {
  listDocuments,
  uploadDocument,
  getDocumentStatus,
  getDocumentSummaries,
  toggleDocumentActive,
  deleteDocument,
  reingestDocument,
} from "@/lib/api";
import { useApp } from "@/lib/context";
import { formatBytes } from "@/lib/utils";
import {
  Upload,
  FileText,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  BookOpen,
  Eye,
  Filter,
} from "lucide-react";

const DEPARTMENTS = ["All", "CSE", "ECE", "EEE", "ME", "AIML", "BT"];
const DOC_TYPES = ["syllabus", "book", "notes", "previous_paper"];

export function DocumentUpload() {
  const { profile } = useApp();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Upload form state
  const [file, setFile] = useState<File | null>(null);
  const [department, setDepartment] = useState("CSE");
  const [semester, setSemester] = useState(3);
  const [subject, setSubject] = useState("Database Management Systems");
  const [academicYear, setAcademicYear] = useState("2026-27");
  const [docType, setDocType] = useState("book");
  const [isActive, setIsActive] = useState(true);

  // Filter state
  const [filterDept, setFilterDept] = useState("All");
  const [filterSem, setFilterSem] = useState<number | null>(null);

  // Ingestion status modal
  const [selectedDocStatus, setSelectedDocStatus] = useState<IngestionStatusDetail | null>(null);
  const [selectedDocSummaries, setSelectedDocSummaries] = useState<ChapterSummary[]>([]);
  const [loadingStatus, setLoadingStatus] = useState(false);

  const loadDocs = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const docs = await listDocuments({
        department: filterDept !== "All" ? filterDept : undefined,
        semester: filterSem ?? undefined,
      });
      setDocuments(docs || []);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, [filterDept, filterSem]);

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    try {
      setUploading(true);
      setErrorMsg(null);
      await uploadDocument(
        file,
        {
          department,
          semester,
          subject,
          academic_year: academicYear,
          doc_type: docType,
          is_active: isActive,
        },
        profile
      );
      setFile(null);
      // Reset input element
      const fileInput = document.getElementById("doc-file-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
      await loadDocs();
    } catch (err: any) {
      setErrorMsg(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleViewStatus = async (docId: string) => {
    try {
      setLoadingStatus(true);
      const [status, summaries] = await Promise.all([
        getDocumentStatus(docId),
        getDocumentSummaries(docId).catch(() => []),
      ]);
      setSelectedDocStatus(status);
      setSelectedDocSummaries(summaries);
    } catch (err: any) {
      alert("Failed to load status: " + err.message);
    } finally {
      setLoadingStatus(false);
    }
  };

  const handleToggleActive = async (docId: string, current: boolean) => {
    try {
      await toggleDocumentActive(docId, !current);
      setDocuments((prev) =>
        prev.map((d) => (d.id === docId ? { ...d, is_active: !current } : d))
      );
    } catch (err: any) {
      alert("Toggle failed: " + err.message);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("Are you sure you want to delete this document and all its chunks?"))
      return;
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      if (selectedDocStatus?.document_id === docId) setSelectedDocStatus(null);
    } catch (err: any) {
      alert("Delete failed: " + err.message);
    }
  };

  const handleReingest = async (docId: string) => {
    try {
      await reingestDocument(docId);
      alert("Re-ingestion queued in background!");
      loadDocs();
    } catch (err: any) {
      alert("Re-ingest failed: " + err.message);
    }
  };

  return (
    <div className="space-y-8">
      {/* Upload Form Box */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-5">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Upload className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Upload Course PDF</h3>
              <p className="text-xs text-muted-foreground">
                Uploaded materials are automatically extracted, chunked, embedded with bge-small, and summarized.
              </p>
            </div>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-600 dark:text-danger-400 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleUploadSubmit} className="space-y-4">
          {/* File Picker */}
          <div className="border-2 border-dashed border-border rounded-xl p-6 text-center hover:border-primary/50 transition-colors bg-secondary/30">
            <input
              id="doc-file-input"
              type="file"
              accept=".pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              required
              className="hidden"
            />
            <label htmlFor="doc-file-input" className="cursor-pointer block space-y-2">
              <FileText className="w-8 h-8 text-primary-500 mx-auto" />
              <div className="text-xs font-medium text-foreground">
                {file ? (
                  <span className="text-primary font-bold">{file.name} ({formatBytes(file.size)})</span>
                ) : (
                  <span>Click to select coursebook or syllabus PDF (up to 50 MB)</span>
                )}
              </div>
              <p className="text-[10px] text-muted-foreground">
                Only PDF documents with searchable text or scanned pages supported
              </p>
            </label>
          </div>

          {/* Metadata Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <label className="block font-medium text-foreground mb-1">Department</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground"
              >
                {DEPARTMENTS.filter((d) => d !== "All").map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-medium text-foreground mb-1">Semester (1–8)</label>
              <select
                value={semester}
                onChange={(e) => setSemester(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground"
              >
                {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
                  <option key={s} value={s}>
                    Semester {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-medium text-foreground mb-1">Document Type</label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground capitalize"
              >
                {DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-medium text-foreground mb-1">Academic Year</label>
              <input
                type="text"
                value={academicYear}
                onChange={(e) => setAcademicYear(e.target.value)}
                placeholder="2026-27"
                required
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground"
              />
            </div>
          </div>

          <div>
            <label className="block font-medium text-foreground text-xs mb-1">Subject Title</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Database Management Systems, Computer Networks"
              required
              className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs"
            />
          </div>

          <div className="flex items-center justify-between pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-foreground">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>Set as active document (searchable by students)</span>
            </label>

            <button
              type="submit"
              disabled={!file || uploading}
              className="flex items-center gap-2 whitespace-nowrap px-5 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-md shadow-primary/20"
            >
              {uploading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Ingesting PDF…
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5" /> Start Ingestion
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Filter and Documents Table */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground text-sm flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary-500" />
              Indexed Documents ({documents.length})
            </h3>
            <button
              onClick={loadDocs}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              title="Refresh list"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {/* Quick Filters */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground flex items-center gap-1">
              <Filter className="w-3 h-3" /> Filter:
            </span>
            <select
              value={filterDept}
              onChange={(e) => setFilterDept(e.target.value)}
              className="px-2.5 py-1 rounded-lg border border-border bg-background text-foreground"
            >
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>

            <select
              value={filterSem ?? ""}
              onChange={(e) => setFilterSem(e.target.value ? Number(e.target.value) : null)}
              className="px-2.5 py-1 rounded-lg border border-border bg-background text-foreground"
            >
              <option value="">All Semesters</option>
              {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
                <option key={s} value={s}>
                  Sem {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Table Box */}
        <div className="border border-border rounded-2xl overflow-hidden glass-card">
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="bg-secondary/60 border-b border-border text-foreground font-semibold">
                  <th className="p-3.5">Subject & Filename</th>
                  <th className="p-3.5">Scope</th>
                  <th className="p-3.5">Type</th>
                  <th className="p-3.5">Ingestion Status</th>
                  <th className="p-3.5">Searchable</th>
                  <th className="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {documents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-muted-foreground">
                      No documents found for this filter.
                    </td>
                  </tr>
                ) : (
                  documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-secondary/30 transition-colors">
                      <td className="p-3.5">
                        <div className="font-semibold text-foreground">{doc.subject}</div>
                        <div className="text-[11px] text-muted-foreground truncate max-w-xs">
                          {doc.original_filename} ({formatBytes(doc.file_size_bytes)})
                        </div>
                      </td>
                      <td className="p-3.5">
                        <span className="font-medium text-foreground">
                          Sem {doc.semester} • {doc.department}
                        </span>
                        <div className="text-[10px] text-muted-foreground">{doc.academic_year}</div>
                      </td>
                      <td className="p-3.5">
                        <span className="px-2 py-0.5 rounded-full capitalize text-[10px] font-medium bg-secondary border border-border">
                          {doc.doc_type}
                        </span>
                      </td>
                      <td className="p-3.5">
                        <div className="flex items-center gap-1.5">
                          {doc.ingestion_status === "done" && (
                            <span className="flex items-center gap-1 text-success-500 font-medium">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Done
                            </span>
                          )}
                          {doc.ingestion_status === "queued" && (
                            <span className="flex items-center gap-1 text-primary-500 font-medium">
                              <Clock className="w-3.5 h-3.5 animate-spin" /> Queued
                            </span>
                          )}
                          {doc.ingestion_status === "processing" && (
                            <span className="flex items-center gap-1 text-primary-500 font-medium">
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Processing
                            </span>
                          )}
                          {doc.ingestion_status === "failed" && (
                            <span className="flex items-center gap-1 text-danger-500 font-medium">
                              <AlertTriangle className="w-3.5 h-3.5" /> Failed
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="p-3.5">
                        <button
                          onClick={() => handleToggleActive(doc.id, doc.is_active)}
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold  transition-colors ${
                            doc.is_active
                              ? "bg-success-500/10 text-success-600 dark:text-success-400"
                              : "bg-secondary text-muted-foreground"
                          }`}
                        >
                          {doc.is_active ? "Active" : "Archived"}
                        </button>
                      </td>
                      <td className="p-3.5 text-right space-x-1">
                        <button
                          onClick={() => handleViewStatus(doc.id)}
                          className="p-1.5 rounded-lg border border-border text-foreground hover:bg-secondary transition-colors"
                          title="View Ingestion Progress & Summaries"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleReingest(doc.id)}
                          className="p-1.5 rounded-lg border border-border text-foreground hover:bg-secondary transition-colors"
                          title="Re-ingest"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="p-1.5 rounded-lg border border-border text-danger-500 hover:bg-danger-500/10 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Ingestion Status Detail Modal */}
      {selectedDocStatus && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 animate-in fade-in duration-150">
          <div className="relative w-full max-w-2xl rounded-2xl glass-card overflow-hidden overflow-hidden p-6 space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
                <Layers className="w-4 h-4 text-primary-500" />
                Ingestion Details ({selectedDocStatus.document_id.slice(0, 8)})
              </h3>
              <button
                onClick={() => setSelectedDocStatus(null)}
                className="text-muted-foreground hover:text-foreground text-xs"
              >
                Close ✕
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-xl border border-border bg-secondary/40">
                <span className="text-muted-foreground block text-[10px]  font-bold">Total Pages</span>
                <span className="text-base font-bold text-foreground">{selectedDocStatus.total_pages ?? "N/A"}</span>
              </div>
              <div className="p-3 rounded-xl border border-border bg-secondary/40">
                <span className="text-muted-foreground block text-[10px]  font-bold">Chunks Created</span>
                <span className="text-base font-bold text-primary">{selectedDocStatus.chunks_created}</span>
              </div>
              <div className="p-3 rounded-xl border border-border bg-secondary/40">
                <span className="text-muted-foreground block text-[10px]  font-bold">Chapters Found</span>
                <span className="text-base font-bold text-foreground">{selectedDocStatus.chapters_found}</span>
              </div>
              <div className="p-3 rounded-xl border border-border bg-secondary/40">
                <span className="text-muted-foreground block text-[10px]  font-bold">Summaries Stored</span>
                <span className="text-base font-bold text-success-500">{selectedDocStatus.summaries_generated}</span>
              </div>
            </div>

            {selectedDocStatus.error && (
              <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-500 text-xs">
                <strong>Ingestion Error:</strong> {selectedDocStatus.error}
              </div>
            )}

            {/* Generated Chapter Summaries */}
            <div className="space-y-2 pt-2">
              <h4 className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-primary-500" />
                Auto-Generated Chapter Summaries ({selectedDocSummaries.length})
              </h4>
              {selectedDocSummaries.length === 0 ? (
                <div className="text-xs text-muted-foreground">No summaries generated yet.</div>
              ) : (
                <div className="space-y-2.5 max-h-60 overflow-y-auto">
                  {selectedDocSummaries.map((s, idx) => (
                    <div key={idx} className="p-3 rounded-xl border border-border bg-card/60 text-xs space-y-1">
                      <div className="font-bold text-foreground flex items-center justify-between">
                        <span>Chapter {s.chapter_no}: {s.chapter_title || "Overview"}</span>
                        <span className="text-[10px] text-muted-foreground font-mono">{s.model_used}</span>
                      </div>
                      <p className="text-muted-foreground text-[11px] leading-relaxed line-clamp-3">
                        {s.summary}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
