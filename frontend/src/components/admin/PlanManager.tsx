"use client";

import React, { useState, useEffect } from "react";
import { PlanItem } from "@/lib/types";
import { fetchPlans, grantPlanManual } from "@/lib/api";
import {
  CreditCard,
  UserCheck,
  RefreshCw,
  Sparkles,
  Check,
  Clock,
  Shield,
  Send,
} from "lucide-react";

export function PlanManager() {
  const [plans, setPlans] = useState<PlanItem[]>([]);
  const [loading, setLoading] = useState(false);

  // Manual grant form
  const [grantUserIds, setGrantUserIds] = useState("");
  const [grantPlanName, setGrantPlanName] = useState("paid");
  const [grantDays, setGrantDays] = useState(30);
  const [granting, setGranting] = useState(false);
  const [grantResult, setGrantResult] = useState<any>(null);

  const loadPlans = async () => {
    try {
      setLoading(true);
      const res = await fetchPlans();
      setPlans(res || []);
    } catch (err: any) {
      console.warn("Failed to load plans", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, []);

  const handleGrantSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ids = grantUserIds
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (ids.length === 0) return alert("Please enter at least one User ID");

    try {
      setGranting(true);
      const res = await grantPlanManual(ids, grantPlanName, grantDays);
      setGrantResult(res);
      setGrantUserIds("");
    } catch (err: any) {
      alert("Plan grant failed: " + err.message);
    } finally {
      setGranting(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Plans List Box */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-5">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
              <CreditCard className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Configured Plans & Tiers</h3>
              <p className="text-xs text-muted-foreground">
                Quotas and limits enforced atomically before model invocations.
              </p>
            </div>
          </div>

          <button
            onClick={loadPlans}
            className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-secondary"
            title="Refresh plans"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className={`p-5 rounded-2xl border space-y-3 ${
                plan.name === "paid"
                  ? "bg-gradient-to-tr from-primary/10 via-card to-card border-primary/40 shadow-sm"
                  : "bg-card/60 border-border"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-bold text-sm text-foreground flex items-center gap-1.5">
                    {plan.display_name} Plan
                    {plan.name === "paid" && <Sparkles className="w-3.5 h-3.5 text-amber-500" />}
                  </h4>
                  <span className="text-[10px] text-muted-foreground uppercase font-bold">
                    Identifier: {plan.name}
                  </span>
                </div>

                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                    plan.is_default
                      ? "bg-secondary text-muted-foreground border border-border"
                      : "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                  }`}
                >
                  {plan.is_default ? "Default" : "Premium"}
                </span>
              </div>

              <div className="pt-2 border-t border-border space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Question Units:</span>
                  <span className="font-semibold text-foreground font-mono">
                    {plan.requests_per_day} units / day
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Token Limit:</span>
                  <span className="font-semibold text-foreground font-mono">
                    {plan.tokens_per_day.toLocaleString()} tokens / day
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Thinking Reasoning:</span>
                  <span className="font-semibold text-purple-500 font-mono">
                    {plan.thinking_credits_per_day ?? (plan.name === "paid" ? 1 : 0)} credit / day
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Pricing:</span>
                  <span className="font-semibold text-foreground">
                    {plan.name === "paid" ? "₹99/mo • ₹449/sem" : "₹0 (Free)"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Manual Plan Grant Tool */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-5">
        <div className="flex items-center gap-2.5 border-b border-border pb-4">
          <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center">
            <UserCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Manual Batch Plan Grant</h3>
            <p className="text-xs text-muted-foreground">
              Grant complimentary or department-sponsored Premium access to students.
            </p>
          </div>
        </div>

        <form onSubmit={handleGrantSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">
              Student UUIDs (One per line or comma-separated)
            </label>
            <textarea
              value={grantUserIds}
              onChange={(e) => setGrantUserIds(e.target.value)}
              placeholder="student-pesu-001&#10;user-uuid-1234&#10;PES2UG23CS001"
              rows={3}
              required
              className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="block font-medium text-foreground mb-1">Target Plan</label>
              <select
                value={grantPlanName}
                onChange={(e) => setGrantPlanName(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground"
              >
                <option value="paid">Paid (Premium Tier)</option>
                <option value="free">Free (Standard Tier)</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-foreground mb-1">Duration (Days)</label>
              <input
                type="number"
                value={grantDays}
                onChange={(e) => setGrantDays(Number(e.target.value))}
                min={1}
                max={365}
                required
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground font-mono"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={granting || !grantUserIds.trim()}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 disabled:opacity-50 transition-all shadow-md shadow-primary/20"
            >
              {granting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Granting Access...
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" /> Execute Plan Grant
                </>
              )}
            </button>
          </div>
        </form>

        {grantResult && (
          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs space-y-1">
            <div className="font-bold flex items-center gap-1.5">
              <Check className="w-4 h-4" /> Granted to {grantResult.granted} user(s)!
            </div>
            <p className="text-[11px]">
              Plan &apos;{grantPlanName}&apos; has been immediately applied to selected profiles with expiration dates set.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
