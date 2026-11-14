"use client";

import React, { useState } from "react";
import { useApp } from "@/lib/context";
import {
  Sparkles,
  Check,
  Zap,
  ArrowRight,
  ShieldCheck,
  HelpCircle,
  Brain,
  Clock,
  BookOpen,
} from "lucide-react";

export default function PricingPage() {
  const { profile, setIsUpgradeModalOpen } = useApp();
  const [billingCycle, setBillingCycle] = useState<"monthly" | "semester">("monthly");

  return (
    <div className="flex-1 overflow-y-auto py-12 px-4 sm:px-6 max-w-6xl mx-auto space-y-16">
      {/* Hero Header */}
      <div className="text-center space-y-4 max-w-2xl mx-auto">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
          <Sparkles className="w-3.5 h-3.5" /> Transparent College Plans
        </span>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight">
          Supercharge your study sessions
        </h1>
        <p className="text-sm sm:text-base text-muted-foreground">
          Grounded course answers, exact book citations, and deep mathematical reasoning built specifically for college exams.
        </p>

        {/* Billing Switcher */}
        <div className="pt-2 flex justify-center">
          <div className="flex items-center p-1 rounded-xl bg-secondary border border-border text-xs font-medium">
            <button
              onClick={() => setBillingCycle("monthly")}
              className={`px-4 py-2 rounded-lg transition-all ${
                billingCycle === "monthly"
                  ? "bg-background text-foreground shadow-sm font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Monthly billing
            </button>
            <button
              onClick={() => setBillingCycle("semester")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg transition-all ${
                billingCycle === "semester"
                  ? "bg-background text-foreground shadow-sm font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Semester pass
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 font-bold">
                Save 25%
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Pricing Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto items-stretch">
        {/* Free Plan */}
        <div className="p-8 rounded-3xl border border-border bg-card/60 backdrop-blur-md flex flex-col justify-between space-y-8 shadow-sm">
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-foreground">Free Plan</h3>
                <p className="text-xs text-muted-foreground">Everything needed for daily prep</p>
              </div>
              <div className="text-3xl font-extrabold text-foreground">₹0</div>
            </div>

            <div className="pt-4 border-t border-border space-y-3.5 text-xs text-foreground/90">
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>
                  <strong>10 question units every day</strong> (1 unit for quick answers, 2 units for detailed step-by-step answers)
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>
                  <strong>40,000 tokens daily limit</strong>
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>
                  Full access to all uploaded textbooks, lecture notes, and syllabus materials for your semester
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>Exact book & page citations with every answer</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>Instant chapter & unit summaries (free, zero quota consumed)</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <span>Automatic resets every night at midnight UTC</span>
              </div>
            </div>
          </div>

          <button
            disabled={!profile.is_paid}
            onClick={() => {}}
            className={`w-full py-3 rounded-2xl text-xs font-semibold transition-all ${
              !profile.is_paid
                ? "bg-secondary text-muted-foreground border border-border cursor-default"
                : "border border-border text-foreground hover:bg-secondary"
            }`}
          >
            {!profile.is_paid ? "Current Active Plan" : "Switch to Free"}
          </button>
        </div>

        {/* Premium Plan */}
        <div className="relative p-8 rounded-3xl border-2 border-primary bg-gradient-to-b from-primary/10 via-card to-card flex flex-col justify-between space-y-8 shadow-2xl shadow-primary/15">
          <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-gradient-to-r from-amber-500 to-purple-600 text-white shadow-md">
            Recommended for Exams
          </div>

          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-foreground flex items-center gap-2">
                  Premium Plan <Sparkles className="w-5 h-5 text-amber-500" />
                </h3>
                <p className="text-xs text-muted-foreground">Deep reasoning & priority queue</p>
              </div>

              <div className="text-right">
                <div className="text-3xl font-extrabold text-foreground">
                  {billingCycle === "monthly" ? "₹99" : "₹449"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {billingCycle === "monthly" ? "/ month" : "/ semester"}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-border space-y-3.5 text-xs text-foreground/90">
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                <span>
                  <strong>30 question units every day</strong> (up to 30 normal or 15 detailed questions)
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                <span>
                  <strong>100,000 tokens daily limit</strong>
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Brain className="w-4 h-4 text-purple-500 shrink-0 mt-0.5" />
                <span>
                  <strong>1 Thinking Mode question per day</strong> — deep reasoning powered by Gemini Flash Thinking for complex derivations, numericals, and proofs
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Zap className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                <span>
                  <strong>Priority Queue</strong> — your questions are answered first during high-demand exam weeks
                </span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                <span>Longer, more comprehensive answers (up to 2,000 output tokens)</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                <span>Quiz and practice question generation</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                <span>Guaranteed access even during peak campus traffic</span>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <button
              onClick={() => setIsUpgradeModalOpen(true)}
              className="w-full py-3.5 rounded-2xl font-semibold text-xs text-white bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 hover:opacity-95 transition-all shadow-lg shadow-indigo-500/25 flex items-center justify-center gap-2"
            >
              {profile.is_paid ? "Active Subscription" : "Upgrade to Premium"}
              <ArrowRight className="w-4 h-4" />
            </button>
            <div className="text-center text-[10px] text-muted-foreground flex items-center justify-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              Razorpay Secured • Cancel anytime
            </div>
          </div>
        </div>
      </div>

      {/* Feature Comparison Matrix */}
      <div className="max-w-4xl mx-auto space-y-6 pt-8">
        <h2 className="text-xl font-bold text-foreground text-center">Feature Breakdown</h2>

        <div className="rounded-2xl border border-border overflow-hidden bg-card/60">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="bg-secondary/60 border-b border-border text-foreground font-semibold">
                <th className="p-4">Capability</th>
                <th className="p-4 w-40 text-center">Free Plan</th>
                <th className="p-4 w-40 text-center text-primary font-bold">Premium Plan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              <tr>
                <td className="p-4 font-medium">Daily Question Units</td>
                <td className="p-4 text-center text-muted-foreground">10 units/day</td>
                <td className="p-4 text-center font-bold text-foreground">30 units/day</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Daily Token Allowance</td>
                <td className="p-4 text-center text-muted-foreground">40,000 tokens</td>
                <td className="p-4 text-center font-bold text-foreground">100,000 tokens</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Gemini Flash Thinking Mode</td>
                <td className="p-4 text-center text-muted-foreground">—</td>
                <td className="p-4 text-center font-bold text-purple-500">1 Credit / day</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Exam Queue Priority</td>
                <td className="p-4 text-center text-muted-foreground">Standard Queue</td>
                <td className="p-4 text-center font-bold text-amber-500">Fast-track Priority</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Max Output Length</td>
                <td className="p-4 text-center text-muted-foreground">600–1,000 tokens</td>
                <td className="p-4 text-center font-bold text-foreground">800–2,000 tokens</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Textbook & Notes Citations</td>
                <td className="p-4 text-center text-emerald-500">Included</td>
                <td className="p-4 text-center text-emerald-500">Included</td>
              </tr>
              <tr>
                <td className="p-4 font-medium">Instant Chapter Summaries</td>
                <td className="p-4 text-center text-emerald-500">Unlimited (0 quota)</td>
                <td className="p-4 text-center text-emerald-500">Unlimited (0 quota)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* FAQ Section */}
      <div className="max-w-3xl mx-auto space-y-6 pt-6">
        <h2 className="text-xl font-bold text-foreground text-center">Frequently Asked Questions</h2>

        <div className="space-y-3">
          <div className="p-4 rounded-2xl border border-border bg-card/60 space-y-1">
            <h4 className="text-xs font-semibold text-foreground">What is a question unit?</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Standard conceptual queries consume 1 unit. Comprehensive, derivation-heavy, or code-heavy queries (&gt;40 words or matching keywords like &apos;in detail&apos; or &apos;step by step&apos;) consume 2 units.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-border bg-card/60 space-y-1">
            <h4 className="text-xs font-semibold text-foreground">Do chapter summaries consume quota?</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              No! Stored chapter summaries and syllabus lookups cost zero units and zero tokens, allowing you to review syllabus outlines and chapter recaps without limit.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-border bg-card/60 space-y-1">
            <h4 className="text-xs font-semibold text-foreground">What is Thinking Mode?</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Thinking Mode utilizes Google Gemini Flash Thinking models to work through complex mathematical derivations, circuit analysis, and architectural comparisons step-by-step with chain-of-thought verification before answering.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
