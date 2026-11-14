"use client";

import React, { useState, useEffect } from "react";
import { ModelStatus } from "@/lib/types";
import {
  fetchAllModelStatus,
  toggleModel,
  clearModelCooldown,
  reverifyModels,
} from "@/lib/api";
import {
  Cpu,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  Clock,
  ShieldCheck,
  Power,
  Flame,
} from "lucide-react";

export function ModelStatusPanel() {
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [reverifying, setReverifying] = useState(false);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const data = await fetchAllModelStatus();
      setModels(data || []);
    } catch (err: any) {
      console.warn("Failed to fetch model status", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 15000); // 15s refresh
    return () => clearInterval(interval);
  }, []);

  const handleToggle = async (modelId: string, current: boolean) => {
    try {
      await toggleModel(modelId, !current);
      setModels((prev) =>
        prev.map((m) => (m.model_id === modelId ? { ...m, is_enabled: !current } : m))
      );
    } catch (err: any) {
      alert("Toggle failed: " + err.message);
    }
  };

  const handleClearCooldown = async (modelId: string) => {
    try {
      await clearModelCooldown(modelId);
      loadStatus();
    } catch (err: any) {
      alert("Clear cooldown failed: " + err.message);
    }
  };

  const handleReverify = async () => {
    try {
      setReverifying(true);
      await reverifyModels();
      await loadStatus();
      alert("Model verification against Gemini & Groq APIs complete!");
    } catch (err: any) {
      alert("Re-verification failed: " + err.message);
    } finally {
      setReverifying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top action bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-2xl glass-card border border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-500/10 text-primary-500 flex items-center justify-center">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              LLM Model Chains & Runtime Status
            </h3>
            <p className="text-xs text-muted-foreground">
              Dual-chain isolation (Free Project vs Paid Project) with live TPM/RPM rate budgeting.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadStatus}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border text-xs font-medium hover:bg-secondary transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>

          <button
            onClick={handleReverify}
            disabled={reverifying}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            {reverifying ? "Checking Provider APIs…" : "Re-verify Models"}
          </button>
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {models.map((model) => {
          const isCooling = model.cooldown_remaining_seconds > 0;
          const rpmPct = Math.min(100, (model.rpm_used / (model.rpm_limit || 1)) * 100);
          const rpdPct = Math.min(100, (model.rpd_used / (model.rpd_limit || 1)) * 100);

          return (
            <div
              key={model.model_id}
              className={`p-5 rounded-2xl border transition-colors space-y-4 flex flex-col justify-between ${
                !model.is_enabled
                  ? "bg-secondary/30 border-border opacity-70"
                  : model.is_available
                  ? "glass-card border-border hover:border-primary/40 shadow-sm"
                  : "bg-danger-500/5 border-danger-500/20"
              }`}
            >
              <div className="space-y-3">
                {/* Header: ID, Provider, Verified */}
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-xs text-foreground font-mono">
                        {model.model_id}
                      </span>
                    </div>
                    <span className="text-[10px]  font-bold px-2 py-0.5 rounded-full bg-secondary text-muted-foreground border border-border">
                      {model.provider}
                    </span>
                  </div>

                  {/* Verification Badge */}
                  {model.is_verified ? (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-success-500/10 text-success-500 border border-success-500/20">
                      <CheckCircle2 className="w-3 h-3" /> Verified
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-danger-500/10 text-danger-500 border border-danger-500/20">
                      <XCircle className="w-3 h-3" /> Unverified
                    </span>
                  )}
                </div>

                {/* Status reason / Cooldown */}
                {isCooling ? (
                  <div className="p-2.5 rounded-xl bg-primary-500/10 border border-primary-500/20 text-primary-600 dark:text-primary-400 text-xs flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-[11px] font-medium">
                      <Clock className="w-3.5 h-3.5 animate-spin" /> Cooldown:{" "}
                      {Math.ceil(model.cooldown_remaining_seconds)}s
                    </span>
                    <button
                      onClick={() => handleClearCooldown(model.model_id)}
                      className="px-2 py-0.5 rounded-lg bg-primary-500 text-white text-[10px] font-bold hover:bg-primary-600 transition-colors"
                    >
                      Clear
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground text-[11px]">Availability:</span>
                    <span
                      className={`font-semibold capitalize text-[11px] ${
                        model.is_available ? "text-success-500" : "text-danger-500"
                      }`}
                    >
                      {model.status_reason || (model.is_available ? "Ready" : "Unavailable")}
                    </span>
                  </div>
                )}

                {/* Metrics: RPM, TPM, RPD */}
                <div className="space-y-2 pt-2 border-t border-border/80 text-xs">
                  <div>
                    <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                      <span>RPM Usage:</span>
                      <span className="font-mono text-foreground">
                        {model.rpm_used} / {model.rpm_limit}
                      </span>
                    </div>
                    <div className="w-full bg-secondary rounded-full h-1 overflow-hidden">
                      <div
                        className="h-full bg-primary-500 rounded-full"
                        style={{ width: `${rpmPct}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                      <span>Daily RPD:</span>
                      <span className="font-mono text-foreground">
                        {model.rpd_used} / {model.rpd_limit}
                      </span>
                    </div>
                    <div className="w-full bg-secondary rounded-full h-1 overflow-hidden">
                      <div
                        className="h-full bg-primary-500 rounded-full"
                        style={{ width: `${rpdPct}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex justify-between text-[11px] text-muted-foreground">
                    <span>TPM Limit:</span>
                    <span className="font-mono text-foreground">
                      {model.tpm_limit ? model.tpm_limit.toLocaleString() : "N/A"}
                    </span>
                  </div>

                  {model.is_summary_model && (
                    <div className="flex justify-between text-[11px] text-primary-500 font-medium">
                      <span>Summary Reserve:</span>
                      <span>{model.reserve_rpd} RPD</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Bottom Toggle switch */}
              <div className="pt-3 border-t border-border flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground">
                  Status: <strong>{model.is_enabled ? "Enabled" : "Disabled"}</strong>
                </span>

                <button
                  onClick={() => handleToggle(model.model_id, model.is_enabled)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold transition-colors ${
                    model.is_enabled
                      ? "bg-secondary text-foreground hover:bg-danger-500/10 hover:text-danger-500 border border-border"
                      : "bg-success-500 text-white hover:bg-success-600"
                  }`}
                >
                  <Power className="w-3.5 h-3.5" />
                  {model.is_enabled ? "Disable" : "Enable"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
