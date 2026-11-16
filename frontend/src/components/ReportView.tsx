import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';
import type { ChecklistItem, InspectionReport } from '../types';

interface ReportViewProps {
  report: InspectionReport | null;
  checklist: ChecklistItem[];
  onInspectEvidence: (item: ChecklistItem | null, sectionId?: string) => void;
}

type FilterMode = 'all' | 'issues' | 'fatal' | 'deterministic';

export const ReportView: React.FC<ReportViewProps> = ({
  report,
  checklist,
  onInspectEvidence,
}) => {
  const [filter, setFilter] = useState<FilterMode>('issues');

  if (!report) {
    return (
      <div className="h-full flex items-center justify-center text-[12px] text-[#8E8E93]">
        待生成报告
      </div>
    );
  }

  const enabledItems = checklist.filter((i) => i.enabled);
  const filteredItems = enabledItems.filter((it) => {
    if (filter === 'issues') {
      return it.compliance_status === 'partial' || it.compliance_status === 'missing';
    }
    if (filter === 'fatal') return it.risk_level === 'fatal';
    return true;
  });

  const verdictStyle =
    report.overall_verdict === 'ready'
      ? 'bg-[#34C759]/12 dark:bg-[#30D158]/18 border-[#34C759]/25 dark:border-[#30D158]/30 text-[#15803D] dark:text-[#30D158]'
      : report.overall_verdict === 'needs_fix'
        ? 'bg-[#FF9500]/12 dark:bg-[#FF9F0A]/18 border-[#FF9500]/25 dark:border-[#FF9F0A]/30 text-[#B45309] dark:text-[#FFB340]'
        : 'bg-[#FF3B30]/12 dark:bg-[#FF453A]/18 border-[#FF3B30]/25 dark:border-[#FF453A]/30 text-[#DC2626] dark:text-[#FF6961]';

  return (
    <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
      {/* Executive Verdict Card */}
      <div className="rounded-[12px] macos-card p-3.5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className={`px-2.5 py-1 rounded-[7px] border text-[12px] font-semibold ${verdictStyle}`}>
            {report.verdict_label}
          </div>
          <div className="text-right tabular-nums">
            <span className="text-[22px] font-bold tracking-tight text-[#1D1D1F] dark:text-[#F5F5F7]">
              {report.readiness_score}
            </span>
            <span className="text-[11px] text-[#8E8E93]"> / 100</span>
          </div>
        </div>

        {/* 4 Compact KPI Tiles */}
        <div className="grid grid-cols-4 gap-2 tabular-nums">
          <div className="rounded-[8px] macos-well px-2.5 py-2">
            <div className="text-[10.5px] text-[#8E8E93]">通过</div>
            <div className="text-[16px] font-semibold text-[#34C759] dark:text-[#30D158] mt-0.5">
              {report.passed_count}
            </div>
          </div>
          <div className="rounded-[8px] macos-well px-2.5 py-2">
            <div className="text-[10.5px] text-[#8E8E93]">待补充</div>
            <div className="text-[16px] font-semibold text-[#FF9500] dark:text-[#FF9F0A] mt-0.5">
              {report.partial_count}
            </div>
          </div>
          <div className="rounded-[8px] macos-well px-2.5 py-2">
            <div className="text-[10.5px] text-[#8E8E93]">未响应</div>
            <div className="text-[16px] font-semibold text-[#FF3B30] dark:text-[#FF453A] mt-0.5">
              {report.missing_count}
            </div>
          </div>
          <div className="rounded-[8px] macos-well px-2.5 py-2">
            <div className="text-[10.5px] text-[#8E8E93]">红线</div>
            <div className="text-[16px] font-semibold text-[#FF3B30] dark:text-[#FF453A] mt-0.5">
              {report.fatal_issue_count}
            </div>
          </div>
        </div>

        <p className="text-[12.5px] text-[#3A3A3C] dark:text-[#D1D1D6] leading-relaxed selectable-text">
          {report.executive_summary}
        </p>

        {report.priority_actions.length > 0 && (
          <div className="pt-2.5 border-t border-black/[0.06] dark:border-white/[0.07] space-y-1">
            <div className="text-[11px] font-semibold text-[#8E8E93]">优先整改</div>
            {report.priority_actions.slice(0, 4).map((act, idx) => (
              <div
                key={idx}
                className="text-[12px] text-[#1D1D1F] dark:text-[#EAEAEF] flex items-start gap-1.5 selectable-text"
              >
                <span className="text-[#007AFF] dark:text-[#409CFF] font-semibold tabular-nums">
                  {idx + 1}.
                </span>
                <span>{act}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Filter Pills */}
      <div className="flex items-center gap-1.5">
        {(
          [
            ['issues', `问题 ${report.partial_count + report.missing_count}`],
            ['all', `全部 ${report.total_items}`],
            ['fatal', '红线'],
            ['deterministic', `形式 ${report.deterministic_findings.length}`],
          ] as [FilterMode, string][]
        ).map(([mode, label]) => (
          <button
            key={mode}
            onClick={() => setFilter(mode)}
            className={`px-2.5 py-1 rounded-full text-[11.5px] font-medium transition-all tabular-nums ${
              filter === mode
                ? 'bg-[#1D1D1F] dark:bg-[#F5F5F7] text-white dark:text-[#1D1D1F] shadow-xs'
                : 'bg-black/[0.05] dark:bg-white/[0.07] text-[#6E6E73] dark:text-[#98989D] hover:bg-black/[0.09] dark:hover:bg-white/[0.12]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Deterministic Findings List or Clause Findings List */}
      {filter === 'deterministic' ? (
        <div className="rounded-[10px] macos-card divide-y divide-black/[0.05] dark:divide-white/[0.06]">
          {report.deterministic_findings.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#8E8E93]">无形式预警</div>
          ) : (
            report.deterministic_findings.map((df) => (
              <div
                key={df.finding_id}
                onClick={() => onInspectEvidence(null, df.section_id)}
                className="p-3 hover:bg-black/[0.022] dark:hover:bg-white/[0.03] cursor-pointer flex items-start justify-between gap-2.5 transition-colors"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <ShieldAlert
                      className={`w-3.5 h-3.5 shrink-0 ${
                        df.severity === 'fatal'
                          ? 'text-[#FF3B30] dark:text-[#FF453A]'
                          : 'text-[#FF9500] dark:text-[#FF9F0A]'
                      }`}
                    />
                    <span className="text-[12.5px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
                      {df.title}
                    </span>
                  </div>
                  <div className="text-[11.5px] text-[#6E6E73] dark:text-[#98989D] selectable-text">
                    {df.detail}
                  </div>
                  <div className="text-[11px] text-[#8E8E93] truncate">{df.breadcrumb}</div>
                </div>
                <span className="text-[10.5px] text-[#8E8E93] macos-well px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
                  {df.page_hint}
                </span>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="rounded-[10px] macos-card divide-y divide-black/[0.05] dark:divide-white/[0.06]">
          {filteredItems.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#8E8E93]">无匹配项</div>
          ) : (
            filteredItems.map((it) => (
              <div
                key={it.item_id}
                onClick={() => onInspectEvidence(it, it.matched_sections[0]?.section_id)}
                className="p-3 hover:bg-black/[0.022] dark:hover:bg-white/[0.03] cursor-pointer transition-colors space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {it.compliance_status === 'passed' ? (
                      <CheckCircle2 className="w-[15px] h-[15px] text-[#34C759] dark:text-[#30D158] shrink-0" />
                    ) : it.compliance_status === 'partial' ? (
                      <AlertTriangle className="w-[15px] h-[15px] text-[#FF9500] dark:text-[#FF9F0A] shrink-0" />
                    ) : (
                      <XCircle className="w-[15px] h-[15px] text-[#FF3B30] dark:text-[#FF453A] shrink-0" />
                    )}
                    <span className="text-[12.5px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] truncate">
                      {it.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {it.matched_sections[0] && (
                      <span className="text-[10.5px] text-[#6E6E73] dark:text-[#98989D] macos-well px-1.5 py-0.5 rounded-[4px] tabular-nums">
                        {it.matched_sections[0].page_label}
                      </span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-[#C7C7CC] dark:text-[#48484A]" />
                  </div>
                </div>

                <div className="text-[12px] text-[#3A3A3C] dark:text-[#D1D1D6] leading-snug selectable-text">
                  {it.conclusion || it.requirement_text}
                </div>

                {it.remediation && it.compliance_status !== 'passed' && (
                  <div className="text-[11.5px] text-[#B45309] dark:text-[#FFB340] bg-[#FF9500]/[0.08] dark:bg-[#FF9F0A]/[0.12] border border-[#FF9500]/15 dark:border-[#FF9F0A]/20 px-2.5 py-1.5 rounded-[6px] selectable-text">
                    {it.remediation}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
