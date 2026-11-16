import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';
import {
  CATEGORY_LABELS,
  type ChecklistItem,
  type InspectionReport,
} from '../types';

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
      <div className="h-full flex items-center justify-center text-[12.5px] text-[#8E8E93]">
        检查完成后自动在此生成结构化报告
      </div>
    );
  }

  const enabledItems = checklist.filter((i) => i.enabled);
  const filteredItems = enabledItems.filter((it) => {
    if (filter === 'issues') return it.compliance_status === 'partial' || it.compliance_status === 'missing';
    if (filter === 'fatal') return it.risk_level === 'fatal';
    return true;
  });

  const verdictStyle =
    report.overall_verdict === 'ready'
      ? 'bg-[#34C759]/10 border-[#34C759]/25 text-[#15803D]'
      : report.overall_verdict === 'needs_fix'
        ? 'bg-[#FF9500]/10 border-[#FF9500]/25 text-[#B45309]'
        : 'bg-[#FF3B30]/10 border-[#FF3B30]/25 text-[#DC2626]';

  return (
    <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
      {/* Executive Verdict Card */}
      <div className="rounded-[12px] bg-white border border-black/[0.07] p-3.5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className={`px-2.5 py-1 rounded-[7px] border text-[12px] font-semibold ${verdictStyle}`}>
            {report.verdict_label}
          </div>
          <div className="text-right tabular-nums">
            <span className="text-[22px] font-bold text-[#1D1D1F]">{report.readiness_score}</span>
            <span className="text-[11px] text-[#8E8E93]"> / 100</span>
          </div>
        </div>

        {/* 4 Compact KPI Tiles */}
        <div className="grid grid-cols-4 gap-2 tabular-nums">
          <div className="rounded-[8px] bg-[#F5F5F7] px-2.5 py-2">
            <div className="text-[10.5px] text-[#6E6E73]">已响应</div>
            <div className="text-[16px] font-semibold text-[#34C759] mt-0.5">{report.passed_count}</div>
          </div>
          <div className="rounded-[8px] bg-[#F5F5F7] px-2.5 py-2">
            <div className="text-[10.5px] text-[#6E6E73]">待补充</div>
            <div className="text-[16px] font-semibold text-[#FF9500] mt-0.5">{report.partial_count}</div>
          </div>
          <div className="rounded-[8px] bg-[#F5F5F7] px-2.5 py-2">
            <div className="text-[10.5px] text-[#6E6E73]">未响应</div>
            <div className="text-[16px] font-semibold text-[#FF3B30] mt-0.5">{report.missing_count}</div>
          </div>
          <div className="rounded-[8px] bg-[#F5F5F7] px-2.5 py-2">
            <div className="text-[10.5px] text-[#6E6E73]">废标红线</div>
            <div className="text-[16px] font-semibold text-[#FF3B30] mt-0.5">{report.fatal_issue_count}</div>
          </div>
        </div>

        <p className="text-[12.5px] text-[#3A3A3C] leading-relaxed selectable-text">
          {report.executive_summary}
        </p>

        {report.priority_actions.length > 0 && (
          <div className="pt-2 border-t border-black/[0.06] space-y-1">
            <div className="text-[11px] font-semibold text-[#6E6E73]">封标前优先整改</div>
            {report.priority_actions.slice(0, 4).map((act, idx) => (
              <div key={idx} className="text-[12px] text-[#1D1D1F] flex items-start gap-1.5 selectable-text">
                <span className="text-[#007AFF] font-semibold tabular-nums">{idx + 1}.</span>
                <span>{act}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-1.5">
        {(
          [
            ['issues', `问题项 (${report.partial_count + report.missing_count})`],
            ['all', `全部条款 (${report.total_items})`],
            ['fatal', '废标红线条款'],
            ['deterministic', `形式预警 (${report.deterministic_findings.length})`],
          ] as [FilterMode, string][]
        ).map(([mode, label]) => (
          <button
            key={mode}
            onClick={() => setFilter(mode)}
            className={`px-2.5 py-1 rounded-full text-[11.5px] font-medium transition-colors tabular-nums ${
              filter === mode
                ? 'bg-[#1D1D1F] text-white'
                : 'bg-black/[0.05] text-[#515154] hover:bg-black/[0.09]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Deterministic Findings List or Clause Findings List */}
      {filter === 'deterministic' ? (
        <div className="rounded-[10px] bg-white border border-black/[0.07] divide-y divide-black/[0.05]">
          {report.deterministic_findings.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#8E8E93]">无形式预警</div>
          ) : (
            report.deterministic_findings.map((df) => (
              <div
                key={df.finding_id}
                onClick={() => onInspectEvidence(null, df.section_id)}
                className="p-3 hover:bg-black/[0.02] cursor-pointer flex items-start justify-between gap-2.5"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <ShieldAlert
                      className={`w-3.5 h-3.5 shrink-0 ${
                        df.severity === 'fatal' ? 'text-[#FF3B30]' : 'text-[#FF9500]'
                      }`}
                    />
                    <span className="text-[12.5px] font-medium text-[#1D1D1F]">{df.title}</span>
                  </div>
                  <div className="text-[11.5px] text-[#6E6E73] selectable-text">{df.detail}</div>
                  <div className="text-[11px] text-[#8E8E93] truncate">{df.breadcrumb}</div>
                </div>
                <span className="text-[10.5px] text-[#6E6E73] bg-[#F5F5F7] px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
                  {df.page_hint}
                </span>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="rounded-[10px] bg-white border border-black/[0.07] divide-y divide-black/[0.05]">
          {filteredItems.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#8E8E93]">当前筛选条件下无条目</div>
          ) : (
            filteredItems.map((it) => (
              <div
                key={it.item_id}
                onClick={() => onInspectEvidence(it, it.matched_sections[0]?.section_id)}
                className="p-3 hover:bg-black/[0.02] cursor-pointer transition-colors space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {it.compliance_status === 'passed' ? (
                      <CheckCircle2 className="w-4 h-4 text-[#34C759] shrink-0" />
                    ) : it.compliance_status === 'partial' ? (
                      <AlertTriangle className="w-4 h-4 text-[#FF9500] shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-[#FF3B30] shrink-0" />
                    )}
                    <span className="text-[12.5px] font-semibold text-[#1D1D1F] truncate">
                      {it.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10.5px] text-[#8E8E93]">
                      {CATEGORY_LABELS[it.category]}
                    </span>
                    {it.matched_sections[0] && (
                      <span className="text-[10.5px] text-[#515154] bg-[#F5F5F7] px-1.5 py-0.5 rounded-[4px] tabular-nums">
                        {it.matched_sections[0].page_label}
                      </span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-[#C7C7CC]" />
                  </div>
                </div>

                <div className="text-[12px] text-[#3A3A3C] leading-snug selectable-text">
                  {it.conclusion || it.requirement_text}
                </div>

                {it.remediation && it.compliance_status !== 'passed' && (
                  <div className="text-[11.5px] text-[#D97706] bg-[#FFFBEB] px-2.5 py-1.5 rounded-[6px] selectable-text">
                    建议：{it.remediation}
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
