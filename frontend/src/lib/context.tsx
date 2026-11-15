"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { Citation, QuotaRemaining, StudentProfile } from "./types";
import { fetchQuotaRemaining } from "./api";

interface AppContextType {
  profile: StudentProfile;
  setProfile: (p: StudentProfile) => void;
  selectedSubject: string | null;
  setSelectedSubject: (subject: string | null) => void;
  isAdminAuthenticated: boolean;
  setIsAdminAuthenticated: (authenticated: boolean) => void;
  quota: QuotaRemaining | null;
  quotaError: boolean;
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
  id: "00000000-0000-4000-8000-000000000001",
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
  const [profileReady, setProfileReady] = useState(false);
  const [selectedSubject, setSelectedSubjectState] = useState<string | null>(null);
  const [isAdminAuthenticated, setIsAdminAuthenticated] = useState(false);
  const [quota, setQuota] = useState<QuotaRemaining | null>(null);
  const [quotaError, setQuotaError] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState<boolean>(false);
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState<boolean>(false);
  const [pdfPreview, setPdfPreview] = useState<{
    citation: Citation;
    isOpen: boolean;
  } | null>(null);

  // Load the profile and keep the requested dark-only appearance.
  useEffect(() => {
    try {
      const savedProfile = localStorage.getItem("pesu_profile");
      if (savedProfile) {
        const storedProfile = JSON.parse(savedProfile) as StudentProfile;
        const validId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(storedProfile.id);
        const normalizedProfile = {
          ...storedProfile,
          id: validId ? storedProfile.id : crypto.randomUUID(),
          role: "student" as const,
        };
        setProfileState(normalizedProfile);
        localStorage.setItem("pesu_profile", JSON.stringify(normalizedProfile));
      } else {
        const firstVisitProfile = { ...DEFAULT_PROFILE, id: crypto.randomUUID() };
        setProfileState(firstVisitProfile);
        localStorage.setItem("pesu_profile", JSON.stringify(firstVisitProfile));
      }
      const savedSubject = localStorage.getItem("pesu_selected_subject");
      if (savedSubject) setSelectedSubjectState(savedSubject);
      localStorage.removeItem("pesu_theme");
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("light");
    } catch (e) {
      console.warn("Storage access failed", e);
    } finally {
      setProfileReady(true);
    }
  }, []);

  const setProfile = (newProfile: StudentProfile) => {
    const studentProfile = { ...newProfile, role: "student" as const };
    setProfileState(studentProfile);
    if (
      newProfile.department !== profile.department ||
      newProfile.semester !== profile.semester
    ) {
      setSelectedSubjectState(null);
      try {
        localStorage.removeItem("pesu_selected_subject");
      } catch {}
    }
    try {
      localStorage.setItem("pesu_profile", JSON.stringify(studentProfile));
    } catch {}
  };

  const setSelectedSubject = (subject: string | null) => {
    setSelectedSubjectState(subject);
    try {
      if (subject) localStorage.setItem("pesu_selected_subject", subject);
      else localStorage.removeItem("pesu_selected_subject");
    } catch {}
  };

  const refreshQuota = async () => {
    try {
      const q = await fetchQuotaRemaining(profile);
      setQuota(q);
      setQuotaError(false);
    } catch (e) {
      console.warn("Failed to refresh quota", e);
      setQuotaError(true);
    }
  };

  useEffect(() => {
    if (!profileReady) return;
    refreshQuota();
    const interval = setInterval(refreshQuota, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [profile, profileReady]);

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
        selectedSubject,
        setSelectedSubject,
        isAdminAuthenticated,
        setIsAdminAuthenticated,
        quota,
        quotaError,
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
