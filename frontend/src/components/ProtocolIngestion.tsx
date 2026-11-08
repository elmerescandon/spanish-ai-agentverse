"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import {
  createProtocol,
  type PipelineStep,
  PRESELECTED_PROTOCOL,
  type ProtocolSummary,
} from "@/lib/api";

const NEXT_PROCESS_STEPS: { id: PipelineStep; label: string }[] = [
  { id: "completeness", label: "Compare against guidelines" },
  { id: "comparison", label: "Compare with previous protocols" },
  { id: "cohort", label: "Cohort analysis" },
];

export interface ProtocolIngestionProps {
  onProtocolLoaded?: (protocol: ProtocolSummary) => void;
  onStepSelected?: (step: PipelineStep) => void;
  activeProtocolId?: string;
  isAnalyzing?: boolean;
  className?: string;
}

interface UploadedFileInfo {
  name: string;
  size: string;
  type: string;
  status: "Uploaded" | "Analyzing" | "Ready";
  protocolTitle?: string;
  protocolId?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function cleanFilenameToTitle(filename: string): string {
  const withoutExt = filename.replace(/\.[^/.]+$/, "");
  const words = withoutExt.replace(/[-_.]+/g, " ").trim();
  const capitalized = words
    .split(/\s+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
  return capitalized
    ? `Clinical Protocol Draft: ${capitalized}`
    : "Clinical Protocol Draft";
}

export default function ProtocolIngestion({
  onProtocolLoaded,
  onStepSelected,
  isAnalyzing = false,
  className = "",
}: ProtocolIngestionProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<UploadedFileInfo | null>(null);
  const [selectedStep, setSelectedStep] = useState<PipelineStep | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [animationKey, setAnimationKey] = useState<number>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleRunPreselected = () => {
    setErrorMessage(null);
    setSelectedStep(null);
    setAnimationKey(Date.now());
    setUploadedFile({
      name: "Phase_3_SGLT2_High_Risk_T2D_Protocol.json",
      size: "14.2 KB",
      type: "application/json",
      status: "Ready",
      protocolTitle: PRESELECTED_PROTOCOL.title,
      protocolId: PRESELECTED_PROTOCOL.protocol_id,
    });
    onProtocolLoaded?.(PRESELECTED_PROTOCOL);
  };

  const processFile = async (file: File) => {
    setIsProcessing(true);
    setErrorMessage(null);
    setSelectedStep(null);
    setAnimationKey(Date.now());

    const formattedSize = formatFileSize(file.size);
    const fileType =
      file.type ||
      (file.name.endsWith(".pdf")
        ? "application/pdf"
        : file.name.endsWith(".json")
          ? "application/json"
          : "text/plain");

    setUploadedFile({
      name: file.name,
      size: formattedSize,
      type: fileType,
      status: "Analyzing",
    });

    try {
      let protocolTitle = cleanFilenameToTitle(file.name);
      let protocolData: Record<string, unknown> = {
        source_file: file.name,
        file_size: formattedSize,
        file_type: fileType,
        uploaded_at: new Date().toISOString(),
      };

      if (file.name.endsWith(".json")) {
        const text = await file.text();
        try {
          const parsed = JSON.parse(text) as Record<string, unknown>;
          if (typeof parsed.title === "string" && parsed.title.trim()) {
            protocolTitle = parsed.title.trim();
          } else if (
            typeof parsed.protocol_title === "string" &&
            parsed.protocol_title.trim()
          ) {
            protocolTitle = parsed.protocol_title.trim();
          } else if (
            typeof parsed.name === "string" &&
            parsed.name.trim()
          ) {
            protocolTitle = parsed.name.trim();
          }

          if (parsed.data && typeof parsed.data === "object") {
            protocolData = {
              ...protocolData,
              ...(parsed.data as Record<string, unknown>),
            };
          } else {
            protocolData = {
              ...protocolData,
              ...parsed,
            };
          }
        } catch {
          throw new Error("Invalid JSON document structure.");
        }
      } else if (file.name.endsWith(".txt")) {
        const text = await file.text();
        const firstLine = text.split("\n")[0]?.trim();
        if (firstLine && firstLine.length > 5 && firstLine.length < 120) {
          protocolTitle = firstLine;
        }
        protocolData.text_preview = text.slice(0, 300);
      } else {
        protocolData.document_format = "PDF Clinical Protocol";
      }

      await new Promise((resolve) => setTimeout(resolve, 400));

      let resultProtocol: ProtocolSummary;
      try {
        resultProtocol = await createProtocol({
          title: protocolTitle,
          data: protocolData,
        });
      } catch {
        resultProtocol = {
          protocol_id: `proto-local-${Math.random().toString(36).substring(2, 10)}`,
          title: protocolTitle,
          status: "ready",
          data: protocolData,
        };
      }

      setUploadedFile({
        name: file.name,
        size: formattedSize,
        type: fileType,
        status: "Ready",
        protocolTitle: resultProtocol.title,
        protocolId: resultProtocol.protocol_id,
      });

      onProtocolLoaded?.(resultProtocol);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to parse protocol file.";
      setErrorMessage(message);
      setUploadedFile(null);
    } finally {
      setIsProcessing(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleClearFile = () => {
    setUploadedFile(null);
    setSelectedStep(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSelectStep = (step: PipelineStep) => {
    setSelectedStep(step);
    onStepSelected?.(step);
  };

  return (
    <section
      aria-label="Protocol Intake & Data Ingestion"
      className={`space-y-6 ${className}`}
    >
      {/* Minimalist Editorial Header */}
      <header className="flex items-center gap-3">
        <FileText
          className="w-5 h-5 text-zinc-700 dark:text-zinc-300 shrink-0"
          strokeWidth={1.5}
        />
        <h1 className="font-serif text-2xl font-normal tracking-tight text-zinc-900 dark:text-zinc-50">
          Protocol Intake &amp; Data Ingestion
        </h1>
      </header>

      {/* Error alert */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3.5 text-xs rounded-xl bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 flex items-center justify-between"
        >
          <span className="font-sans">{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="font-sans font-medium underline hover:opacity-75 cursor-pointer ml-3 shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Single Specific Card */}
      <div className="bg-white dark:bg-zinc-900 rounded-2xl p-8 space-y-6">
        <div className="space-y-1">
          <h2 className="font-serif text-lg font-normal text-zinc-900 dark:text-zinc-100">
            Upload Protocol Document
          </h2>
          <p className="font-sans text-xs text-zinc-500 dark:text-zinc-400">
            Upload a clinical protocol draft (.pdf, .json, .txt) or run the preselected benchmark.
          </p>
        </div>

        {/* Single persistent file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.json,.txt"
          onChange={handleFileChange}
          disabled={isProcessing || isAnalyzing}
          className="hidden"
          id="protocol-file-input"
          aria-label="Upload protocol file"
        />

        {/* Step Content: Upload Dropzone OR Animated Loaded File View */}
        {!uploadedFile ? (
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`p-10 rounded-xl transition-colors flex flex-col items-center justify-center text-center cursor-pointer ${
              isDragging
                ? "bg-zinc-100 dark:bg-zinc-800"
                : "bg-zinc-50 dark:bg-zinc-800/40 hover:bg-zinc-100/80 dark:hover:bg-zinc-800/60"
            }`}
          >
            <span className="font-sans text-xs font-medium text-zinc-800 dark:text-zinc-200">
              Click or drag file here
            </span>
            <span className="font-sans text-[11px] text-zinc-400 dark:text-zinc-500 mt-1">
              Supports PDF, JSON, and TXT
            </span>
          </div>
        ) : (
          <div
            key={animationKey || uploadedFile.name}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className="relative overflow-hidden p-5 rounded-xl bg-zinc-50 dark:bg-zinc-800/40 animate-file-change space-y-3 transition-all select-none"
          >
            {/* One-shot shimmer wave during file load */}
            <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-xl">
              <div className="w-1/2 h-full bg-gradient-to-r from-transparent via-white/50 dark:via-zinc-600/20 to-transparent animate-shimmer-wave" />
            </div>

            <div className="flex items-start justify-between gap-4 text-xs relative z-10">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 truncate">
                  <span className="font-sans font-medium text-zinc-900 dark:text-zinc-100 truncate">
                    {uploadedFile.name}
                  </span>
                  <span className="font-sans text-zinc-400 shrink-0">
                    ({uploadedFile.size})
                  </span>
                </div>
                <p className="font-sans text-xs text-zinc-500 dark:text-zinc-400 truncate">
                  {uploadedFile.protocolTitle || "Loaded protocol draft"}
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                {uploadedFile.status === "Analyzing" && (
                  <span className="inline-flex items-center gap-1.5 font-sans text-xs text-amber-700 dark:text-amber-400 font-medium">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                    Processing...
                  </span>
                )}

                {uploadedFile.status === "Ready" && (
                  <span className="font-sans text-xs text-emerald-700 dark:text-emerald-400 font-medium animate-icon-pulse">
                    Status: Ready
                  </span>
                )}

                {!isProcessing && (
                  <button
                    type="button"
                    onClick={handleClearFile}
                    className="font-sans text-[11px] text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors cursor-pointer"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            {/* Minimalist animated progress bar that fills when the file loads */}
            <div className="w-full bg-zinc-200/70 dark:bg-zinc-700/60 h-1 rounded-full overflow-hidden relative z-10">
              <div className="bg-zinc-900 dark:bg-zinc-100 h-full rounded-full animate-upload-progress" />
            </div>
          </div>
        )}

        {/* Action Bar: Preselected Button OR Next Process Steps once Ready */}
        {uploadedFile?.status !== "Ready" ? (
          <div className="pt-1 flex justify-center">
            <button
              type="button"
              onClick={handleRunPreselected}
              disabled={isProcessing || isAnalyzing}
              className="inline-flex items-center justify-center px-6 py-2.5 rounded-lg font-sans text-xs sm:text-sm font-medium tracking-wide bg-zinc-900 text-zinc-50 hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 transition-all active:scale-[0.99] disabled:opacity-50 cursor-pointer"
            >
              Run Preselected Protocol
            </button>
          </div>
        ) : (
          <div className="pt-2 space-y-3 animate-file-change">
            <p className="font-sans text-[11px] text-zinc-400 dark:text-zinc-500 text-center">
              Select next analysis process
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {NEXT_PROCESS_STEPS.map((step) => {
                const isSelected = selectedStep === step.id;
                return (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => handleSelectStep(step.id)}
                    className={`px-4 py-2.5 rounded-lg font-sans text-xs font-medium transition-all active:scale-[0.99] cursor-pointer text-center ${
                      isSelected
                        ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
                        : "bg-zinc-100/80 text-zinc-800 hover:bg-zinc-900 hover:text-zinc-50 dark:bg-zinc-800/60 dark:text-zinc-200 dark:hover:bg-zinc-100 dark:hover:text-zinc-900"
                    }`}
                  >
                    {step.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
