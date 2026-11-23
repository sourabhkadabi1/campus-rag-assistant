"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useApp } from "@/lib/context";
import {
  BookOpenCheck,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RefreshCw,
  FileText,
  RotateCcw,
  Zap,
  ChevronRight,
  BookOpen,
} from "lucide-react";
import {
  generatePracticeQuiz,
  submitPracticeQuiz,
  getPracticeHistory,
} from "@/lib/api";
import {
  PracticeQuestion,
  PracticeSet,
  PracticeSubmitResponse,
} from "@/lib/types";

export default function PracticePage() {
  const {
    profile,
    selectedSubject,
    refreshQuota,
    setIsUpgradeModalOpen,
    openPdfPreview,
  } = useApp();

  // Generator form state
  const [subject, setSubject] = useState(selectedSubject || "Computer Networks");
  const [topic, setTopic] = useState("");
  const [unitNo, setUnitNo] = useState<number | "">("");
  const [chapterNo, setChapterNo] = useState<number | "">("");
  const [questionType, setQuestionType] = useState<"mcq" | "descriptive" | "mixed">("mcq");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [count, setCount] = useState<number>(5);

  // Active quiz state
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<PracticeSet | null>(null);
  const [userAnswers, setUserAnswers] = useState<Record<string, number>>({});
  const [submitResult, setSubmitResult] = useState<PracticeSubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // History state
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    if (selectedSubject) {
      setSubject(selectedSubject);
    }
  }, [selectedSubject]);

  useEffect(() => {
    loadHistory();
  }, [profile.id]);

  const loadHistory = async () => {
    try {
      const res = await getPracticeHistory(profile);
      setHistory(res.items || []);
    } catch (e) {
      // Ignore initial history failure
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim()) {
      setErrorMsg("Please enter or select a subject.");
      return;
    }

    if (!profile.is_paid) {
      setIsUpgradeModalOpen(true);
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    setSubmitResult(null);
    setUserAnswers({});

    try {
      const quiz = await generatePracticeQuiz(
        {
          subject: subject.trim(),
          topic: topic.trim() || undefined,
          unit_no: unitNo !== "" ? Number(unitNo) : undefined,
          chapter_no: chapterNo !== "" ? Number(chapterNo) : undefined,
          question_type: questionType,
          difficulty,
          count,
        },
        profile
      );
      setActiveQuiz(quiz);
      await refreshQuota();
      await loadHistory();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to generate practice quiz.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectOption = (questionId: string, optionIdx: number) => {
    if (submitResult) return; // Locked after submission
    setUserAnswers((prev) => ({ ...prev, [questionId]: optionIdx }));
  };

  const handleSubmit = async () => {
    if (!activeQuiz) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await submitPracticeQuiz(activeQuiz.id, userAnswers, profile);
      setSubmitResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to evaluate answers.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetQuiz = () => {
    setActiveQuiz(null);
    setSubmitResult(null);
    setUserAnswers({});
  };

  return (
    <div className="flex-1 overflow-y-auto py-10 px-4 sm:px-6 max-w-5xl mx-auto space-y-10">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-primary">
              Stage 7: Practice Engine
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-secondary text-foreground/80 border border-border">
              Sem {profile.semester} • {profile.department}
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-foreground mt-1">
            Textbook Practice & Quizzes
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Generate exam-style MCQs and descriptive questions grounded strictly in uploaded semester textbooks.
          </p>
        </div>

        {activeQuiz && (
          <button
            onClick={handleResetQuiz}
            className="self-start md:self-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-secondary hover:bg-secondary/70 text-xs font-medium text-foreground transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            New Practice Set
          </button>
        )}
      </div>

      {/* Premium Upgrade Banner for Free Users */}
      {!profile.is_paid && (
        <div className="p-4 sm:p-5 rounded-2xl border border-primary/30 bg-primary/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/20 text-primary flex items-center justify-center shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">
                Practice & Quiz Generation is a Premium Feature
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Upgrade to the Premium Plan (₹99/mo) to generate unlimited subject quizzes, detailed derivations, and page-cited answers.
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsUpgradeModalOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-opacity shrink-0 shadow-sm"
          >
            <Zap className="w-3.5 h-3.5" />
            Upgrade to Premium
          </button>
        </div>
      )}

      {/* Main Content Area */}
      {!activeQuiz ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Generation Config Card */}
          <div className="lg:col-span-2 p-6 rounded-2xl border border-border bg-card/60 backdrop-blur space-y-6">
            <div className="flex items-center gap-2">
              <BookOpenCheck className="w-5 h-5 text-primary" />
              <h2 className="text-lg font-bold text-foreground">Configure Practice Quiz</h2>
            </div>

            <form onSubmit={handleGenerate} className="space-y-5">
              {/* Subject */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Course Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g. Computer Networks, Microprocessors"
                  className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
              </div>

              {/* Topic / Concepts */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">
                  Specific Topic / Keyword <span className="text-muted-foreground">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. Subnetting, TCP 3-way handshake, OSI layers"
                  className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Unit & Chapter */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">
                    Unit No <span className="text-muted-foreground">(Optional)</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={unitNo}
                    onChange={(e) => setUnitNo(e.target.value ? Number(e.target.value) : "")}
                    placeholder="e.g. 2"
                    className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">
                    Chapter No <span className="text-muted-foreground">(Optional)</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={chapterNo}
                    onChange={(e) => setChapterNo(e.target.value ? Number(e.target.value) : "")}
                    placeholder="e.g. 4"
                    className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Question Type */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Question Format</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "mcq", label: "Multiple Choice" },
                    { id: "descriptive", label: "Descriptive" },
                    { id: "mixed", label: "Mixed Set" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setQuestionType(t.id as any)}
                      className={`px-3 py-2 rounded-xl text-xs font-medium border transition-colors ${
                        questionType === t.id
                          ? "bg-primary text-primary-foreground border-primary font-semibold"
                          : "bg-secondary/40 text-muted-foreground border-border hover:text-foreground"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Difficulty & Count */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Difficulty</label>
                  <select
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value as any)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="easy">Easy (Definitions & Basics)</option>
                    <option value="medium">Medium (Standard Exam Level)</option>
                    <option value="hard">Hard (Numericals & Derivations)</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Question Count</label>
                  <select
                    value={count}
                    onChange={(e) => setCount(Number(e.target.value))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary/50 text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value={3}>3 Questions (Quick Drill)</option>
                    <option value={5}>5 Questions (Standard)</option>
                    <option value={10}>10 Questions (Full Unit Mock)</option>
                  </select>
                </div>
              </div>

              {errorMsg && (
                <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs">
                  {errorMsg}
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 rounded-xl bg-primary text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:opacity-90 disabled:opacity-50 transition-all shadow-sm"
              >
                {isLoading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Synthesizing Questions from Textbooks...
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    Generate Practice Quiz (Uses 2 Units)
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Practice History Sidebar */}
          <div className="p-6 rounded-2xl border border-border bg-card/60 backdrop-blur space-y-4">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-muted-foreground" />
              <h3 className="text-sm font-bold text-foreground">Recent Practice History</h3>
            </div>

            {history.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No past quizzes yet. Generate your first practice set to test your exam preparation!
              </p>
            ) : (
              <div className="space-y-2.5 overflow-y-auto max-h-[420px] pr-1">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="p-3 rounded-xl border border-border bg-secondary/30 hover:bg-secondary/60 text-xs transition-colors space-y-1"
                  >
                    <div className="font-semibold text-foreground flex items-center justify-between">
                      <span className="truncate">{item.subject}</span>
                      <span className="text-[10px] uppercase font-bold text-primary">
                        {item.difficulty}
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground flex items-center justify-between">
                      <span>{item.question_count || 5} questions</span>
                      <span>{new Date(item.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Active Quiz Taking / Review View */
        <div className="space-y-8">
          {/* Quiz Metadata Bar */}
          <div className="p-4 rounded-2xl border border-border bg-secondary/30 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-3">
              <span className="font-bold text-foreground text-sm">{activeQuiz.subject}</span>
              {activeQuiz.topic && (
                <span className="px-2 py-0.5 rounded-full bg-secondary border border-border text-muted-foreground">
                  {activeQuiz.topic}
                </span>
              )}
              {activeQuiz.unit_no && (
                <span className="px-2 py-0.5 rounded-full bg-secondary border border-border text-muted-foreground">
                  Unit {activeQuiz.unit_no}
                </span>
              )}
              <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold uppercase">
                {activeQuiz.difficulty}
              </span>
            </div>

            {submitResult && (
              <div className="flex items-center gap-2 font-bold text-sm">
                <span>Score:</span>
                <span
                  className={`px-2.5 py-0.5 rounded-full ${
                    submitResult.percentage >= 70
                      ? "bg-success-500/20 text-success-500"
                      : "bg-warning-500/20 text-warning-500"
                  }`}
                >
                  {submitResult.score} / {submitResult.total} ({submitResult.percentage}%)
                </span>
              </div>
            )}
          </div>

          {/* Question List */}
          <div className="space-y-6">
            {activeQuiz.questions.map((q, idx) => {
              const fb = submitResult?.feedback.find((f) => f.question_id === q.id);
              const isSubmitted = !!submitResult;

              return (
                <div
                  key={q.id}
                  className={`p-6 rounded-2xl border transition-all ${
                    isSubmitted
                      ? fb?.is_correct
                        ? "border-success-500/40 bg-success-500/5"
                        : fb?.type === "mcq"
                        ? "border-destructive/40 bg-destructive/5"
                        : "border-border bg-card/60"
                      : "border-border bg-card/60"
                  } space-y-4`}
                >
                  {/* Question Header */}
                  <div className="flex items-start justify-between gap-4">
                    <span className="text-xs font-bold text-primary px-2 py-0.5 rounded bg-primary/10">
                      Question {idx + 1}
                    </span>
                    {q.citation && (
                      <button
                        onClick={() => openPdfPreview(q.citation as any)}
                        className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <BookOpen className="w-3 h-3 text-primary" />
                        <span>
                          Ch {q.citation.chapter_no || "N/A"} • Page {q.citation.page_start || "N/A"}
                        </span>
                      </button>
                    )}
                  </div>

                  <p className="text-sm sm:text-base font-semibold text-foreground">
                    {q.question}
                  </p>

                  {/* MCQ Options */}
                  {q.type === "mcq" && q.options && (
                    <div className="space-y-2 pt-1">
                      {q.options.map((opt, optIdx) => {
                        const isSelected = userAnswers[q.id] === optIdx;
                        const isCorrectOption = q.correct_option_index === optIdx;

                        let optClasses = "border-border bg-secondary/40 hover:bg-secondary/70";
                        if (isSubmitted) {
                          if (isCorrectOption) {
                            optClasses = "border-success-500 bg-success-500/20 text-success-400 font-semibold";
                          } else if (isSelected && !isCorrectOption) {
                            optClasses = "border-destructive bg-destructive/20 text-destructive font-semibold";
                          } else {
                            optClasses = "border-border opacity-50";
                          }
                        } else if (isSelected) {
                          optClasses = "border-primary bg-primary/10 text-primary font-semibold";
                        }

                        return (
                          <button
                            key={optIdx}
                            type="button"
                            disabled={isSubmitted}
                            onClick={() => handleSelectOption(q.id, optIdx)}
                            className={`w-full text-left p-3 rounded-xl border text-xs sm:text-sm flex items-center justify-between transition-all ${optClasses}`}
                          >
                            <span>{opt}</span>
                            {isSubmitted && isCorrectOption && (
                              <CheckCircle2 className="w-4 h-4 text-success-500 shrink-0" />
                            )}
                            {isSubmitted && isSelected && !isCorrectOption && (
                              <XCircle className="w-4 h-4 text-destructive shrink-0" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Explanation / Model Answer After Submission */}
                  {isSubmitted && (
                    <div className="pt-3 border-t border-border/60 text-xs space-y-2">
                      <div className="font-semibold text-foreground flex items-center gap-1.5">
                        <HelpCircle className="w-3.5 h-3.5 text-primary" />
                        <span>Textbook Model Answer & Explanation</span>
                      </div>
                      <p className="text-muted-foreground leading-relaxed">
                        {q.model_answer}
                      </p>
                      {q.key_points && q.key_points.length > 0 && (
                        <div className="pt-1">
                          <span className="font-medium text-foreground">Key Concepts Tested:</span>
                          <ul className="list-disc list-inside mt-1 text-muted-foreground space-y-0.5">
                            {q.key_points.map((kp, kIdx) => (
                              <li key={kIdx}>{kp}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Bottom Action Bar */}
          <div className="p-4 rounded-2xl border border-border bg-card/60 flex items-center justify-between gap-4">
            <button
              onClick={handleResetQuiz}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-border bg-secondary hover:bg-secondary/80 text-xs font-semibold text-foreground transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Configure Another Quiz
            </button>

            {!submitResult ? (
              <button
                onClick={handleSubmit}
                disabled={isSubmitting}
                className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs sm:text-sm font-bold hover:opacity-90 disabled:opacity-50 transition-all shadow-sm"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Grading Answers...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    Submit & Check Answers
                  </>
                )}
              </button>
            ) : (
              <button
                onClick={() => {
                  setSubmitResult(null);
                  setUserAnswers({});
                }}
                className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs sm:text-sm font-bold hover:opacity-90 transition-all shadow-sm"
              >
                <RotateCcw className="w-4 h-4" />
                Retake Quiz
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
