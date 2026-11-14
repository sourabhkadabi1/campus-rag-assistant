"use client";

import React from "react";
import { Citation } from "@/lib/types";
import { BookOpen, FileText, ExternalLink, Bookmark } from "lucide-react";
import { useApp } from "@/lib/context";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const { openPdfPreview } = useApp();

  const getDocTypeColor = (type: string) => {
    switch (type.toLowerCase()) {
      case "book":
        return "bg-blue-500/10 text-blue-500 border-blue-500/20";
      case "syllabus":
        return "bg-emerald-500/10 text-emerald-500 border-emerald-500/20";
      case "notes":
        return "bg-amber-500/10 text-amber-500 border-amber-500/20";
      case "previous_paper":
        return "bg-purple-500/10 text-purple-500 border-purple-500/20";
      default:
        return "bg-secondary text-muted-foreground border-border";
    }
  };

  return (
    <div
      onClick={() => openPdfPreview(citation)}
      className="group relative flex flex-col justify-between p-3 rounded-xl border border-border bg-card/70 hover:bg-secondary/70 hover:border-primary/40 cursor-pointer transition-all duration-200 shadow-sm hover:shadow"
    >
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
            <Bookmark className="w-3 h-3 text-indigo-500" /> Source [{index + 1}]
          </span>
          <span
            className={`text-[10px] font-medium px-2 py-0.5 rounded-full border capitalize ${getDocTypeColor(
              citation.doc_type
            )}`}
          >
            {citation.doc_type}
          </span>
        </div>

        <h4 className="text-xs font-semibold text-foreground line-clamp-1 group-hover:text-primary transition-colors">
          {citation.subject}
        </h4>

        {citation.chapter_no !== null && (
          <p className="text-[11px] text-muted-foreground line-clamp-1">
            Chapter {citation.chapter_no}
            {citation.chapter_title ? `: ${citation.chapter_title}` : ""}
          </p>
        )}
      </div>

      <div className="mt-2 pt-2 border-t border-border flex items-center justify-between text-[11px]">
        <span className="font-medium text-foreground/80 flex items-center gap-1">
          <BookOpen className="w-3 h-3 text-muted-foreground" />
          {citation.page_start
            ? citation.page_end && citation.page_end !== citation.page_start
              ? `pp. ${citation.page_start}–${citation.page_end}`
              : `p. ${citation.page_start}`
            : "Reference page"}
        </span>

        <span className="text-[10px] text-primary flex items-center gap-0.5 opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all">
          View PDF <ExternalLink className="w-2.5 h-2.5" />
        </span>
      </div>
    </div>
  );
}
