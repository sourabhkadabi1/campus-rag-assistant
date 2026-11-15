"use client";

import React, { useEffect, useState } from "react";
import { useApp } from "@/lib/context";
import { X, User, GraduationCap, Save, Check, RefreshCw } from "lucide-react";

const DEPARTMENTS = ["CSE", "AIML"];
const SEMESTERS = [3, 4];

export function ProfileModal() {
  const { profile, setProfile, isProfileModalOpen, setIsProfileModalOpen, refreshQuota } = useApp();

  const [fullName, setFullName] = useState(profile.full_name);
  const [email, setEmail] = useState(profile.email);
  const [rollNo, setRollNo] = useState(profile.roll_no);
  const [department, setDepartment] = useState(profile.department);
  const [semester, setSemester] = useState(profile.semester);
  const [isPaid, setIsPaid] = useState(profile.is_paid);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    if (!isProfileModalOpen) return;
    setFullName(profile.full_name);
    setEmail(profile.email);
    setRollNo(profile.roll_no);
    setDepartment(profile.department);
    setSemester(profile.semester);
    setIsPaid(profile.is_paid);
  }, [isProfileModalOpen, profile]);

  if (!isProfileModalOpen) return null;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const updated = {
      ...profile,
      full_name: fullName,
      email,
      roll_no: rollNo,
      department,
      semester,
      is_paid: isPaid,
      plan_name: isPaid ? ("paid" as const) : ("free" as const),
    };
    setProfile(updated);
    setSavedSuccess(true);
    refreshQuota();
    setTimeout(() => {
      setSavedSuccess(false);
      setIsProfileModalOpen(false);
    }, 800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 animate-in fade-in duration-150">
      <div className="relative w-full max-w-lg rounded-2xl glass-card overflow-hidden overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border bg-card/90">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <User className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-sm">Student Profile & Settings</h3>
              <p className="text-xs text-muted-foreground">
                Retrieval is strictly scoped to your department & semester.
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsProfileModalOpen(false)}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSave} className="p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">
                Full Name
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">
                Roll Number / PRN
              </label>
              <input
                type="text"
                value={rollNo}
                onChange={(e) => setRollNo(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary font-mono "
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">
              College Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">
                Department
              </label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {!DEPARTMENTS.includes(department) && (
                  <option value={department}>{department} (not supported yet)</option>
                )}
                {DEPARTMENTS.map((dept) => (
                  <option key={dept} value={dept}>
                    {dept === "AIML" ? "AI-ML" : dept}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">
                Enrolled Semester
              </label>
              <select
                value={semester}
                onChange={(e) => setSemester(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary font-medium"
              >
                {!SEMESTERS.includes(semester) && (
                  <option value={semester}>Semester {semester} (not supported yet)</option>
                )}
                {SEMESTERS.map((sem) => (
                  <option key={sem} value={sem}>
                    Semester {sem}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Subscription settings */}
          <div className="pt-3 border-t border-border space-y-3">
            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-secondary/40">
              <div className="flex items-center gap-2">
                <GraduationCap className="w-4 h-4 text-primary-500" />
                <div>
                  <span className="text-xs font-semibold text-foreground block">
                    Subscription Tier
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    Paid tier unlocks Thinking mode (Gemini Flash Thinking) + 30 units/day
                  </span>
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={isPaid}
                  onChange={(e) => setIsPaid(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-border after:border after:rounded-full after:h-5 after:w-5 after:transition-colors peer-checked:bg-primary-500"></div>
              </label>
            </div>
          </div>

          {/* Footer actions */}
          <div className="pt-3 border-t border-border flex items-center justify-between">
            <button
              type="button"
              onClick={() => {
                setFullName("PESU Scholar");
                setEmail("student@pesu.edu");
                setRollNo("PES2UG23CS001");
                setDepartment("CSE");
                setSemester(3);
                setIsPaid(false);
              }}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Reset default
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsProfileModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-medium border border-border hover:bg-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
              >
                {savedSuccess ? (
                  <>
                    <Check className="w-3.5 h-3.5" /> Saved!
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" /> Save Profile
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
