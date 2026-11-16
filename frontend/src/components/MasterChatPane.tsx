import React, { useState, useRef, useEffect } from 'react';
import {
  FileCheck2,
  Upload,
  ArrowUp,
  Play,
  RotateCcw,
  Sparkles,
  Download,
  Loader2,
  FolderOpen,
  Square,
} from 'lucide-react';
import type { ChatMessage, DocumentSummary, ProjectDetail, WorkspaceSample } from '../types';

interface MasterChatPaneProps {
  project: ProjectDetail;
  samples: WorkspaceSample[];
  uploadingRole: 'tender' | 'response' | null;
  uploadPct: number;
  sendingChat: boolean;
  onUploadFile: (role: 'tender' | 'response', file: File) => void;
  onMountSample: (role: 'tender' | 'response', filename: string) => void;
  onSendMessage: (msg: string) => void;
  onTriggerPlan: (targetLot?: string) => void;
  onStartRun: (recheckOnly: boolean) => void;
  onCancelTask: () => void;
  onSwitchInspectorTab: (tab: 'live' | 'report' | 'evidence') => void;
  readOnly?: boolean;
  exportedAt?: string;
  exportingHtml?: boolean;
  onExportHtml?: () => void;
  className?: string;
}

function renderFormattedLine(line: string): React.ReactNode {
  const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={idx} className="font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 mx-0.5 text-[11.5px] rounded-[4px] bg-black/[0.06] dark:bg-white/[0.1] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono tabular-nums"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function LiteMarkdown({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-1.5 leading-relaxed selectable-text">
      {lines.map((ln, i) => {
        const trimmed = ln.trim();
        if (!trimmed) return <div key={i} className="h-1" />;
        if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
          return (
            <div key={i} className="flex items-start gap-2 pl-0.5">
              <span className="text-[#007AFF] dark:text-[#409CFF] mt-[6px] w-1 h-1 rounded-full bg-current shrink-0" />
              <span className="flex-1">{renderFormattedLine(trimmed.slice(2))}</span>
            </div>
          );
        }
        return <p key={i}>{renderFormattedLine(trimmed)}</p>;
      })}
    </div>
  );
}

interface DocSlotCardProps {
  role: 'tender' | 'response';
  label: string;
  doc: DocumentSummary | null;
  samples: WorkspaceSample[];
  isUploading: boolean;
  uploadPct: number;
  onSelectFile: (file: File) => void;
  onSelectSample: (filename: string) => void;
  readOnly?: boolean;
  onReadOnlyClick?: () => void;
}

const DocSlotCard: React.FC<DocSlotCardProps> = ({
  role,
  label,
  doc,
  samples,
  isUploading,
  uploadPct,
  onSelectFile,
  onSelectSample,
  readOnly = false,
  onReadOnlyClick,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [showSamplePicker, setShowSamplePicker] = useState(false);
  const sampleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (sampleRef.current && !sampleRef.current.contains(e.target as Node)) {
        setShowSamplePicker(false);
      }
    };
    window.addEventListener('mousedown', h);
    return () => window.removeEventListener('mousedown', h);
  }, []);

  const roleSamples = samples.filter((s) => s.guessed_role === role);
  const displaySamples = roleSamples.length > 0 ? roleSamples : samples;
  const canBrowseResponse = readOnly && role === 'response' && Boolean(doc) && Boolean(onReadOnlyClick);

  return (
    <div
      title={canBrowseResponse ? '浏览响应文件原文' : doc?.filename}
      onDragOver={(e) => {
        if (readOnly) return;
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => {
        if (!readOnly) setDragOver(false);
      }}
      onDrop={(e) => {
        if (readOnly) return;
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onSelectFile(f);
      }}
      onClick={() => {
        if (readOnly) {
          if (canBrowseResponse) onReadOnlyClick?.();
          return;
        }
        if (!isUploading) inputRef.current?.click();
      }}
      className={`relative flex-1 min-w-0 h-[36px] rounded-[8px] px-2.5 flex items-center justify-between gap-2 transition-all ${
        readOnly ? (canBrowseResponse ? 'cursor-pointer' : 'cursor-default') : 'cursor-pointer'
      } ${
        dragOver
          ? 'border border-[#007AFF] dark:border-[#0A84FF] bg-[#007AFF]/[0.06] dark:bg-[#0A84FF]/[0.12]'
          : doc
            ? `macos-card ${!readOnly || canBrowseResponse ? 'hover:border-black/[0.15] dark:hover:border-white/[0.16]' : ''}`
            : 'border border-dashed border-black/[0.14] dark:border-white/[0.14] bg-black/[0.02] dark:bg-white/[0.025] hover:bg-black/[0.04] dark:hover:bg-white/[0.05]'
      }`}
    >
      {!readOnly && (
        <input
          ref={inputRef}
          type="file"
          accept=".docx,.pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onSelectFile(f);
            e.target.value = '';
          }}
        />
      )}

      <div className="flex items-center gap-2 min-w-0">
        {isUploading ? (
          <Loader2 className="w-3.5 h-3.5 text-[#007AFF] dark:text-[#0A84FF] animate-spin shrink-0" />
        ) : doc ? (
          <FileCheck2 className="w-3.5 h-3.5 text-[#34C759] dark:text-[#30D158] shrink-0" />
        ) : (
          <Upload className="w-3.5 h-3.5 text-[#8E8E93] shrink-0" />
        )}

        <span className="text-[11px] font-medium text-[#8E8E93] shrink-0">{label}</span>

        <span
          className={`text-[12px] truncate ${
            doc
              ? 'font-medium text-[#1D1D1F] dark:text-[#F5F5F7]'
              : 'text-[#8E8E93] dark:text-[#636366]'
          }`}
        >
          {isUploading ? `导入中 ${uploadPct}%` : doc ? doc.filename : readOnly ? '未导入' : '选择或拖入'}
        </span>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {doc && !isUploading && (
          <span className="text-[10.5px] text-[#8E8E93] tabular-nums">{doc.total_pages}页</span>
        )}

        {!readOnly && !isUploading && displaySamples.length > 0 && (
          <div
            ref={sampleRef}
            className="shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowSamplePicker((v) => !v)}
              title="工作区样本"
              className="w-6 h-6 rounded-[5px] text-[#8E8E93] hover:text-[#007AFF] dark:hover:text-[#409CFF] hover:bg-black/[0.05] dark:hover:bg-white/[0.08] flex items-center justify-center transition-colors"
            >
              <FolderOpen className="w-3.5 h-3.5" />
            </button>
            {showSamplePicker && (
              <div
                className={`absolute top-full mt-1.5 ${
                  role === 'tender' ? 'left-0' : 'right-0'
                } w-72 max-w-[calc(100vw-32px)] rounded-[10px] macos-popover p-1 z-40`}
              >
                {displaySamples.map((s) => (
                  <button
                    key={s.filename}
                    onClick={() => {
                      setShowSamplePicker(false);
                      onSelectSample(s.filename);
                    }}
                    className="w-full text-left px-2.5 py-1.5 rounded-[6px] text-[#1D1D1F] dark:text-[#F5F5F7] hover:bg-[#007AFF] dark:hover:bg-[#0A84FF] hover:text-white text-[11.5px] flex items-center justify-between gap-2 transition-colors"
                  >
                    <span className="truncate">{s.filename}</span>
                    <span className="text-[10.5px] opacity-65 shrink-0 tabular-nums">
                      {s.size_mb}M
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {isUploading && (
        <div className="absolute bottom-0 left-1 right-1 h-[2px] bg-black/[0.06] dark:bg-white/[0.08] rounded-full overflow-hidden">
          <div
            className="h-full bg-[#007AFF] dark:bg-[#0A84FF] transition-all duration-200"
            style={{ width: `${uploadPct}%` }}
          />
        </div>
      )}
    </div>
  );
};

export const MasterChatPane: React.FC<MasterChatPaneProps> = ({
  project,
  samples,
  uploadingRole,
  uploadPct,
  sendingChat,
  onUploadFile,
  onMountSample,
  onSendMessage,
  onTriggerPlan,
  onStartRun,
  onCancelTask,
  onSwitchInspectorTab,
  readOnly = false,
  exportedAt,
  exportingHtml = false,
  onExportHtml,
  className,
}) => {
  const [input, setInput] = useState('');
  const [lotOverrides, setLotOverrides] = useState<Record<string, string>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [project.messages.length, sendingChat]);

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || sendingChat || readOnly) return;
    setInput('');
    onSendMessage(trimmed);
  };

  const isRunning =
    project.telemetry.stage === 'inspecting' ||
    project.telemetry.stage === 'planning' ||
    project.telemetry.stage === 'assembling_report';

  const canConfirmStart =
    !readOnly && project.checklist.length > 0 && !isRunning && project.stage === 'awaiting_confirm';
  const canRecheck =
    !readOnly && project.checklist.length > 0 && !isRunning && project.stage === 'completed';

  return (
    <section
      className={`bg-white dark:bg-[#1E1E22] border-r border-black/[0.075] dark:border-white/[0.075] flex flex-col h-full ${
        className || 'flex-1 min-w-[320px]'
      }`}
    >
      {/* Dual Document Bar — aligned pixel-for-pixel with InspectorPane 52px header */}
      <div className="relative z-20 h-[52px] px-3.5 bg-[#FAFAFC]/85 dark:bg-[#1B1B1F]/85 backdrop-blur-md border-b border-black/[0.065] dark:border-white/[0.075] flex items-center gap-2.5 shrink-0">
        <DocSlotCard
          role="tender"
          label="招标"
          doc={project.tender_doc}
          samples={samples}
          isUploading={uploadingRole === 'tender'}
          uploadPct={uploadPct}
          onSelectFile={(f) => onUploadFile('tender', f)}
          onSelectSample={(fn) => onMountSample('tender', fn)}
          readOnly={readOnly}
        />
        <DocSlotCard
          role="response"
          label="响应"
          doc={project.response_doc}
          samples={samples}
          isUploading={uploadingRole === 'response'}
          uploadPct={uploadPct}
          onSelectFile={(f) => onUploadFile('response', f)}
          onSelectSample={(fn) => onMountSample('response', fn)}
          readOnly={readOnly}
          onReadOnlyClick={
            readOnly && project.response_doc ? () => onSwitchInspectorTab('evidence') : undefined
          }
        />
      </div>

      {/* Conversation Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {project.messages.length === 0 && !sendingChat && project.telemetry.stage !== 'planning' ? (
          <div className="h-full flex flex-col items-center justify-center text-[#8E8E93] gap-2.5">
            <div className="w-10 h-10 rounded-[11px] macos-well flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-[#007AFF] dark:text-[#0A84FF]" />
            </div>
            <span className="text-[12px] tracking-wide">
              {readOnly ? '暂无会话记录' : '置入招标与响应文件'}
            </span>
          </div>
        ) : (
          <div className="space-y-3.5">
            {project.messages.map((m: ChatMessage) => {
              const isUser = m.role === 'user';
              const hasReport = Boolean(project.report) || project.stage === 'completed';
              return (
                <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[86%] rounded-[12px] px-3.5 py-2.5 text-[13px] ${
                      isUser
                        ? 'macos-btn-primary rounded-br-[4px]'
                        : m.msg_type === 'error'
                          ? 'bg-[#FF3B30]/[0.08] dark:bg-[#FF453A]/[0.14] text-[#1D1D1F] dark:text-[#F5F5F7] border border-[#FF3B30]/20 dark:border-[#FF453A]/30 rounded-bl-[4px]'
                          : 'bg-[#F4F4F7] dark:bg-[#27272C] text-[#1D1D1F] dark:text-[#EAEAEF] border border-black/[0.045] dark:border-white/[0.065] shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] rounded-bl-[4px]'
                    }`}
                  >
                    {isUser ? (
                      <div className="whitespace-pre-wrap selectable-text">{m.content}</div>
                    ) : (
                      <LiteMarkdown text={m.content} />
                    )}

                    {/* Inline Precheck Action Bar (0-Token local parse gate) */}
                    {m.msg_type === 'precheck_card' && (() => {
                      const detectedLots = Array.isArray(m.meta?.detected_lots)
                        ? (m.meta.detected_lots as string[])
                        : [];
                      const parseLotCode = (raw: string) => {
                        const mt = raw.match(/^([A-Z0-9]+)/i);
                        return mt ? mt[1].toUpperCase() : raw;
                      };
                      const defaultLot = String(
                        m.meta?.target_lot ||
                          project.target_lot ||
                          (detectedLots[0] ? parseLotCode(detectedLots[0]) : ''),
                      );
                      const selectedLot = lotOverrides[m.id] ?? defaultLot;
                      const hasPlan = project.checklist.length > 0;
                      return (
                        <div className="mt-2.5 pt-2.5 border-t border-black/[0.07] dark:border-white/[0.08] space-y-2">
                          {detectedLots.length > 1 && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              {detectedLots.map((lotStr) => {
                                const code = parseLotCode(lotStr);
                                const active = selectedLot === code;
                                return (
                                  <button
                                    key={lotStr}
                                    type="button"
                                    disabled={isRunning || readOnly}
                                    onClick={() =>
                                      setLotOverrides((prev) => ({ ...prev, [m.id]: code }))
                                    }
                                    title={lotStr}
                                    className={`px-2 py-0.5 rounded-full text-[11px] font-medium transition-colors disabled:opacity-50 ${
                                      active
                                        ? 'bg-[#007AFF] dark:bg-[#0A84FF] text-white'
                                        : 'bg-black/[0.06] dark:bg-white/[0.09] text-[#515154] dark:text-[#AEAEB2] hover:bg-black/[0.1] dark:hover:bg-white/[0.14]'
                                    }`}
                                  >
                                    {code}标段
                                  </button>
                                );
                              })}
                            </div>
                          )}
                          <div className="flex items-center gap-2">
                            {!readOnly && (
                              <button
                                disabled={isRunning}
                                onClick={() => onTriggerPlan(selectedLot || undefined)}
                                className={`h-[27px] px-3 rounded-[6px] disabled:opacity-45 text-[12px] font-medium flex items-center gap-1.5 transition-all active:scale-[0.98] ${
                                  hasPlan
                                    ? 'macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7]'
                                    : 'macos-btn-primary'
                                }`}
                              >
                                {hasPlan ? (
                                  <RotateCcw className="w-3 h-3" />
                                ) : (
                                  <Sparkles className="w-3 h-3" />
                                )}
                                <span>{hasPlan ? '重新规划' : '生成检查计划'}</span>
                              </button>
                            )}
                            <button
                              onClick={() => onSwitchInspectorTab('live')}
                              className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[12px] font-medium transition-all active:scale-[0.98]"
                            >
                              查看预警
                            </button>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Inline Plan Action Bar */}
                    {m.msg_type === 'plan_card' && (
                      <div className="mt-2.5 pt-2.5 border-t border-black/[0.07] dark:border-white/[0.08] flex items-center gap-2">
                        {!readOnly && (
                          <button
                            disabled={isRunning}
                            onClick={() => onStartRun(false)}
                            className={`h-[27px] px-3 rounded-[6px] disabled:opacity-45 text-[12px] font-medium flex items-center gap-1.5 transition-all active:scale-[0.98] ${
                              hasReport
                                ? 'macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7]'
                                : 'macos-btn-primary'
                            }`}
                          >
                            {hasReport ? (
                              <RotateCcw className="w-3 h-3" />
                            ) : (
                              <Play className="w-3 h-3 fill-current" />
                            )}
                            <span>{hasReport ? '重新核查' : '开始核查'}</span>
                          </button>
                        )}
                        <button
                          onClick={() => onSwitchInspectorTab('live')}
                          className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[12px] font-medium transition-all active:scale-[0.98]"
                        >
                          查看清单
                        </button>
                      </div>
                    )}

                    {/* Inline Report Ready Action Bar */}
                    {m.msg_type === 'report_ready' && (
                      <div className="mt-2.5 pt-2.5 border-t border-black/[0.07] dark:border-white/[0.08] flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => onSwitchInspectorTab('report')}
                          className="h-[27px] px-3 rounded-[6px] macos-btn-primary text-[12px] font-medium transition-all active:scale-[0.98]"
                        >
                          查看报告
                        </button>
                        {!readOnly ? (
                          <button
                            type="button"
                            disabled={exportingHtml}
                            onClick={onExportHtml}
                            className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[12px] font-medium flex items-center gap-1.5 transition-all active:scale-[0.98] disabled:opacity-60"
                          >
                            {exportingHtml ? (
                              <Loader2 className="w-3 h-3 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
                            ) : (
                              <Download className="w-3 h-3 text-[#007AFF] dark:text-[#409CFF]" />
                            )}
                            <span>{exportingHtml ? '导出中…' : '导出报告'}</span>
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => onSwitchInspectorTab('live')}
                              className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[12px] font-medium transition-all active:scale-[0.98]"
                            >
                              查看清单
                            </button>
                            {project.response_doc && (
                              <button
                                type="button"
                                onClick={() => onSwitchInspectorTab('evidence')}
                                className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[12px] font-medium transition-all active:scale-[0.98]"
                              >
                                浏览原文
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {(sendingChat || project.telemetry.stage === 'planning') && (
              <div className="flex justify-start">
                <div className="rounded-[12px] rounded-bl-[4px] bg-[#F4F4F7] dark:bg-[#27272C] border border-black/[0.045] dark:border-white/[0.065] px-3 py-2 text-[12px] text-[#6E6E73] dark:text-[#98989D] flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
                  <span>{project.telemetry.stage === 'planning' ? '规划中…' : '思考中…'}</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Bottom Input Composer or Read-Only Snapshot Footer */}
      {readOnly ? (
        <div className="h-[38px] px-3.5 border-t border-black/[0.06] dark:border-white/[0.07] bg-[#FAFAFC]/70 dark:bg-[#1B1B1F]/70 text-[11px] text-[#8E8E93] flex items-center justify-between tabular-nums shrink-0">
          <span>标书智检 · 交互式报告</span>
          {exportedAt && <span>{exportedAt}</span>}
        </div>
      ) : (
        <div className="p-3 border-t border-black/[0.06] dark:border-white/[0.07] bg-[#FAFAFC]/70 dark:bg-[#1B1B1F]/70 backdrop-blur-md">
          {(isRunning ||
            canConfirmStart ||
            canRecheck ||
            (project.tender_doc &&
              project.response_doc &&
              project.checklist.length === 0 &&
              !isRunning)) && (
            <div className="flex items-center gap-1.5 mb-2">
              {isRunning && (
                <button
                  onClick={onCancelTask}
                  className="px-2.5 py-1 rounded-full bg-[#FF3B30]/10 dark:bg-[#FF453A]/18 hover:bg-[#FF3B30]/18 dark:hover:bg-[#FF453A]/28 text-[#FF3B30] dark:text-[#FF6961] text-[11.5px] font-medium flex items-center gap-1 transition-colors"
                >
                  <Square className="w-2.5 h-2.5 fill-current" />
                  <span>停止</span>
                </button>
              )}
              {project.tender_doc &&
                project.response_doc &&
                project.checklist.length === 0 &&
                !isRunning && (
                  <button
                    onClick={() => onTriggerPlan()}
                    className="px-2.5 py-1 rounded-full bg-[#007AFF]/10 dark:bg-[#0A84FF]/18 hover:bg-[#007AFF]/16 dark:hover:bg-[#0A84FF]/26 text-[#007AFF] dark:text-[#409CFF] text-[11.5px] font-medium transition-colors"
                  >
                    生成清单
                  </button>
                )}
              {canConfirmStart && (
                <button
                  onClick={() => onStartRun(false)}
                  className="px-2.5 py-1 rounded-full bg-[#007AFF]/10 dark:bg-[#0A84FF]/18 hover:bg-[#007AFF]/16 dark:hover:bg-[#0A84FF]/26 text-[#007AFF] dark:text-[#409CFF] text-[11.5px] font-medium flex items-center gap-1 transition-colors"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>开始核查</span>
                </button>
              )}
              {canRecheck && (
                <button
                  onClick={() => onStartRun(true)}
                  className="px-2.5 py-1 rounded-full macos-btn-secondary text-[#1D1D1F] dark:text-[#F5F5F7] text-[11.5px] font-medium flex items-center gap-1 transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>复检问题项</span>
                </button>
              )}
            </div>
          )}

          <div className="flex items-end gap-2 rounded-[10px] macos-input px-3 py-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="输入指令…"
              className="flex-1 bg-transparent resize-none outline-none text-[13px] text-[#1D1D1F] dark:text-[#F5F5F7] placeholder:text-[#8E8E93] dark:placeholder:text-[#636366] max-h-28 leading-5"
            />
            <button
              disabled={!input.trim() || sendingChat}
              onClick={submit}
              className="w-6 h-6 rounded-full bg-[#007AFF] dark:bg-[#0A84FF] disabled:bg-black/[0.1] dark:disabled:bg-white/[0.1] text-white disabled:text-white/50 flex items-center justify-center shrink-0 transition-all active:scale-95"
            >
              <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
