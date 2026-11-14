"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useApp } from "@/lib/context";
import { DocumentUpload } from "@/components/admin/DocumentUpload";
import { ModelStatusPanel } from "@/components/admin/ModelStatusPanel";
import { MarginDashboard } from "@/components/admin/MarginDashboard";
import { SettingsEditor } from "@/components/admin/SettingsEditor";
import { PlanManager } from "@/components/admin/PlanManager";
import {
  Shield,
  FileText,
  Cpu,
  DollarSign,
  Sliders,
  CreditCard,
  Lock,
  ArrowLeft,
  KeyRound,
  Check,
  AlertCircle,
  LogOut,
} from "lucide-react";

export default function AdminPortalPage() {
  const { profile, setProfile } = useApp();
  const [activeTab, setActiveTab] = useState<
    "documents" | "models" | "margin" | "settings" | "plans"
  >("documents");

  // Admin passkey authentication state
  const [passkeyInput, setPasskeyInput] = useState("");
  const [authError, setAuthError] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);

  const EXPECTED_KEY =
    process.env.NEXT_PUBLIC_ADMIN_PASSKEY || "pesu-admin-2026";

  const handleUnlockAdmin = (e: React.FormEvent) => {
    e.preventDefault();
    if (passkeyInput.trim() === EXPECTED_KEY) {
      setAuthSuccess(true);
      setAuthError(false);
      setTimeout(() => {
        setProfile({
          ...profile,
          role: "admin",
        });
        setPasskeyInput("");
        setAuthSuccess(false);
      }, 600);
    } else {
      setAuthError(true);
      setAuthSuccess(false);
    }
  };

  const handleExitAdmin = () => {
    setProfile({
      ...profile,
      role: "student",
    });
  };

  // If user is a student, show strictly the 403 Restricted Gate
  if (profile.role !== "admin") {
    return (
      <div className="flex-1 flex items-center justify-center p-6 bg-background">
        <div className="max-w-md w-full p-8 rounded-3xl glass-card border border-border shadow-2xl space-y-6 text-center animate-in fade-in zoom-in-95 duration-200">
          <div className="w-16 h-16 rounded-3xl bg-red-500/10 text-red-500 flex items-center justify-center mx-auto shadow-inner border border-red-500/20">
            <Lock className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded-full bg-red-500/10 text-red-500 tracking-wider">
              403 Forbidden
            </span>
            <h1 className="text-xl font-bold text-foreground">
              Administrator Access Restricted
            </h1>
            <p className="text-xs text-muted-foreground leading-relaxed">
              This management console is restricted exclusively to college system administrators.
              Students are not permitted to view document ingestion, LLM model chains, spend budgets, or system settings.
            </p>
          </div>

          {/* Action to return to Student App */}
          <div className="pt-2">
            <Link
              href="/"
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all shadow-md shadow-primary/20"
            >
              <ArrowLeft className="w-4 h-4" />
              Return to Student Assistant
            </Link>
          </div>

          {/* Administrator Unlock Area */}
          <div className="pt-4 border-t border-border space-y-3 text-left">
            <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5 text-indigo-500" /> Authorized Administrator Sign-In
            </span>

            <form onSubmit={handleUnlockAdmin} className="space-y-2.5">
              <div>
                <input
                  type="password"
                  value={passkeyInput}
                  onChange={(e) => {
                    setPasskeyInput(e.target.value);
                    setAuthError(false);
                  }}
                  placeholder="Enter administrator passkey..."
                  className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary font-mono"
                />
              </div>

              {authError && (
                <p className="text-[11px] text-red-500 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> Incorrect passkey. Access denied.
                </p>
              )}

              {authSuccess && (
                <p className="text-[11px] text-emerald-500 flex items-center gap-1">
                  <Check className="w-3.5 h-3.5" /> Verified! Unlocking dashboard...
                </p>
              )}

              <button
                type="submit"
                disabled={!passkeyInput.trim() || authSuccess}
                className="w-full py-2 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-secondary transition-colors"
              >
                Authenticate as Admin
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // Authenticated Admin View
  return (
    <div className="flex-1 overflow-y-auto py-8 px-4 sm:px-6 max-w-7xl mx-auto space-y-8 w-full animate-in fade-in duration-200">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-6">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 text-white flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold text-foreground tracking-tight">
                Admin Control Center
              </h1>
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                Superuser Authorized
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Manage syllabus documents, model rate limits, API spend caps, and subscription tiers.
            </p>
          </div>
        </div>

        {/* Exit Admin Mode */}
        <button
          onClick={handleExitAdmin}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          title="Switch back to student view to test student experience"
        >
          <LogOut className="w-3.5 h-3.5 text-amber-500" />
          Exit Admin Mode
        </button>
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-border overflow-x-auto gap-2 text-xs font-semibold">
        <button
          onClick={() => setActiveTab("documents")}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all whitespace-nowrap ${
            activeTab === "documents"
              ? "border-primary text-primary font-bold bg-primary/5 rounded-t-xl"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          }`}
        >
          <FileText className="w-4 h-4" />
          Documents & Ingestion
        </button>

        <button
          onClick={() => setActiveTab("models")}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all whitespace-nowrap ${
            activeTab === "models"
              ? "border-primary text-primary font-bold bg-primary/5 rounded-t-xl"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          }`}
        >
          <Cpu className="w-4 h-4" />
          Model Verification & Status
        </button>

        <button
          onClick={() => setActiveTab("margin")}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all whitespace-nowrap ${
            activeTab === "margin"
              ? "border-primary text-primary font-bold bg-primary/5 rounded-t-xl"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          }`}
        >
          <DollarSign className="w-4 h-4" />
          Margin Dashboard
        </button>

        <button
          onClick={() => setActiveTab("settings")}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all whitespace-nowrap ${
            activeTab === "settings"
              ? "border-primary text-primary font-bold bg-primary/5 rounded-t-xl"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          }`}
        >
          <Sliders className="w-4 h-4" />
          Balance & Runtime Controls
        </button>

        <button
          onClick={() => setActiveTab("plans")}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all whitespace-nowrap ${
            activeTab === "plans"
              ? "border-primary text-primary font-bold bg-primary/5 rounded-t-xl"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/40"
          }`}
        >
          <CreditCard className="w-4 h-4" />
          Plan Management
        </button>
      </div>

      {/* Tab Panels */}
      <div className="pt-2">
        {activeTab === "documents" && <DocumentUpload />}
        {activeTab === "models" && <ModelStatusPanel />}
        {activeTab === "margin" && <MarginDashboard />}
        {activeTab === "settings" && <SettingsEditor />}
        {activeTab === "plans" && <PlanManager />}
      </div>
    </div>
  );
}
