"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { Citation, QuotaRemaining, StudentProfile } from "./types";
import { fetchQuotaRemaining } from "./api";

interface AppContextType {
  profile: StudentProfile;
  setProfile: (p: StudentProfile) => void;
  isDarkMode: boolean;
  toggleDarkMode: () => void;
  quota: QuotaRemaining | null;
  refreshQuota: () => Promise<void>;
  isProfileModalOpen: boolean;
  setIsProfileModalOpen: (open: boolean) => void;
  isUpgradeModalOpen: boolean;
  setIsUpgradeModalOpen: (open: boolean) => void;
  pdfPreview: { citation: Citation; isOpen: boolean } | null;
  openPdfPreview: (citation: Citation) => void;
  closePdfPreview: () => void;
}

const DEFAULT_PROFILE: StudentProfile = {
  id: "student-pesu-001",
  email: "student@pesu.edu",
  full_name: "PESU Scholar",
  role: "student",
  department: "CSE",
  semester: 3,
  roll_no: "PES2UG23CS001",
  plan_name: "free",
  is_paid: false,
};

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfileState] = useState<StudentProfile>(DEFAULT_PROFILE);
  const [isDarkMode, setIsDarkMode] = useState<boolean>(false);
  const [quota, setQuota] = useState<QuotaRemaining | null>(null);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState<boolean>(false);
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState<boolean>(false);
  const [pdfPreview, setPdfPreview] = useState<{
    citation: Citation;
    isOpen: boolean;
  } | null>(null);

  // Load profile & theme from localStorage
  useEffect(() => {
    try {
      const savedProfile = localStorage.getItem("pesu_profile");
      if (savedProfile) {
        setProfileState(JSON.parse(savedProfile));
      }
      const savedTheme = localStorage.getItem("pesu_theme");
      if (savedTheme !== null) {
        const dark = savedTheme === "dark";
        setIsDarkMode(dark);
        if (dark) {
          document.documentElement.classList.add("dark");
          document.documentElement.classList.remove("light");
        } else {
          document.documentElement.classList.remove("dark");
          document.documentElement.classList.add("light");
        }
      } else {
        const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setIsDarkMode(dark);
        document.documentElement.classList.toggle("dark", dark);
        document.documentElement.classList.toggle("light", !dark);
      }
    } catch (e) {
      console.warn("Storage access failed", e);
    }
  }, []);

  const setProfile = (newProfile: StudentProfile) => {
    setProfileState(newProfile);
    try {
      localStorage.setItem("pesu_profile", JSON.stringify(newProfile));
    } catch {}
  };

  const toggleDarkMode = () => {
    setIsDarkMode((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("pesu_theme", next ? "dark" : "light");
      } catch {}
      if (next) {
        document.documentElement.classList.add("dark");
        document.documentElement.classList.remove("light");
      } else {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
      }
      return next;
    });
  };

  const refreshQuota = async () => {
    try {
      const q = await fetchQuotaRemaining(profile);
      setQuota(q);
    } catch (e) {
      console.warn("Failed to refresh quota", e);
    }
  };

  useEffect(() => {
    refreshQuota();
    const interval = setInterval(refreshQuota, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [profile]);

  const openPdfPreview = (citation: Citation) => {
    setPdfPreview({ citation, isOpen: true });
  };

  const closePdfPreview = () => {
    setPdfPreview(null);
  };

  return (
    <AppContext.Provider
      value={{
        profile,
        setProfile,
        isDarkMode,
        toggleDarkMode,
        quota,
        refreshQuota,
        isProfileModalOpen,
        setIsProfileModalOpen,
        isUpgradeModalOpen,
        setIsUpgradeModalOpen,
        pdfPreview,
        openPdfPreview,
        closePdfPreview,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
}
