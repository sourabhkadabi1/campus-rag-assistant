"use client";

import React, { useEffect, useState } from "react";
import { ChatSession } from "@/lib/types";
import { useApp } from "@/lib/context";
import { listChatSessions, createChatSession, deleteChatSession } from "@/lib/api";
import {
  Plus,
  MessageSquare,
  Trash2,
  BookOpen,
  GraduationCap,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
} from "lucide-react";

interface SidebarProps {
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onQuickPrompt: (prompt: string, detailed?: boolean) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

export function Sidebar({
  currentSessionId,
  onSelectSession,
  onNewSession,
  onQuickPrompt,
  isOpen,
  setIsOpen,
}: SidebarProps) {
  const { profile } = useApp();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(false);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const res = await listChatSessions(profile);
      setSessions(res.sessions || []);
    } catch (e) {
      console.warn("Failed to load sessions", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, [profile, currentSessionId]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteChatSession(id, profile);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (currentSessionId === id) {
        onNewSession();
      }
    } catch (err) {
      console.warn("Failed to delete session", err);
    }
  };

  const samplePrompts = [
    { title: "Summarize Chapter 2", detailed: false, desc: "Instant chapter summary (0 quota)" },
    { title: "Explain Normalization step by step", detailed: true, desc: "Detailed breakdown (2 units)" },
    { title: "Syllabus of Unit 1", detailed: false, desc: "Official syllabus lookup" },
    { title: "Derive Time Complexity with proof", detailed: true, desc: "Deep multi-step reasoning" },
  ];

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 left-4 z-30 p-3 rounded-2xl glass-card shadow-lg border border-border text-foreground hover:bg-secondary transition-colors"
        title="Open Sidebar"
      >
        <ChevronRight className="w-5 h-5 text-primary" />
      </button>
    );
  }

  return (
    <aside className="w-72 shrink-0 border-r border-border bg-card/60 backdrop-blur-md flex flex-col justify-between h-[calc(100vh-4rem)] transition-colors">
      <div className="p-4 space-y-4 flex-1 overflow-y-auto">
        {/* New Chat Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={onNewSession}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl font-medium text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            New Chat Session
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2.5 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        {/* Current Academic Scope Card */}
        <div className="p-3 rounded-xl border border-border bg-secondary/40 space-y-1.5 text-xs">
          <div className="flex items-center justify-between text-muted-foreground font-semibold text-[10px]  ">
            <span className="flex items-center gap-1">
              <GraduationCap className="w-3.5 h-3.5 text-primary-500" /> Grounded Filter
            </span>
            <span className="text-success-500 font-bold">Active</span>
          </div>
          <p className="text-foreground font-semibold">
            Semester {profile.semester} • {profile.department}
          </p>
          <p className="text-[11px] text-muted-foreground leading-tight">
            Queries only retrieve admin-approved textbooks & syllabus for your current semester.
          </p>
        </div>

        {/* Sessions List */}
        <div className="space-y-1">
          <span className="text-[10px] font-bold   text-muted-foreground px-2 block">
            Recent Conversations
          </span>

          <div className="space-y-1">
            {sessions.length === 0 ? (
              <div className="p-3 text-center text-xs text-muted-foreground">
                No past sessions yet
              </div>
            ) : (
              sessions.map((session) => {
                const isActive = session.id === currentSessionId;
                return (
                  <div
                    key={session.id}
                    onClick={() => onSelectSession(session.id)}
                    className={`group flex items-center justify-between p-2.5 rounded-xl text-xs font-medium cursor-pointer transition-colors ${
                      isActive
                        ? "bg-secondary text-primary font-semibold border border-primary/20 shadow-sm"
                        : "text-foreground/80 hover:bg-secondary/60 hover:text-foreground"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                      <span className="truncate">{session.title || "Study Session"}</span>
                    </div>

                    <button
                      onClick={(e) => handleDelete(e, session.id)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-danger-500 transition-opacity"
                      title="Delete session"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Suggested Quick Prompts */}
        <div className="pt-2 border-t border-border space-y-2">
          <span className="text-[10px] font-bold   text-muted-foreground px-2 block">
            Curriculum Shortcuts
          </span>

          <div className="space-y-1.5">
            {samplePrompts.map((p, idx) => (
              <button
                key={idx}
                onClick={() => onQuickPrompt(p.title, p.detailed)}
                className="w-full text-left p-2 rounded-xl border border-border/60 hover:border-primary/40 bg-card/40 hover:bg-secondary/60 transition-colors text-xs group"
              >
                <div className="font-medium text-foreground group-hover:text-primary transition-colors flex items-center justify-between">
                  <span>{p.title}</span>
                  <Sparkles className="w-3 h-3 text-muted-foreground group-hover:text-primary-500" />
                </div>
                <div className="text-[10px] text-muted-foreground">{p.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-border text-[11px] text-muted-foreground flex items-center justify-between">
        <span>PESU College Assistant</span>
        <span className="font-mono text-[10px]">v0.5.0</span>
      </div>
    </aside>
  );
}
