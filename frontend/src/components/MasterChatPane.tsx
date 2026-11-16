import React, { useState, useRef, useEffect } from 'react';
import {
  FileCheck2,
  Upload,
  ArrowUp,
  Play,
  RotateCcw,
  Sparkles,
  FileText,
  FileSpreadsheet,
  Loader2,
  FolderOpen,
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
  onStartRun: (recheckOnly: boolean) => void;
  onSwitchInspectorTab: (tab: 'live' | 'report' | 'evidence') => void;
}

function renderFormattedLine(line: string): React.ReactNode {
  const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={idx} className="font-semibold text-[#1D1D1F]">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 mx-0.5 text-[11.5px] rounded-[4px] bg-black/[0.06] text-[#1D1D1F] font-mono tabular-nums"
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
            <div key={i} className="flex items-start gap-2 pl-1">
              <span className="text-[#007AFF] mt-1 text-[10px]">●</span>
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

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onSelectFile(f);
      }}
      onClick={() => !isUploading && inputRef.current?.click()}
      className={`relative flex-1 min-w-0 rounded-[9px] px-3 py-2 border transition-all cursor-pointer ${
        dragOver
          ? 'border-[#007AFF] bg-[#007AFF]/[0.05]'
          : doc
            ? 'border-black/[0.08] bg-white hover:border-black/[0.15]'
            : 'border-dashed border-black/[0.14] bg-white/70 hover:bg-white hover:border-black/[0.22]'
      }`}
    >
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

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {isUploading ? (
            <Loader2 className="w-4 h-4 text-[#007AFF] animate-spin shrink-0" />
          ) : doc ? (
            <FileCheck2 className="w-4 h-4 text-[#34C759] shrink-0" />
          ) : (
            <Upload className="w-3.5 h-3.5 text-[#8E8E93] shrink-0" />
          )}

          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-[#8E8E93]">{label}</span>
              {doc && (
                <span className="text-[10.5px] text-[#6E6E73] tabular-nums">
                  {doc.total_pages}页
                  {doc.total_images > 0 ? ` · ${doc.total_images}图` : ''}
                  {doc.deterministic_count > 0 ? ` · ${doc.deterministic_count}提醒` : ''}
                </span>
              )}
            </div>
            <div className="text-[12px] font-medium text-[#1D1D1F] truncate">
              {isUploading
                ? `正在导入 (${uploadPct}%)…`
                : doc
                  ? doc.filename
                  : '拖入或点击选择 .docx / .pdf'}
            </div>
          </div>
        </div>

        {!isUploading && displaySamples.length > 0 && (
          <div
            ref={sampleRef}
            className="relative shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowSamplePicker((v) => !v)}
              title="挂载工作区标书"
              className="p-1 rounded-[5px] text-[#8E8E93] hover:text-[#007AFF] hover:bg-[#007AFF]/10 transition-colors"
            >
              <FolderOpen className="w-3.5 h-3.5" />
            </button>
            {showSamplePicker && (
              <div className="absolute right-0 mt-1.5 w-72 rounded-[10px] bg-white shadow-[0_10px_28px_rgba(0,0,0,0.14)] border border-black/[0.08] p-1 z-40">
                {displaySamples.map((s) => (
                  <button
                    key={s.filename}
                    onClick={() => {
                      setShowSamplePicker(false);
                      onSelectSample(s.filename);
                    }}
                    className="w-full text-left px-2.5 py-1.5 rounded-[6px] hover:bg-[#007AFF] hover:text-white text-[11.5px] flex items-center justify-between gap-2 group"
                  >
                    <span className="truncate">{s.filename}</span>
                    <span className="text-[10.5px] opacity-65 shrink-0 tabular-nums">
                      {s.size_mb}MB
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {isUploading && (
        <div className="mt-1.5 h-1 w-full bg-black/[0.06] rounded-full overflow-hidden">
          <div
            className="h-full bg-[#007AFF] transition-all duration-200"
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
  onStartRun,
  onSwitchInspectorTab,
}) => {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [project.messages.length, sendingChat]);

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || sendingChat) return;
    setInput('');
    onSendMessage(trimmed);
  };

  const isRunning =
    project.telemetry.stage === 'inspecting' ||
    project.telemetry.stage === 'planning' ||
    project.telemetry.stage === 'assembling_report';

  const canConfirmStart = project.checklist.length > 0 && !isRunning && project.stage === 'awaiting_confirm';
  const canRecheck = project.checklist.length > 0 && !isRunning && project.stage === 'completed';

  return (
    <section className="flex-1 min-w-[380px] bg-white border-r border-black/[0.08] flex flex-col h-full">
      {/* Dual Document Mount Bar */}
      <div className="px-3.5 py-2.5 bg-[#FAFAFC] border-b border-black/[0.06] flex items-center gap-2.5">
        <DocSlotCard
          role="tender"
          label="官方招标文件"
          doc={project.tender_doc}
          samples={samples}
          isUploading={uploadingRole === 'tender'}
          uploadPct={uploadPct}
          onSelectFile={(f) => onUploadFile('tender', f)}
          onSelectSample={(fn) => onMountSample('tender', fn)}
        />
        <DocSlotCard
          role="response"
          label="我方响应文件"
          doc={project.response_doc}
          samples={samples}
          isUploading={uploadingRole === 'response'}
          uploadPct={uploadPct}
          onSelectFile={(f) => onUploadFile('response', f)}
          onSelectSample={(fn) => onMountSample('response', fn)}
        />
      </div>

      {/* Conversation Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {project.messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-[#8E8E93] gap-2">
            <div className="w-9 h-9 rounded-[10px] bg-[#F5F5F7] flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-[#007AFF]" />
            </div>
            <span className="text-[12.5px]">挂载招标文件与响应文件后由 Master 自动制定核查计划</span>
          </div>
        ) : (
          project.messages.map((m: ChatMessage) => {
            const isUser = m.role === 'user';
            return (
              <div
                key={m.id}
                className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[88%] rounded-[12px] px-3.5 py-2.5 text-[13px] ${
                    isUser
                      ? 'bg-[#007AFF] text-white rounded-br-[4px]'
                      : m.msg_type === 'error'
                        ? 'bg-[#FF3B30]/[0.08] text-[#1D1D1F] border border-[#FF3B30]/20 rounded-bl-[4px]'
                        : 'bg-[#F5F5F7] text-[#1D1D1F] border border-black/[0.04] rounded-bl-[4px]'
                  }`}
                >
                  {isUser ? (
                    <div className="whitespace-pre-wrap selectable-text">{m.content}</div>
                  ) : (
                    <LiteMarkdown text={m.content} />
                  )}

                  {/* Inline Plan Action Bar */}
                  {m.msg_type === 'plan_card' && (
                    <div className="mt-3 pt-2.5 border-t border-black/[0.08] flex items-center gap-2">
                      <button
                        disabled={isRunning}
                        onClick={() => onStartRun(false)}
                        className="h-[28px] px-3 rounded-[6px] bg-[#007AFF] hover:bg-[#0066D6] disabled:opacity-45 text-white text-[12px] font-medium flex items-center gap-1.5 transition-colors"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>开始并发检查</span>
                      </button>
                      <button
                        onClick={() => onSwitchInspectorTab('live')}
                        className="h-[28px] px-2.5 rounded-[6px] bg-white hover:bg-black/[0.04] border border-black/[0.1] text-[#1D1D1F] text-[12px] font-medium transition-colors"
                      >
                        审阅清单条目
                      </button>
                    </div>
                  )}

                  {/* Inline Report Ready Action Bar */}
                  {m.msg_type === 'report_ready' && (
                    <div className="mt-3 pt-2.5 border-t border-black/[0.08] flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => onSwitchInspectorTab('report')}
                        className="h-[28px] px-3 rounded-[6px] bg-[#007AFF] hover:bg-[#0066D6] text-white text-[12px] font-medium transition-colors"
                      >
                        查看结构化报告
                      </button>
                      <a
                        href={`/api/projects/${project.id}/export/docx`}
                        className="h-[28px] px-2.5 rounded-[6px] bg-white hover:bg-black/[0.04] border border-black/[0.1] text-[#1D1D1F] text-[12px] font-medium flex items-center gap-1 transition-colors"
                      >
                        <FileText className="w-3 h-3 text-[#007AFF]" />
                        <span>Word 报告</span>
                      </a>
                      <a
                        href={`/api/projects/${project.id}/export/xlsx`}
                        className="h-[28px] px-2.5 rounded-[6px] bg-white hover:bg-black/[0.04] border border-black/[0.1] text-[#1D1D1F] text-[12px] font-medium flex items-center gap-1 transition-colors"
                      >
                        <FileSpreadsheet className="w-3 h-3 text-[#34C759]" />
                        <span>Excel 销项表</span>
                      </a>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {(sendingChat || project.telemetry.stage === 'planning') && (
          <div className="flex justify-start">
            <div className="rounded-[12px] rounded-bl-[4px] bg-[#F5F5F7] px-3.5 py-2 text-[12.5px] text-[#6E6E73] flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF]" />
              <span>
                {project.telemetry.stage === 'planning' ? 'Master 正在规整核查工作流…' : 'Master 思考中…'}
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Bottom Input Composer */}
      <div className="p-3 border-t border-black/[0.06] bg-white">
        {(canConfirmStart || canRecheck || (project.tender_doc && project.response_doc && project.checklist.length === 0 && !isRunning)) && (
          <div className="flex items-center gap-1.5 mb-2">
            {project.tender_doc && project.response_doc && project.checklist.length === 0 && !isRunning && (
              <button
                onClick={() => onSendMessage('生成检查计划')}
                className="px-2.5 py-1 rounded-full bg-[#007AFF]/10 hover:bg-[#007AFF]/15 text-[#007AFF] text-[11.5px] font-medium transition-colors"
              >
                生成检查计划
              </button>
            )}
            {canConfirmStart && (
              <button
                onClick={() => onStartRun(false)}
                className="px-2.5 py-1 rounded-full bg-[#007AFF]/10 hover:bg-[#007AFF]/15 text-[#007AFF] text-[11.5px] font-medium flex items-center gap-1 transition-colors"
              >
                <Play className="w-3 h-3 fill-current" />
                <span>开始检查</span>
              </button>
            )}
            {canRecheck && (
              <button
                onClick={() => onStartRun(true)}
                className="px-2.5 py-1 rounded-full bg-[#F5F5F7] hover:bg-black/[0.07] text-[#1D1D1F] text-[11.5px] font-medium flex items-center gap-1 transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                <span>仅复检问题项</span>
              </button>
            )}
          </div>
        )}

        <div className="flex items-end gap-2 rounded-[10px] border border-black/[0.12] focus-within:border-[#007AFF] bg-[#FAFAFC] px-3 py-2 transition-colors">
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
            placeholder="向 Master Agent 发送指令…"
            className="flex-1 bg-transparent resize-none outline-none text-[13px] text-[#1D1D1F] placeholder:text-[#8E8E93] max-h-28 leading-5"
          />
          <button
            disabled={!input.trim() || sendingChat}
            onClick={submit}
            className="w-6 h-6 rounded-full bg-[#007AFF] disabled:bg-black/[0.12] text-white flex items-center justify-center shrink-0 transition-colors"
          >
            <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
          </button>
        </div>
      </div>
    </section>
  );
};
