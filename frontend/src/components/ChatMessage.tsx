"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Message } from "@/lib/types";
import { CitationCard } from "./CitationCard";
import { useApp } from "@/lib/context";
import {
  Sparkles,
  Bot,
  User,
  Copy,
  Check,
  Brain,
  Zap,
  Bookmark,
  AlertCircle,
  Clock,
  ArrowRight,
} from "lucide-react";

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { setIsUpgradeModalOpen } = useApp();
  const [copied, setCopied] = useState(false);
  const [codeCopiedIndex, setCodeCopiedIndex] = useState<number | null>(null);

  const isAssistant = message.role === "assistant";

  const handleCopyText = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyCode = (codeStr: string, idx: number) => {
    navigator.clipboard.writeText(codeStr);
    setCodeCopiedIndex(idx);
    setTimeout(() => setCodeCopiedIndex(null), 2000);
  };

  if (!isAssistant) {
    return (
      <div className="flex justify-end gap-3 max-w-4xl mx-auto w-full group">
        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tr-sm p-4 bg-primary text-primary-foreground shadow-md">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        </div>
        <div className="w-8 h-8 rounded-full bg-secondary text-foreground flex items-center justify-center shrink-0 border border-border mt-0.5">
          <User className="w-4 h-4 text-muted-foreground" />
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex gap-3 sm:gap-4 max-w-4xl mx-auto w-full group">
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5 shadow-sm ${
          message.thinking_mode
            ? "bg-secondary   text-white"
            : "bg-secondary   text-white"
        }`}
      >
        {message.thinking_mode ? (
          <Brain className="w-4 h-4 " />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>

      {/* Bubble */}
      <div className="flex-1 space-y-3 min-w-0">
        {/* Route / Metadata Badges */}
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {message.route === "summary" && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-success-500/10 text-success-600 dark:text-success-400 border border-success-500/20">
              <Zap className="w-3 h-3" /> Chapter Summary, no quota
            </span>
          )}

          {message.route === "syllabus" && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-primary-500/10 text-primary-600 dark:text-primary-400 border border-primary-500/20">
              <Bookmark className="w-3 h-3" /> Official Syllabus, no quota
            </span>
          )}

          {message.route === "cache" && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-secondary text-muted-foreground border border-border">
              <Clock className="w-3 h-3" /> Cached Answer • 0 quota
            </span>
          )}

          {message.thinking_mode && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-semibold bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 shadow-sm">
              <Brain className="w-3 h-3 text-primary-500" /> Deep Reasoning (Thinking Mode)
            </span>
          )}

          {message.detected_detailed && !message.thinking_mode && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-primary-500/10 text-primary-500 border border-primary-500/20">
              Detailed Scope (2 units)
            </span>
          )}

          {message.model_used && (
            <span className="text-[10px] text-muted-foreground px-2 py-0.5 rounded bg-secondary/50">
              {message.model_used}
            </span>
          )}
        </div>

        {/* Content Box */}
        <div className="relative p-5 rounded-2xl rounded-tl-sm glass-card border border-border text-foreground space-y-3 shadow-sm">
          {message.content ? (
            <div className="prose-custom text-sm text-foreground/95">
              <ReactMarkdown
                remarkPlugins={[remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  code({ node, inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || "");
                    const codeText = String(children).replace(/\n$/, "");

                    if (!inline && match) {
                      const codeIdx = Math.floor(Math.random() * 10000);
                      return (
                        <div className="relative my-3 rounded-xl overflow-hidden border border-border bg-code-950 text-code-100 font-mono text-xs">
                          <div className="flex items-center justify-between px-3.5 py-1.5 bg-code-900 border-b border-code-800 text-code-400 text-[11px]">
                            <span className=" font-semibold ">
                              {match[1]}
                            </span>
                            <button
                              onClick={() => handleCopyCode(codeText, codeIdx)}
                              className="flex items-center gap-1 hover:text-white transition-colors"
                            >
                              {codeCopiedIndex === codeIdx ? (
                                <>
                                  <Check className="w-3 h-3 text-success-400" /> Copied
                                </>
                              ) : (
                                <>
                                  <Copy className="w-3 h-3" /> Copy
                                </>
                              )}
                            </button>
                          </div>
                          <pre className="p-3.5 overflow-x-auto">
                            <code>{codeText}</code>
                          </pre>
                        </div>
                      );
                    }

                    return (
                      <code
                        className="px-1.5 py-0.5 rounded bg-secondary text-primary font-mono text-xs"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>

              {message.isStreaming && (
                <span className="inline-block w-1.5 h-4 ml-1 bg-primary  align-middle" />
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground  py-2">
              <Sparkles className="w-4 h-4 text-primary animate-spin" />
              <span>Analyzing semester documents and reasoning…</span>
            </div>
          )}

          {/* Bottom Action Row */}
          {message.content && !message.isStreaming && (
            <div className="pt-2 border-t border-border/60 flex items-center justify-between text-xs text-muted-foreground">
              <span className="text-[11px]">
                {message.tokens_used ? `~${message.tokens_used} tokens generated` : "Grounded answer"}
              </span>

              <button
                onClick={handleCopyText}
                className="flex items-center gap-1 hover:text-foreground transition-colors p-1 rounded hover:bg-secondary"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-success-500" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Answer</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Upgrade / Thinking Hint Banner */}
        {message.hint && (
          <div
            className={`flex items-center justify-between p-3 rounded-xl border text-xs ${
              message.hint === "upgrade_for_thinking"
                ? "bg-secondary   to-transparent border-primary-500/30 text-primary-700 dark:text-primary-300"
                : "bg-primary-500/10 border-primary-500/20 text-primary-700 dark:text-primary-300"
            }`}
          >
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-primary-500 shrink-0" />
              <span>
                {message.hint === "upgrade_for_thinking"
                  ? "Complex question detected. Unlock Gemini Flash Thinking for deep multi-step derivations and proofs."
                  : "You have 1 Thinking credit available today! Toggle Thinking Mode for deep derivations."}
              </span>
            </div>

            {message.hint === "upgrade_for_thinking" && (
              <button
                onClick={() => setIsUpgradeModalOpen(true)}
                className="flex items-center gap-1 font-semibold text-primary hover:underline shrink-0 ml-3"
              >
                Upgrade <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
        )}

        {/* Citations Grid */}
        {message.citations && message.citations.length > 0 && (
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground">
              <span className="flex items-center gap-1.5  ">
                <Bookmark className="w-3.5 h-3.5 text-primary-500" /> Grounded In {message.citations.length} Semester Sources
              </span>
              <span className="text-[10px] text-muted-foreground font-normal">
                Click any source to preview verified PDF page
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
              {message.citations.map((c, idx) => (
                <CitationCard key={idx} citation={c} index={idx} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
