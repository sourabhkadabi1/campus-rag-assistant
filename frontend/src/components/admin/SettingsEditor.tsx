"use client";

import React, { useState, useEffect } from "react";
import {
  fetchAccountBalance,
  updateAccountBalance,
  togglePremiumSetting,
  fetchModelPrices,
  updateModelPrices,
  fetchBudgetGuardStatus,
  updateBudgetGuard,
} from "@/lib/api";
import {
  Sliders,
  Sparkles,
  DollarSign,
  ShieldAlert,
  Save,
  Check,
  RefreshCw,
  Power,
  Coins,
} from "lucide-react";

export function SettingsEditor() {
  const [balance, setBalance] = useState<number>(5.0);
  const [newBalanceInput, setNewBalanceInput] = useState<string>("5.00");
  const [premiumEnabled, setPremiumEnabled] = useState<boolean>(false);
  const [modelPrices, setModelPrices] = useState<Record<string, { input: number; output: number }>>({});
  const [budgetGuard, setBudgetGuard] = useState<any>(null);
  const [manualRetrieval, setManualRetrieval] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const loadAllSettings = async () => {
    try {
      const [balRes, pricesRes, bgRes] = await Promise.all([
        fetchAccountBalance().catch(() => ({ account_balance_usd: 5.0 })),
        fetchModelPrices().catch(() => ({ prices: {} })),
        fetchBudgetGuardStatus().catch(() => null),
      ]);

      setBalance(balRes.account_balance_usd);
      setNewBalanceInput(balRes.account_balance_usd.toFixed(2));
      setModelPrices(pricesRes.prices || {});
      if (bgRes) {
        setBudgetGuard(bgRes);
        setManualRetrieval(bgRes.manual_retrieval_only ?? false);
      }
    } catch (err) {
      console.warn("Failed to load settings", err);
    }
  };

  useEffect(() => {
    loadAllSettings();
  }, []);

  const handleTogglePremium = async (enabled: boolean) => {
    try {
      await togglePremiumSetting(enabled);
      setPremiumEnabled(enabled);
    } catch (err: any) {
      alert("Failed to toggle premium: " + err.message);
    }
  };

  const handleUpdateBalance = async (e: React.FormEvent) => {
    e.preventDefault();
    const val = parseFloat(newBalanceInput);
    if (isNaN(val) || val < 0) return alert("Please enter a valid amount");

    try {
      setSaving(true);
      await updateAccountBalance(val);
      setBalance(val);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 1200);
    } catch (err: any) {
      alert("Failed to update balance: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handlePriceChange = (modelId: string, field: "input" | "output", value: string) => {
    const num = parseFloat(value) || 0;
    setModelPrices((prev) => ({
      ...prev,
      [modelId]: {
        ...prev[modelId],
        [field]: num,
      },
    }));
  };

  const handleSavePrices = async () => {
    try {
      setSaving(true);
      await updateModelPrices(modelPrices);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 1200);
    } catch (err: any) {
      alert("Failed to update prices: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleManualRetrieval = async (val: boolean) => {
    try {
      await updateBudgetGuard({ manual_retrieval_only: val });
      setManualRetrieval(val);
    } catch (err: any) {
      alert("Failed to update budget guard: " + err.message);
    }
  };

  return (
    <div className="space-y-8">
      {/* Live Runtime Controls Box */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-6">
        <div className="flex items-center gap-2.5 border-b border-border pb-4">
          <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Global Runtime Switches</h3>
            <p className="text-xs text-muted-foreground">
              Immediate server switches affecting all student queries without restart.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Live Premium Toggle */}
          <div className="p-5 rounded-xl border border-border bg-secondary/30 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-primary-500" />
                PREMIUM_ENABLED
              </span>
              <p className="text-[11px] text-muted-foreground max-w-xs">
                Master switch for Gemini Flash Thinking route. When disabled, paid users answer through the normal paid chain without interruption.
              </p>
            </div>

            <button
              onClick={() => handleTogglePremium(!premiumEnabled)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm ${
                premiumEnabled
                  ? "bg-primary-600 text-white hover:bg-primary-700"
                  : "bg-secondary text-muted-foreground hover:text-foreground border border-border"
              }`}
            >
              <Power className="w-3.5 h-3.5" />
              {premiumEnabled ? "ACTIVE" : "DISABLED"}
            </button>
          </div>

          {/* Exam Week Mode / Manual Retrieval Only */}
          <div className="p-5 rounded-xl border border-border bg-secondary/30 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4 text-primary-500" />
                Exam Week Mode (Retrieval-Only)
              </span>
              <p className="text-[11px] text-muted-foreground max-w-xs">
                Protects free-tier quota spikes by serving direct retrieved passages without LLM calls.
              </p>
            </div>

            <button
              onClick={() => handleToggleManualRetrieval(!manualRetrieval)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm ${
                manualRetrieval
                  ? "bg-primary-600 text-white hover:bg-primary-700"
                  : "bg-secondary text-muted-foreground hover:text-foreground border border-border"
              }`}
            >
              <Power className="w-3.5 h-3.5" />
              {manualRetrieval ? "ACTIVE" : "OFF"}
            </button>
          </div>
        </div>
      </div>

      {/* Account Balance Editor */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-5">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-success-500/10 text-success-500 flex items-center justify-center">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">API Balance Guard</h3>
              <p className="text-xs text-muted-foreground">
                Current Google Cloud / API billing balance. Thinking mode disables when &lt; $2.00; paid users switch to retrieval-only when &lt; $0.75.
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleUpdateBalance} className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Current Reconciled Balance (USD)
            </label>
            <div className="relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground $PLACEHOLDER text-sm">
                $
              </span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={newBalanceInput}
                onChange={(e) => setNewBalanceInput(e.target.value)}
                required
                className="w-full pl-8 pr-4 py-2.5 rounded-xl border border-border bg-background text-foreground text-sm $PLACEHOLDER font-bold focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div className="pt-5">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shadow-md shadow-primary/20"
            >
              {saveSuccess ? (
                <>
                  <Check className="w-3.5 h-3.5" /> Updated!
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" /> Set Balance
                </>
              )}
            </button>
          </div>
        </form>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs pt-2">
          <div className="p-3 rounded-xl border border-border bg-secondary/30">
            <span className="text-muted-foreground block text-[10px]  font-bold">Thinking Cutoff</span>
            <span className="font-semibold text-primary-500">$2.00 threshold</span>
          </div>
          <div className="p-3 rounded-xl border border-border bg-secondary/30">
            <span className="text-muted-foreground block text-[10px]  font-bold">Emergency Cutoff</span>
            <span className="font-semibold text-danger-500">$0.75 threshold</span>
          </div>
          <div className="p-3 rounded-xl border border-border bg-secondary/30 col-span-2 sm:col-span-1">
            <span className="text-muted-foreground block text-[10px]  font-bold">Daily Spend Cap</span>
            <span className="font-semibold text-foreground $PLACEHOLDER">$0.15 / day</span>
          </div>
        </div>
      </div>

      {/* Model Pricing Editor */}
      <div className="p-6 rounded-2xl glass-card border border-border space-y-5">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary-500/10 text-primary-500 flex items-center justify-center">
              <DollarSign className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Model Token Pricing (USD per 1M Tokens)</h3>
              <p className="text-xs text-muted-foreground">
                Prices used to compute real request cost_usd and deduct from balance.
              </p>
            </div>
          </div>

          <button
            onClick={handleSavePrices}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shadow-sm"
          >
            {saveSuccess ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            Save Prices
          </button>
        </div>

        <div className="border border-border rounded-xl overflow-hidden">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="bg-secondary/60 border-b border-border text-foreground font-semibold">
                <th className="p-3">Model ID</th>
                <th className="p-3">Input Price ($/1M)</th>
                <th className="p-3">Output Price ($/1M)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {Object.keys(modelPrices).length === 0 ? (
                <tr>
                  <td colSpan={3} className="p-4 text-center text-muted-foreground">
                    Using system defaults ($0.30/$2.50 for Flash Lite, $1.50/$7.50 for Flash Thinking).
                  </td>
                </tr>
              ) : (
                Object.entries(modelPrices).map(([modelId, prices]) => (
                  <tr key={modelId} className="hover:bg-secondary/20">
                    <td className="p-3 $PLACEHOLDER font-semibold text-foreground">{modelId}</td>
                    <td className="p-3">
                      <input
                        type="number"
                        step="0.01"
                        value={prices.input}
                        onChange={(e) => handlePriceChange(modelId, "input", e.target.value)}
                        className="w-24 px-2 py-1 rounded border border-border bg-background text-foreground $PLACEHOLDER"
                      />
                    </td>
                    <td className="p-3">
                      <input
                        type="number"
                        step="0.01"
                        value={prices.output}
                        onChange={(e) => handlePriceChange(modelId, "output", e.target.value)}
                        className="w-24 px-2 py-1 rounded border border-border bg-background text-foreground $PLACEHOLDER"
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
