"use client";

import React, { useState, useRef, useEffect } from "react";
import { Message, Citation } from "@/lib/types";
import { useApp } from "@/lib/context";
import { Sidebar } from "@/components/Sidebar";
import { ChatMessage } from "@/components/ChatMessage";
import {
  askQuestionStream,
  createChatSession,
  getSessionMessages,
  addSessionMessage,
} from "@/lib/api";
import {
  Send,
  Sparkles,
  Brain,
  Zap,
  Bookmark,
  GraduationCap,
  Layers,
  StopCircle,
  Clock,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";

const DETAILED_KEYWORDS = [
  "in detail",
  "step by step",
  "derive",
  "prove",
  "compare",
  "with example",
  "write code",
  "numerical",
];

export default function StudentChatPage() {
  const { profile, quota, refreshQuota, setIsUpgradeModalOpen } = useApp();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuestion, setInputQuestion] = useState("");
  const [isDetailed, setIsDetailed] = useState(false);
  const [useThinking, setUseThinking] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [queueInfo, setQueueInfo] = useState<{
    position: number;
    estimatedSeconds?: number;
  } | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-detect detailed question as student types
  const lowerInput = inputQuestion.toLowerCase();
  const wordCount = inputQuestion.trim().split(/\s+/).filter(Boolean).length;
  const isAutoDetailed =
    DETAILED_KEYWORDS.some((kw) => lowerInput.includes(kw)) || wordCount > 40;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (messages.length > 0 || queueInfo) scrollToBottom();
  }, [messages, queueInfo]);

  useEffect(() => {
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  }, []);

  // Handle switching sessions
  const handleSelectSession = async (newSessionId: string) => {
    setSessionId(newSessionId);
    try {
      const res = await getSessionMessages(newSessionId, profile);
      setMessages(res.messages || []);
    } catch (e) {
      console.warn("Failed to load session messages", e);
    }
  };

  // Start new clean session
  const handleNewSession = () => {
    setSessionId(null);
    setMessages([]);
    setQueueInfo(null);
  };

  // Quick prompt triggered from sidebar
  const handleQuickPrompt = (prompt: string, detailed = false) => {
    setInputQuestion(prompt);
    setIsDetailed(detailed);
    textareaRef.current?.focus();
  };

  // Send question
  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = inputQuestion.trim();
    if (!q || isStreaming) return;

    // Check if thinking mode is toggled by free user
    if (useThinking && !profile.is_paid) {
      setIsUpgradeModalOpen(true);
      return;
    }

    // Ensure session exists
    let activeSessionId = sessionId;
    if (!activeSessionId) {
      try {
        const titleSnippet = q.slice(0, 30) + (q.length > 30 ? "…" : "");
        const newSession = await createChatSession(profile, titleSnippet);
        activeSessionId = newSession.id;
        setSessionId(activeSessionId);
      } catch (err) {
        console.warn("Could not create remote session", err);
      }
    }

    const userMessage: Message = {
      id: "u_" + Date.now(),
      role: "user",
      content: q,
      created_at: new Date().toISOString(),
    };

    const assistantPlaceholder: Message = {
      id: "a_" + Date.now(),
      role: "assistant",
      content: "",
      isStreaming: true,
      thinking_mode: useThinking && profile.is_paid,
      detected_detailed: isAutoDetailed || isDetailed,
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInputQuestion("");
    setIsStreaming(true);
    setQueueInfo(null);

    // Save user message to backend DB
    if (activeSessionId) {
      addSessionMessage(activeSessionId, { role: "user", content: q }, profile);
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    let accumulatedContent = "";
    let accumulatedCitations: Citation[] = [];
    let detectedRoute: Message["route"] = "llm";
    let actualThinking = useThinking && profile.is_paid;
    let thinkingReason: string | undefined = undefined;
    let hint: "try_thinking" | "upgrade_for_thinking" | undefined = undefined;

    try {
      await askQuestionStream(
        q,
        profile,
        {
          sessionId: activeSessionId || undefined,
          detailed: isAutoDetailed || isDetailed,
          thinking: useThinking && profile.is_paid,
        },
        {
          onFilter(data) {
            console.log("Parsed filter:", data);
          },
          onRoute(route) {
            detectedRoute = route as Message["route"];
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceholder.id ? { ...m, route: route as Message["route"] } : m
              )
            );
          },
          onQueue(position, estimatedSeconds) {
            setQueueInfo({ position, estimatedSeconds });
          },
          onToken(token) {
            setQueueInfo(null); // token received, departed queue
            accumulatedContent += token;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceholder.id
                  ? { ...m, content: accumulatedContent }
                  : m
              )
            );
          },
          onCitations(citations) {
            accumulatedCitations = citations;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceholder.id ? { ...m, citations } : m
              )
            );
          },
          onDone(doneData) {
            if (doneData.thinking_mode !== undefined) {
              actualThinking = doneData.thinking_mode;
            }
            if (doneData.thinking_reason) {
              thinkingReason = doneData.thinking_reason;
            }
            if (doneData.hint) {
              hint = doneData.hint;
            }
            refreshQuota();
          },
          onError(error) {
            accumulatedContent += `\n\n⚠️ **Error:** ${error}`;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceholder.id
                  ? { ...m, content: accumulatedContent, isStreaming: false }
                  : m
              )
            );
          },
        },
        abortController.signal
      );
    } catch (err: any) {
      if (err.name !== "AbortError") {
        accumulatedContent += `\n\n⚠️ An error occurred while communicating with the assistant.`;
      }
    } finally {
      setIsStreaming(false);
      setQueueInfo(null);
      abortControllerRef.current = null;

      // Finalize assistant message
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantPlaceholder.id
            ? {
                ...m,
                content: accumulatedContent,
                citations: accumulatedCitations,
                isStreaming: false,
                thinking_mode: actualThinking,
                thinking_reason: thinkingReason,
                hint,
                route: detectedRoute,
              }
            : m
        )
      );

      // Record assistant response to chat history
      if (activeSessionId && accumulatedContent) {
        addSessionMessage(
          activeSessionId,
          {
            role: "assistant",
            content: accumulatedContent,
            citations: accumulatedCitations,
          },
          profile
        );
      }
    }
  };

  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  };

  return (
    <div className="study-app flex-1 flex overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        currentSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onQuickPrompt={handleQuickPrompt}
        isOpen={isSidebarOpen}
        setIsOpen={setIsSidebarOpen}
      />

      {/* Main Chat Area */}
      <div className="study-chat flex-1 flex flex-col h-[calc(100vh-4rem)] bg-background overflow-hidden relative">
        {/* Messages Scroll Area */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 space-y-6">
          {messages.length === 0 ? (
            /* Empty State Hero */
            <div className="study-home max-w-4xl mx-auto my-auto py-10 px-4 space-y-7">
              <div className="study-mark w-12 h-12 bg-secondary    text-white flex items-center justify-center">
                <GraduationCap className="w-8 h-8" />
              </div>

              <div className="study-heading space-y-3">
                <h1 className="text-4xl sm:text-6xl font-extrabold text-foreground ">
                  Find it in your course notes
                </h1>
                <p className="text-sm text-muted-foreground max-w-lg mx-auto">
                  Ask questions grounded exclusively in your verified{" "}
                  <strong>Semester {profile.semester} ({profile.department})</strong> course books, syllabus, and lecture notes.
                </p>
              </div>

              {/* Feature Pill Grid */}
              <div className="study-proof grid grid-cols-1 sm:grid-cols-3 gap-5 text-left">
                <div className="p-3.5 rounded-xl border border-border bg-card/60 space-y-1">
                  <div className="flex items-center gap-2 text-primary-500 font-semibold text-xs">
                    <Bookmark className="w-4 h-4" /> Exact Citations
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Every answer is linked with page numbers to uploaded textbooks.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card/60 space-y-1">
                  <div className="flex items-center gap-2 text-success-500 font-semibold text-xs">
                    <Zap className="w-4 h-4" /> Instant Summaries
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Chapter and unit summaries serve instantly with 0 quota consumed.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card/60 space-y-1">
                  <div className="flex items-center gap-2 text-primary-500 font-semibold text-xs">
                    <Brain className="w-4 h-4" /> Deep Thinking
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Gemini Flash Thinking solves complex mathematical derivations.
                  </p>
                </div>
              </div>

              {/* Suggested Questions */}
              <div className="study-prompts pt-2">
                <span className="text-[11px] font-semibold text-muted-foreground   block mb-2">
                  Try asking
                </span>
                <div className="flex flex-wrap justify-center gap-2">
                  {[
                    "Summarize chapter 1",
                    "Explain B+ Trees in detail with example",
                    "What is in Unit 2 syllabus?",
                    "Step by step proof of Master Theorem",
                  ].map((sample, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleQuickPrompt(sample, idx % 2 === 1)}
                      className="px-3 py-1.5 rounded-full border border-border text-xs text-foreground/80 hover:text-foreground hover:bg-secondary transition-colors"
                    >
                      {sample}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Render Message History */
            messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
          )}

          {/* Queue Indicator Banner */}
          {queueInfo && (
            <div className="max-w-4xl mx-auto p-3.5 rounded-2xl border border-primary-500/30 bg-primary-500/10 text-primary-700 dark:text-primary-300 flex items-center justify-between  text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                <Clock className="w-4 h-4 animate-spin text-primary-500" />
                <span>
                  High campus traffic: You are at <strong>position #{queueInfo.position}</strong> in the model request queue.
                </span>
              </div>
              {queueInfo.estimatedSeconds && (
                <span className="text-[11px] font-medium">
                  Est: ~{queueInfo.estimatedSeconds}s wait
                </span>
              )}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Dock Area */}
        <div className="p-4 sm:p-6 border-t border-border bg-card/80 backdrop-blur-md">
          <div className="max-w-4xl mx-auto space-y-2.5">
            {/* Controls Bar above input */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              {/* Left toggles: Detailed & Thinking */}
              <div className="flex items-center gap-2">
                {/* Detailed Mode Indicator / Toggle */}
                <button
                  type="button"
                  onClick={() => setIsDetailed(!isDetailed)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium transition-colors ${
                    isAutoDetailed || isDetailed
                      ? "bg-primary-500/15 text-primary-600 dark:text-primary-400 border-primary-500/30"
                      : "bg-secondary/60 text-muted-foreground border-border hover:text-foreground"
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span>
                    Detailed Scope {isAutoDetailed ? "(Auto-detected • 2 units)" : "(2 units)"}
                  </span>
                </button>

                {/* Thinking Toggle (Paid only) */}
                <button
                  type="button"
                  onClick={() => {
                    if (!profile.is_paid) {
                      setIsUpgradeModalOpen(true);
                    } else {
                      setUseThinking(!useThinking);
                    }
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium transition-colors ${
                    useThinking && profile.is_paid
                      ? "bg-secondary   text-primary-600 dark:text-primary-400 border-primary-500/40 shadow-sm"
                      : "bg-secondary/60 text-muted-foreground border-border hover:text-foreground"
                  }`}
                >
                  <Brain className={`w-3.5 h-3.5 ${useThinking && profile.is_paid ? "text-primary-500 " : ""}`} />
                  <span>Thinking Mode</span>
                  {!profile.is_paid ? (
                    <span className="text-[10px]  font-bold px-1.5 py-0.2 rounded bg-primary-500/15 text-primary-500">
                      Paid
                    </span>
                  ) : (
                    <span className="text-[10px] text-primary-500 font-semibold">
                      (3 units + 1 credit)
                    </span>
                  )}
                </button>
              </div>

              {/* Right: Semester indicator & stop stream */}
              <div className="flex items-center gap-2 text-muted-foreground text-[11px]">
                {isStreaming && (
                  <button
                    onClick={handleStopStreaming}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-danger-500/30 bg-danger-500/10 text-danger-500 hover:bg-danger-500/20 transition-colors"
                  >
                    <StopCircle className="w-3.5 h-3.5" /> Stop Generating
                  </button>
                )}
                <span>
                  Searching <strong>Sem {profile.semester}</strong> documents
                </span>
              </div>
            </div>

            {/* Main Textarea Container */}
            <form onSubmit={handleSend} className="study-input relative flex items-end border border-border bg-background focus-within:ring-2 focus-within:ring-primary focus-within:border-primary overflow-hidden">
              <textarea
                ref={textareaRef}
                value={inputQuestion}
                onChange={(e) => setInputQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={`Ask anything from your Semester ${profile.semester} syllabus (e.g. "derive time complexity", "summarize chapter 2")…`}
                rows={2}
                className="flex-1 p-3.5 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none resize-none max-h-32"
              />

              <div className="p-2 flex items-center gap-2">
                <button
                  type="submit"
                  disabled={!inputQuestion.trim() || isStreaming}
                  className="p-2.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-md shadow-primary/20"
                  title="Send Question"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </form>

            <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
              <span>Shift + Enter for new line • Grounded in approved course material</span>
              <span>
                Daily reset at <strong>midnight UTC</strong>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
