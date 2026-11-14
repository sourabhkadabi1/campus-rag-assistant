"use client";

import React, { useState, useEffect } from "react";
import { MarginDashboardData } from "@/lib/types";
import { fetchMarginDashboard } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  DollarSign,
  TrendingUp,
  AlertTriangle,
  Zap,
  Clock,
  Layers,
  Sparkles,
  RefreshCw,
  ShieldAlert,
  Percent,
} from "lucide-react";

export function MarginDashboard() {
  const [data, setData] = useState<MarginDashboardData | null>(null);
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await fetchMarginDashboard();
      setData(res);
    } catch (err: any) {
      console.warn("Failed to load margin dashboard", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, []);

  if (!data) {
    return (
      <div className="p-8 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin text-primary" />
        <span>Loading Margin Dashboard metrics...</span>
      </div>
    );
  }

  const thinkingSpendPct = Math.min(
    100,
    (data.premium_spend_today_usd / (data.premium_daily_cap_usd || 0.15)) * 100
  );

  return (
    <div className="space-y-6">
      {/* Margin Alert Banner if triggered */}
      {data.margin_alert && (
        <div className="p-4 rounded-2xl bg-red-500/10 border-2 border-red-500/40 text-red-700 dark:text-red-300 flex items-start gap-3 shadow-md animate-pulse">
          <ShieldAlert className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
          <div className="space-y-1 text-xs">
            <h4 className="font-bold text-sm">Critical Margin Warning!</h4>
            <p>
              {data.margin_alert_message ||
                "Average cost per paid user exceeds 40% of net plan price. Review thinking rate caps or model selection."}
            </p>
          </div>
        </div>
      )}

      {/* Top Action / Header */}
      <div className="flex items-center justify-between p-4 rounded-2xl glass-card border border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">API Cost & Margin Analytics</h3>
            <p className="text-xs text-muted-foreground">
              Real-time spend deduction from ACCOUNT_BALANCE_USD based on live token usage.
            </p>
          </div>
        </div>

        <button
          onClick={loadData}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border text-xs font-medium hover:bg-secondary transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Metrics
        </button>
      </div>

      {/* Core KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Remaining Balance */}
        <div className="p-5 rounded-2xl glass-card border border-border space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Remaining Balance</span>
            <DollarSign className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-foreground">
            ${data.remaining_balance_usd.toFixed(2)}
          </div>
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>
              ~<strong>{data.estimated_days_left} days</strong> runway remaining
            </span>
          </div>
        </div>

        {/* Today's Spend */}
        <div className="p-5 rounded-2xl glass-card border border-border space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Today's Spend</span>
            <TrendingUp className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="text-2xl font-extrabold text-foreground">
            {formatCurrency(data.today_spend_usd)}
          </div>
          <div className="text-[11px] text-muted-foreground">
            7-day spend: {formatCurrency(data.seven_day_spend_usd)}
          </div>
        </div>

        {/* Premium / Thinking Spend */}
        <div className="p-5 rounded-2xl glass-card border border-border space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Thinking Mode Spend</span>
            <Sparkles className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-2xl font-extrabold text-foreground font-mono">
            ${data.premium_spend_today_usd.toFixed(4)}
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>Cap: ${data.premium_daily_cap_usd} / day</span>
              <span>{Math.round(thinkingSpendPct)}%</span>
            </div>
            <div className="w-full bg-secondary rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  thinkingSpendPct > 80 ? "bg-red-500" : "bg-purple-500"
                }`}
                style={{ width: `${thinkingSpendPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* Cache Hit Rate */}
        <div className="p-5 rounded-2xl glass-card border border-border space-y-2">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Cache Hit Rate</span>
            <Zap className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl font-extrabold text-foreground">
            {(data.cache_hit_rate * 100).toFixed(1)}%
          </div>
          <div className="text-[11px] text-muted-foreground">
            Zero API cost on cache hits
          </div>
        </div>
      </div>

      {/* Advanced Margin Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Unit Economics Breakdown */}
        <div className="p-6 rounded-2xl glass-card border border-border space-y-4">
          <h4 className="font-semibold text-xs text-foreground flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-500" />
            Unit Economics & Costs
          </h4>

          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-secondary/40">
              <span className="text-muted-foreground">Monthly Plan Price:</span>
              <span className="font-semibold text-foreground">
                ${data.plan_price_monthly_usd.toFixed(2)} (₹99)
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-secondary/40">
              <span className="text-muted-foreground">Avg Cost / Paid User / Month:</span>
              <span
                className={`font-semibold ${
                  data.margin_alert ? "text-red-500" : "text-emerald-500"
                }`}
              >
                ${data.avg_cost_per_paid_user_month.toFixed(4)}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-secondary/40">
              <span className="text-muted-foreground">Detailed Questions Share:</span>
              <span className="font-semibold text-foreground">
                {(data.detailed_share * 100).toFixed(1)}% of total queries
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-secondary/40">
              <span className="text-muted-foreground">Thinking Requests Today:</span>
              <span className="font-semibold text-purple-500">
                {data.thinking_requests_today} calls
              </span>
            </div>
          </div>
        </div>

        {/* Avg Cost per Profile Chart / List */}
        <div className="p-6 rounded-2xl glass-card border border-border space-y-4">
          <h4 className="font-semibold text-xs text-foreground flex items-center gap-2">
            <Percent className="w-4 h-4 text-purple-500" />
            Avg Cost per Query by Profile
          </h4>

          <div className="space-y-3 text-xs">
            <div className="p-4 rounded-xl border border-border bg-secondary/30 space-y-2">
              <div className="flex justify-between font-medium">
                <span className="text-foreground">Free Tier Queries:</span>
                <span className="text-emerald-500 font-bold">$0.000000</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Free queries are strictly routed to free-tier projects (GEMINI_API_KEY_FREE) or local embeddings, generating $0 billing cost.
              </p>
            </div>

            <div className="p-4 rounded-xl border border-border bg-secondary/30 space-y-2">
              <div className="flex justify-between font-medium">
                <span className="text-foreground">Paid Tier Queries:</span>
                <span className="text-indigo-500 font-bold font-mono">
                  ${(data.avg_cost_per_profile["paid"] || 0.00045).toFixed(6)} / req
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Charged models with live prompt budgeting and strict token limits maintain healthy &gt;60% gross profit margins.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
