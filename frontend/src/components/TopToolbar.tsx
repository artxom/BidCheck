import React, { useState, useRef, useEffect } from 'react';
import {
  PanelLeft,
  SlidersHorizontal,
  Download,
  Activity,
  Loader2,
  Sun,
  Moon,
  Square,
} from 'lucide-react';
import type { ProjectDetail, TelemetrySnapshot } from '../types';

interface TopToolbarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  project: ProjectDetail | null;
  telemetry: TelemetrySnapshot | null;
  resolvedTheme: 'light' | 'dark';
  onToggleTheme: () => void;
  onOpenSettings: () => void;
  onCancelTask?: () => void;
  readOnly?: boolean;
  exportingHtml?: boolean;
  onExportHtml?: () => void;
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

function formatCost(c: number): string {
  if (c <= 0) return '¥0.00';
  if (c < 0.01) return `¥${c.toFixed(3)}`;
  return `¥${c.toFixed(2)}`;
}

function compactStageLabel(t: TelemetrySnapshot): string {
  switch (t.stage) {
    case 'parsing':
      return '解析中';
    case 'planning':
      return '规划中';
    case 'awaiting_confirm':
      return t.stage_label === '待复检' ? '待复检' : '待确认';
    case 'inspecting':
      return t.total_items > 0 ? `核查中 ${t.completed_items}/${t.total_items}` : '核查中';
    case 'assembling_report':
      return '汇总中';
    case 'completed':
      return '已完成';
    case 'error':
      return '异常';
    default:
      if (t.stage_label.includes('密钥') || t.stage_label.includes('Key')) return '待配置密钥';
      if (t.stage_label === '待生成清单') return '待生成清单';
      if (t.stage_label === '已停止') return '已停止';
      if (t.stage_label.includes('补齐') || t.stage_label.includes('导入')) return '待导入文档';
      return '就绪';
  }
}

export const TopToolbar: React.FC<TopToolbarProps> = ({
  sidebarOpen,
  onToggleSidebar,
  project,
  telemetry,
  resolvedTheme,
  onToggleTheme,
  onOpenSettings,
  onCancelTask,
  readOnly = false,
  exportingHtml = false,
  onExportHtml,
}) => {
  const [showTelemetryPopover, setShowTelemetryPopover] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setShowTelemetryPopover(false);
      }
    };
    window.addEventListener('mousedown', handler);
    return () => window.removeEventListener('mousedown', handler);
  }, []);

  const stage = telemetry?.stage || 'idle';
  const isBusy =
    stage === 'parsing' ||
    stage === 'planning' ||
    stage === 'inspecting' ||
    stage === 'assembling_report';
  const activeCallSum = (telemetry?.active_models || []).reduce((acc, m) => acc + m.active_calls, 0);

  const dotColor =
    stage === 'completed'
      ? 'bg-[#34C759] dark:bg-[#30D158]'
      : stage === 'error'
        ? 'bg-[#FF3B30] dark:bg-[#FF453A]'
        : stage === 'awaiting_confirm'
          ? 'bg-[#FF9500] dark:bg-[#FF9F0A]'
          : isBusy
            ? 'bg-[#007AFF] dark:bg-[#0A84FF] animate-pulse'
            : 'bg-[#8E8E93] dark:bg-[#636366]';

  const canExportHtml = Boolean(project && (project.report || project.checklist.length > 0));
  const sidebarToggleTitle = readOnly
    ? sidebarOpen
      ? '收起会话栏 (⌘\\)'
      : '展开会话栏 (⌘\\)'
    : sidebarOpen
      ? '收起侧栏 (⌘\\)'
      : '展开侧栏 (⌘\\)';

  return (
    <header className="h-[44px] shrink-0 macos-toolbar px-3 flex items-center justify-between gap-3 z-30">
      {/* Left: Sidebar toggle + Project Title */}
      <div className="flex-1 flex items-center gap-2 min-w-0 overflow-hidden">
        <button
          onClick={onToggleSidebar}
          title={sidebarToggleTitle}
          className={`w-7 h-7 rounded-[6px] shrink-0 flex items-center justify-center transition-colors ${
            sidebarOpen
              ? 'text-[#1D1D1F] dark:text-[#F5F5F7] bg-black/[0.05] dark:bg-white/[0.07]'
              : 'text-[#6E6E73] dark:text-[#98989D] hover:bg-black/[0.05] dark:hover:bg-white/[0.07]'
          }`}
        >
          <PanelLeft className="w-[15px] h-[15px]" />
        </button>

        <span className="w-[1px] h-3.5 bg-black/[0.08] dark:bg-white/[0.1] shrink-0" />

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[13px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] truncate max-w-[280px]">
            {project?.name || '标书智检'}
          </span>
          {project?.target_lot && (
            <span className="hidden sm:inline-flex px-1.5 py-[1px] text-[10.5px] font-semibold rounded-[5px] bg-[#007AFF]/10 dark:bg-[#0A84FF]/18 text-[#007AFF] dark:text-[#409CFF] shrink-0">
              {project.target_lot}标段
            </span>
          )}
          {readOnly && (
            <span className="hidden md:inline-flex px-1.5 py-[1px] text-[10.5px] font-medium rounded-[5px] bg-black/[0.05] dark:bg-white/[0.08] text-[#6E6E73] dark:text-[#98989D] shrink-0">
              离线报告
            </span>
          )}
        </div>
      </div>

      {/* Center: Xcode-style Live Activity Capsule */}
      {telemetry && (
        <div className="shrink-0 flex items-center gap-1.5">
          <div className="relative" ref={popRef}>
            <button
              onClick={() => setShowTelemetryPopover((v) => !v)}
              className="h-[28px] px-3 rounded-full macos-capsule flex items-center gap-2.5 text-[11.5px] text-[#1D1D1F] dark:text-[#E5E5EA] tabular-nums transition-all active:scale-[0.99]"
            >
              <span className="flex items-center gap-1.5 font-medium">
                <span className={`w-[7px] h-[7px] rounded-full ${dotColor}`} />
                <span>{compactStageLabel(telemetry)}</span>
              </span>

              {telemetry.total_items > 0 && (
                <>
                  <span className="hidden sm:block w-[1px] h-3 bg-black/[0.1] dark:bg-white/[0.12]" />
                  <div className="hidden sm:flex items-center gap-1.5">
                    <div className="w-14 h-[5px] bg-black/[0.08] dark:bg-white/[0.12] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#007AFF] dark:bg-[#0A84FF] transition-all duration-300 rounded-full"
                        style={{ width: `${Math.min(100, telemetry.progress_pct)}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-[#6E6E73] dark:text-[#98989D]">
                      {telemetry.progress_pct.toFixed(0)}%
                    </span>
                  </div>
                </>
              )}

              {isBusy && telemetry.eta_seconds !== null && telemetry.eta_seconds > 0 ? (
                <>
                  <span className="w-[1px] h-3 bg-black/[0.1] dark:bg-white/[0.12]" />
                  <span className="text-[11px] text-[#6E6E73] dark:text-[#98989D]">
                    -{formatDuration(telemetry.eta_seconds)}
                  </span>
                </>
              ) : isBusy ? (
                <>
                  <span className="w-[1px] h-3 bg-black/[0.1] dark:bg-white/[0.12]" />
                  <span className="text-[11px] text-[#6E6E73] dark:text-[#98989D]">
                    {formatDuration(telemetry.elapsed_seconds)}
                  </span>
                </>
              ) : (
                stage === 'awaiting_confirm' &&
                telemetry.estimated_plan_seconds > 0 && (
                  <>
                    <span className="w-[1px] h-3 bg-black/[0.1] dark:bg-white/[0.12]" />
                    <span className="text-[11px] text-[#6E6E73] dark:text-[#98989D]">
                      ~{formatDuration(telemetry.estimated_plan_seconds)}
                    </span>
                  </>
                )
              )}

              <span className="w-[1px] h-3 bg-black/[0.1] dark:bg-white/[0.12]" />
              <span className="text-[11px] text-[#515154] dark:text-[#AEAEB2] flex items-center gap-1">
                <Activity className="w-3 h-3 text-[#007AFF] dark:text-[#0A84FF]" />
                <span>{formatTokens(telemetry.total_tokens)}</span>
                <span className="text-[#8E8E93] dark:text-[#636366]">·</span>
                <span>{formatCost(telemetry.estimated_cost)}</span>
                {activeCallSum > 0 && (
                  <span className="ml-0.5 px-1.5 py-[0.5px] rounded-full bg-[#007AFF] dark:bg-[#0A84FF] text-white text-[10px] font-medium">
                    {activeCallSum}
                  </span>
                )}
              </span>
            </button>

            {showTelemetryPopover && (
              <div className="fixed sm:absolute top-[50px] sm:top-auto left-1/2 -translate-x-1/2 sm:mt-2 w-[min(336px,calc(100vw-24px))] rounded-[12px] macos-popover p-3 text-[12px] z-50">
                <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-black/[0.06] dark:border-white/[0.08]">
                  <span className="font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">模型用量</span>
                  <span className="text-[11px] text-[#6E6E73] dark:text-[#98989D] tabular-nums">
                    {formatDuration(telemetry.elapsed_seconds)}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 mb-2.5 tabular-nums">
                  <div className="macos-well rounded-[8px] p-2">
                    <div className="text-[10px] text-[#8E8E93] dark:text-[#8E8E93]">输入</div>
                    <div className="text-[13px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] mt-0.5">
                      {formatTokens(telemetry.prompt_tokens)}
                    </div>
                  </div>
                  <div className="macos-well rounded-[8px] p-2">
                    <div className="text-[10px] text-[#8E8E93] dark:text-[#8E8E93]">输出</div>
                    <div className="text-[13px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] mt-0.5">
                      {formatTokens(telemetry.completion_tokens)}
                    </div>
                  </div>
                  <div className="macos-well rounded-[8px] p-2">
                    <div className="text-[10px] text-[#8E8E93] dark:text-[#8E8E93]">费用</div>
                    <div className="text-[13px] font-semibold text-[#007AFF] dark:text-[#409CFF] mt-0.5">
                      ¥{telemetry.estimated_cost.toFixed(4)}
                    </div>
                  </div>
                </div>

                {telemetry.active_models.length === 0 ? (
                  <div className="text-center py-2.5 text-[#8E8E93] text-[11.5px]">暂无记录</div>
                ) : (
                  <div className="space-y-1.5">
                    {telemetry.active_models.map((m) => (
                      <div
                        key={`${m.role}-${m.model}`}
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-[7px] macos-well tabular-nums"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                m.active_calls > 0
                                  ? 'bg-[#007AFF] dark:bg-[#0A84FF] animate-ping'
                                  : 'bg-[#34C759] dark:bg-[#30D158]'
                              }`}
                            />
                            <span className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7] truncate">
                              {m.role_label}
                            </span>
                          </div>
                          <div className="text-[10.5px] text-[#8E8E93] font-mono truncate">{m.model}</div>
                        </div>
                        <div className="text-right shrink-0 ml-2">
                          <div className="text-[11px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
                            {formatTokens(m.total_tokens)} · {m.total_calls}次
                          </div>
                          <div className="text-[10px] text-[#8E8E93]">
                            {m.active_calls > 0 ? `并发 ${m.active_calls}` : `¥${m.cost.toFixed(4)}`}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {telemetry.estimated_plan_tokens > 0 && (
                  <div className="mt-2.5 pt-2 border-t border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between text-[11px] text-[#8E8E93] tabular-nums">
                    <span>计划预估</span>
                    <span>
                      ~{formatTokens(telemetry.estimated_plan_tokens)} · ~
                      {formatCost(telemetry.estimated_plan_cost ?? 0)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {!readOnly && isBusy && onCancelTask && (
            <button
              onClick={onCancelTask}
              title="停止当前任务"
              className="w-6 h-6 rounded-full macos-btn-secondary text-[#FF3B30] dark:text-[#FF453A] flex items-center justify-center transition-all active:scale-95"
            >
              <Square className="w-2.5 h-2.5 fill-current" />
            </button>
          )}
        </div>
      )}

      {/* Right: Export + Appearance + Settings */}
      <div className="sm:flex-1 flex items-center justify-end gap-1.5 shrink-0">
        {!readOnly && project && canExportHtml && (
          <button
            type="button"
            disabled={exportingHtml}
            onClick={onExportHtml}
            title="导出可交互静态 HTML 报告"
            className="h-[27px] px-2.5 rounded-[6px] macos-btn-secondary text-[11.5px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7] flex items-center gap-1.5 transition-all active:scale-[0.98] disabled:opacity-60"
          >
            {exportingHtml ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
                <span>导出中…</span>
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5 text-[#007AFF] dark:text-[#409CFF]" />
                <span>导出报告</span>
              </>
            )}
          </button>
        )}

        <button
          onClick={onToggleTheme}
          title={resolvedTheme === 'dark' ? '切换浅色外观' : '切换深色外观'}
          className="w-7 h-7 rounded-[6px] text-[#515154] dark:text-[#AEAEB2] hover:bg-black/[0.06] dark:hover:bg-white/[0.08] active:scale-[0.96] flex items-center justify-center transition-all"
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="w-[15px] h-[15px]" />
          ) : (
            <Moon className="w-[15px] h-[15px]" />
          )}
        </button>

        {!readOnly && (
          <button
            onClick={onOpenSettings}
            title="设置 (⌘,)"
            className="w-7 h-7 rounded-[6px] text-[#515154] dark:text-[#AEAEB2] hover:bg-black/[0.06] dark:hover:bg-white/[0.08] active:scale-[0.96] flex items-center justify-center transition-all"
          >
            <SlidersHorizontal className="w-[15px] h-[15px]" />
          </button>
        )}
      </div>
    </header>
  );
};
