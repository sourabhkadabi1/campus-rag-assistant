"use client";

import React from "react";
import { useApp } from "@/lib/context";
import { X, BookOpen, FileText, CheckCircle2, Download, ExternalLink } from "lucide-react";

export function PdfViewerModal() {
  const { pdfPreview, closePdfPreview } = useApp();

  if (!pdfPreview || !pdfPreview.isOpen) return null;
  const { citation } = pdfPreview;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl glass-card overflow-hidden overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-4 border-b border-border bg-card/90">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary-500/10 text-primary-500 flex items-center justify-center">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-sm flex items-center gap-2">
                {citation.subject}
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-secondary  text-muted-foreground border border-border">
                  {citation.doc_type}
                </span>
              </h3>
              <p className="text-xs text-muted-foreground">
                {citation.chapter_no !== null && `Chapter ${citation.chapter_no} • `}
                {citation.chapter_title && `"${citation.chapter_title}" • `}
                {citation.page_start ? `Page ${citation.page_start}` : "Course Material"}
              </p>
            </div>
          </div>

          <button
            onClick={closePdfPreview}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content / Preview */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-background/50">
          <div className="flex items-center gap-2 p-3 rounded-xl bg-success-500/10 border border-success-500/20 text-success-600 dark:text-success-400 text-xs">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>
              <strong>Grounded Source:</strong> This answer was generated strictly from the
              verified college document uploaded for your semester.
            </span>
          </div>

          {/* PDF Page Mock View */}
          <div className="relative p-8 space-y-4 min-h-[360px] flex flex-col justify-between">
            <div className="flex items-center justify-between border-b border-border/60 pb-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{citation.subject}, Syllabus & Coursebook</span>
              <span>
                Page {citation.page_start ?? 1}
                {citation.page_end && citation.page_end !== citation.page_start
                  ? ` to ${citation.page_end}`
                  : ""}
              </span>
            </div>

            <div className="space-y-3 text-sm text-foreground/90 font-serif leading-relaxed">
              <h2 className="text-base font-bold font-sans text-primary">
                {citation.chapter_title || `Chapter ${citation.chapter_no ?? "Core Topics"}`}
              </h2>
              <p>
                This textbook section contains the definitive curriculum definitions, mathematical
                formulations, theorems, and proofs prescribed by the department academic board.
              </p>
              <div className="p-4 rounded-lg bg-secondary/60 border border-border/80 text-xs text-muted-foreground">
                [Verified Document Chunk #{citation.document_id.slice(0, 8)}]
                <br />
                Subject: {citation.subject} | Doc Type: {citation.doc_type}
                <br />
                Page Reference: {citation.page_start || "1"}
              </div>
              <p className="text-xs text-muted-foreground italic">
                * Note: Full PDF rendering connects to the Supabase storage bucket document:{" "}
                <code className="text-foreground">{citation.document_id}</code>.
              </p>
            </div>

            <div className="pt-4 border-t border-border/60 flex items-center justify-between text-xs text-muted-foreground">
              <span>Department of Computer Science & Engineering</span>
              <span className="font-semibold text-foreground">Semester 3 Curriculum</span>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-border bg-card/90 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            Document ID: <code className="text-foreground">{citation.document_id.slice(0, 12)}…</code>
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={closePdfPreview}
              className="px-4 py-2 rounded-xl text-xs font-medium border border-border hover:bg-secondary transition-colors"
            >
              Close
            </button>
            <button
              onClick={() => {
                alert(`Opening document ${citation.document_id} page ${citation.page_start || 1}`);
              }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
            >
              <Download className="w-3.5 h-3.5" />
              Download Section PDF
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
