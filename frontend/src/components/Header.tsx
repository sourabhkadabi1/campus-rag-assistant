"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/lib/context";
import { QuotaBadge } from "./QuotaBadge";
import {
  GraduationCap,
  MessageSquare,
  Sparkles,
  Shield,
  Sun,
  Moon,
  User,
  BadgeCheck,
} from "lucide-react";

export function Header() {
  const pathname = usePathname();
  const { profile, isDarkMode, toggleDarkMode, setIsProfileModalOpen, setIsUpgradeModalOpen } =
    useApp();

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        {/* Brand & Identity */}
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20 group-hover:scale-105 transition-transform">
              <GraduationCap className="w-5 h-5" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-base tracking-tight bg-gradient-to-r from-foreground via-foreground to-foreground/70 bg-clip-text">
                  PESU RAG
                </span>
                <span className="text-[10px] uppercase font-extrabold px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-500 tracking-wider">
                  AI
                </span>
              </div>
              <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                Sem {profile.semester} • {profile.department}
              </span>
            </div>
          </Link>

          {/* Nav Links */}
          <nav className="hidden md:flex items-center gap-1">
            <Link
              href="/"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                pathname === "/"
                  ? "bg-secondary text-primary font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              Chat Assistant
            </Link>

            <Link
              href="/pricing"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                pathname === "/pricing"
                  ? "bg-secondary text-primary font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              }`}
            >
              <Sparkles className="w-4 h-4 text-amber-500" />
              Pricing & Plans
            </Link>

            {/* Admin link - only rendered for authenticated admin */}
            {profile.role === "admin" && (
              <Link
                href="/admin"
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  pathname.startsWith("/admin")
                    ? "bg-secondary text-primary font-semibold"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                }`}
              >
                <Shield className="w-4 h-4 text-emerald-500" />
                Admin Portal
              </Link>
            )}
          </nav>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2.5">
          {/* Quota Badge */}
          <QuotaBadge />

          {/* Theme Toggle */}
          <button
            onClick={toggleDarkMode}
            aria-label="Toggle theme"
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary border border-transparent hover:border-border transition-colors"
          >
            {isDarkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
          </button>

          {/* Profile Button */}
          <button
            onClick={() => setIsProfileModalOpen(true)}
            className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-xl border border-border bg-card/60 hover:bg-secondary text-left transition-colors"
          >
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
              {profile.full_name ? profile.full_name[0].toUpperCase() : "U"}
            </div>
            <div className="hidden sm:flex flex-col">
              <span className="text-xs font-semibold text-foreground leading-tight flex items-center gap-1">
                {profile.full_name || "Student"}
                {profile.is_paid && <BadgeCheck className="w-3.5 h-3.5 text-amber-500 inline" />}
              </span>
              <span className="text-[10px] text-muted-foreground capitalize">
                {profile.role} ({profile.plan_name})
              </span>
            </div>
          </button>
        </div>
      </div>
    </header>
  );
}
