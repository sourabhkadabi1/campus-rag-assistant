"use client";

import React, { useState } from "react";
import { useApp } from "@/lib/context";
import { Sparkles, Zap, Clock, ShieldCheck, ArrowUpRight } from "lucide-react";
import Link from "next/link";

export function QuotaBadge() {
  const { quota, profile, setIsUpgradeModalOpen } = useApp();
  const [showTooltip, setShowTooltip] = useState(false);

  if (!quota) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary text-xs text-muted-foreground animate-pulse">
        <Clock className="w-3.5 h-3.5" />
        <span>Loading quota...</span>
      </div>
    );
  }

  const reqRemaining = quota.requests_remaining;
  const reqLimit = quota.requests_limit;
  const thinkingLeft = quota.thinking_credits_remaining ?? (profile.is_paid ? 1 : 0);
  const isPaid = profile.is_paid || quota.is_paid;

  const pct = Math.max(0, Math.min(100, (reqRemaining / (reqLimit || 1)) * 100));

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <button
        onClick={() => !isPaid && setIsUpgradeModalOpen(true)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
          isPaid
            ? "bg-gradient-to-r from-amber-500/10 via-purple-500/10 to-indigo-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 hover:border-amber-500/50"
            : reqRemaining <= 2
            ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
            : "bg-secondary/80 border-border hover:bg-secondary text-foreground"
        }`}
      >
        <div className="flex items-center gap-1">
          <Zap className={`w-3.5 h-3.5 ${isPaid ? "text-amber-500" : "text-indigo-500"}`} />
          <span>
            {reqRemaining}/{reqLimit} <span className="hidden sm:inline">units</span>
          </span>
        </div>

        {isPaid && (
          <div className="flex items-center gap-1 pl-1.5 border-l border-amber-500/30 text-purple-600 dark:text-purple-400 font-semibold">
            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
            <span>{thinkingLeft} Thinking</span>
          </div>
        )}

        {!isPaid && (
          <span className="hidden md:flex items-center gap-0.5 text-indigo-600 dark:text-indigo-400 pl-1 border-l border-border hover:underline">
            Upgrade <ArrowUpRight className="w-3 h-3" />
          </span>
        )}
      </button>

      {/* Tooltip Card */}
      {showTooltip && (
        <div className="absolute right-0 top-full mt-2 w-72 p-3.5 rounded-xl glass-card shadow-xl z-50 text-xs space-y-2.5 animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between pb-2 border-b border-border">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-indigo-500" />
              {isPaid ? "Premium Student Plan" : "Free Student Plan"}
            </span>
            <span className="px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider bg-primary/10 text-primary">
              {isPaid ? "Active" : "Free"}
            </span>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between text-muted-foreground">
              <span>Daily question units:</span>
              <span className="font-medium text-foreground">
                {reqRemaining} of {reqLimit} left
              </span>
            </div>
            <div className="w-full bg-secondary rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  pct > 40 ? "bg-indigo-500" : pct > 15 ? "bg-amber-500" : "bg-red-500"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="text-[10px] text-muted-foreground flex justify-between">
              <span>Quick answer: 1 unit</span>
              <span>Detailed answer: 2 units</span>
            </div>
          </div>

          <div className="pt-1.5 border-t border-border space-y-1">
            <div className="flex justify-between text-muted-foreground">
              <span>Tokens today:</span>
              <span className="font-medium text-foreground">
                {quota.tokens_used.toLocaleString()} / {quota.tokens_limit.toLocaleString()}
              </span>
            </div>
            {isPaid && (
              <div className="flex justify-between text-muted-foreground">
                <span>Thinking reasoning credit:</span>
                <span className="font-medium text-purple-500">
                  {thinkingLeft} available today
                </span>
              </div>
            )}
            <div className="flex justify-between text-muted-foreground">
              <span>Free instant summaries:</span>
              <span className="font-medium text-emerald-500">Unlimited (0 quota)</span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-border text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" /> Resets midnight UTC
            </span>
            {!isPaid && (
              <button
                onClick={() => setIsUpgradeModalOpen(true)}
                className="text-primary font-semibold hover:underline"
              >
                Upgrade now →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
