import React, { useState, useRef, useEffect } from 'react';
import {
  PanelLeft,
  Settings,
  Download,
  Activity,
  FileText,
  FileSpreadsheet,
  ChevronDown,
} from 'lucide-react';
import type { ProjectDetail, TelemetrySnapshot } from '../types';

interface TopToolbarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  project: ProjectDetail | null;
  telemetry: TelemetrySnapshot | null;
  onOpenSettings: () => void;
}

function formatDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || sec <= 0) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export const TopToolbar: React.FC<TopToolbarProps> = ({
  sidebarOpen,
  onToggleSidebar,
  project,
  telemetry,
  onOpenSettings,
}) => {
  const [showTelemetryPopover, setShowTelemetryPopover] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const expRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setShowTelemetryPopover(false);
      }
      if (expRef.current && !expRef.current.contains(e.target as Node)) {
        setShowExportMenu(false);
      }
    };
    window.addEventListener('mousedown', handler);
    return () => window.removeEventListener('mousedown', handler);
  }, []);

  const stage = telemetry?.stage || 'idle';
  const isBusy = stage === 'parsing' || stage === 'planning' || stage === 'inspecting' || stage === 'assembling_report';
  const activeCallSum = (telemetry?.active_models || []).reduce((acc, m) => acc + m.active_calls, 0);

  const dotColor =
    stage === 'completed'
      ? 'bg-[#34C759]'
      : stage === 'error'
        ? 'bg-[#FF3B30]'
        : stage === 'awaiting_confirm'
          ? 'bg-[#FF9500]'
          : isBusy
            ? 'bg-[#007AFF] animate-pulse'
            : 'bg-[#8E8E93]';

  const canExportDocx = Boolean(project?.report);
  const canExportXlsx = Boolean(project && project.checklist.length > 0);

  return (
    <header className="h-[46px] shrink-0 bg-white/85 backdrop-blur-xl border-b border-black/[0.08] px-3.5 flex items-center justify-between gap-3 z-20">
      {/* Left: Sidebar toggle + Project Title */}
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={onToggleSidebar}
          title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
          className="p-1.5 rounded-[6px] text-[#515154] hover:bg-black/[0.06] active:bg-black/[0.1] transition-colors"
        >
          <PanelLeft className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[13px] font-semibold text-[#1D1D1F] truncate max-w-[260px]">
            {project?.name || '标书智检'}
          </span>
          {project?.target_lot && (
            <span className="px-1.5 py-0.5 text-[11px] font-medium rounded-[5px] bg-[#007AFF]/10 text-[#007AFF] shrink-0">
              {project.target_lot}标段
            </span>
          )}
        </div>
      </div>

      {/* Center: Compact Live Telemetry Capsule */}
      {telemetry && (
        <div className="relative" ref={popRef}>
          <button
            onClick={() => setShowTelemetryPopover((v) => !v)}
            className="h-[30px] px-3 rounded-full bg-black/[0.04] hover:bg-black/[0.07] border border-black/[0.06] flex items-center gap-3 text-[12px] text-[#1D1D1F] tabular-nums transition-colors"
          >
            <span className="flex items-center gap-1.5 font-medium">
              <span className={`w-2 h-2 rounded-full ${dotColor}`} />
              <span>{telemetry.stage_label}</span>
            </span>

            {telemetry.total_items > 0 && (
              <>
                <span className="w-[1px] h-3 bg-black/[0.12]" />
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 bg-black/[0.08] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#007AFF] transition-all duration-300 rounded-full"
                      style={{ width: `${Math.min(100, telemetry.progress_pct)}%` }}
                    />
                  </div>
                  <span className="text-[11px] text-[#6E6E73]">{telemetry.progress_pct.toFixed(0)}%</span>
                </div>
              </>
            )}

            {(isBusy && telemetry.eta_seconds !== null) ? (
              <>
                <span className="w-[1px] h-3 bg-black/[0.12]" />
                <span className="text-[11px] text-[#6E6E73]">
                  剩余 {formatDuration(telemetry.eta_seconds)}
                </span>
              </>
            ) : (
              stage === 'awaiting_confirm' &&
              telemetry.estimated_plan_seconds > 0 && (
                <>
                  <span className="w-[1px] h-3 bg-black/[0.12]" />
                  <span className="text-[11px] text-[#6E6E73]">
                    预估 {formatDuration(telemetry.estimated_plan_seconds)}
                  </span>
                </>
              )
            )}

            <span className="w-[1px] h-3 bg-black/[0.12]" />
            <span className="text-[11px] text-[#515154] flex items-center gap-1">
              <Activity className="w-3 h-3 text-[#007AFF]" />
              <span>{formatTokens(telemetry.total_tokens)}</span>
              <span className="text-[#8E8E93]">·</span>
              <span>¥{telemetry.estimated_cost.toFixed(3)}</span>
              {activeCallSum > 0 && (
                <span className="ml-0.5 px-1.5 py-0.2 rounded-full bg-[#007AFF] text-white text-[10px]">
                  {activeCallSum} 并发
                </span>
              )}
            </span>
          </button>

          {showTelemetryPopover && (
            <div className="absolute left-1/2 -translate-x-1/2 mt-2 w-[360px] rounded-[12px] bg-white/95 backdrop-blur-2xl shadow-[0_12px_36px_rgba(0,0,0,0.14)] border border-black/[0.08] p-3.5 text-[12px] z-50">
              <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-black/[0.06]">
                <span className="font-semibold text-[#1D1D1F]">模型调度与 Token 明细</span>
                <span className="text-[11px] text-[#6E6E73] tabular-nums">
                  已耗时 {formatDuration(telemetry.elapsed_seconds)}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 mb-3 tabular-nums">
                <div className="bg-[#F5F5F7] rounded-[8px] p-2">
                  <div className="text-[10px] text-[#8E8E93]">输入 Tokens</div>
                  <div className="text-[13px] font-semibold mt-0.5">{formatTokens(telemetry.prompt_tokens)}</div>
                </div>
                <div className="bg-[#F5F5F7] rounded-[8px] p-2">
                  <div className="text-[10px] text-[#8E8E93]">输出 Tokens</div>
                  <div className="text-[13px] font-semibold mt-0.5">{formatTokens(telemetry.completion_tokens)}</div>
                </div>
                <div className="bg-[#F5F5F7] rounded-[8px] p-2">
                  <div className="text-[10px] text-[#8E8E93]">累计预估费用</div>
                  <div className="text-[13px] font-semibold text-[#007AFF] mt-0.5">
                    ¥{telemetry.estimated_cost.toFixed(4)}
                  </div>
                </div>
              </div>

              {telemetry.active_models.length === 0 ? (
                <div className="text-center py-3 text-[#8E8E93] text-[12px]">尚无模型调用记录</div>
              ) : (
                <div className="space-y-1.5">
                  {telemetry.active_models.map((m) => (
                    <div
                      key={`${m.role}-${m.model}`}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded-[7px] bg-[#FAFAFC] border border-black/[0.04] tabular-nums"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              m.active_calls > 0 ? 'bg-[#007AFF] animate-ping' : 'bg-[#34C759]'
                            }`}
                          />
                          <span className="font-medium text-[#1D1D1F] truncate">{m.role_label}</span>
                        </div>
                        <div className="text-[11px] text-[#8E8E93] truncate">{m.model}</div>
                      </div>
                      <div className="text-right shrink-0 ml-2">
                        <div className="text-[11px] font-medium text-[#1D1D1F]">
                          {formatTokens(m.total_tokens)} · {m.total_calls}次
                        </div>
                        <div className="text-[10px] text-[#8E8E93]">
                          {m.active_calls > 0 ? `运行中 ${m.active_calls}` : `¥${m.cost.toFixed(4)}`}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Right: Export & Settings */}
      <div className="flex items-center gap-1.5">
        {project && (canExportDocx || canExportXlsx) && (
          <div className="relative" ref={expRef}>
            <button
              onClick={() => setShowExportMenu((v) => !v)}
              className="h-[28px] px-2.5 rounded-[6px] bg-black/[0.04] hover:bg-black/[0.08] text-[12px] font-medium text-[#1D1D1F] flex items-center gap-1 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>导出</span>
              <ChevronDown className="w-3 h-3 text-[#8E8E93]" />
            </button>

            {showExportMenu && (
              <div className="absolute right-0 mt-1.5 w-44 rounded-[10px] bg-white/95 backdrop-blur-xl shadow-[0_10px_28px_rgba(0,0,0,0.14)] border border-black/[0.08] p-1 text-[12px] z-50">
                <a
                  href={canExportDocx ? `/api/projects/${project.id}/export/docx` : undefined}
                  onClick={(e) => {
                    if (!canExportDocx) e.preventDefault();
                    else setShowExportMenu(false);
                  }}
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-[6px] ${
                    canExportDocx
                      ? 'text-[#1D1D1F] hover:bg-[#007AFF] hover:text-white'
                      : 'text-[#C7C7CC] cursor-not-allowed'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Word 检查报告 (.docx)</span>
                </a>
                <a
                  href={canExportXlsx ? `/api/projects/${project.id}/export/xlsx` : undefined}
                  onClick={(e) => {
                    if (!canExportXlsx) e.preventDefault();
                    else setShowExportMenu(false);
                  }}
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-[6px] ${
                    canExportXlsx
                      ? 'text-[#1D1D1F] hover:bg-[#007AFF] hover:text-white'
                      : 'text-[#C7C7CC] cursor-not-allowed'
                  }`}
                >
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  <span>Excel 整改销项表 (.xlsx)</span>
                </a>
              </div>
            )}
          </div>
        )}

        <button
          onClick={onOpenSettings}
          title="模型与系统配置 (⌘,)"
          className="h-[28px] px-2.5 rounded-[6px] hover:bg-black/[0.06] active:bg-black/[0.1] text-[#515154] flex items-center gap-1.5 text-[12px] transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
          <span>模型配置</span>
        </button>
      </div>
    </header>
  );
};
