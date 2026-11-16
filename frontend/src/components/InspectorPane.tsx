import React from 'react';
import { LiveRunView } from './LiveRunView';
import { ReportView } from './ReportView';
import { EvidenceView } from './EvidenceView';
import type {
  ChecklistItem,
  DeterministicFinding,
  InspectionReport,
  OutlineSectionLite,
} from '../types';

export type InspectorTab = 'live' | 'report' | 'evidence';

interface InspectorPaneProps {
  projectId: string;
  activeTab: InspectorTab;
  onChangeTab: (t: InspectorTab) => void;
  checklist: ChecklistItem[];
  report: InspectionReport | null;
  deterministicFindings: DeterministicFinding[];
  outline: OutlineSectionLite[];
  isRunning: boolean;
  selectedItem: ChecklistItem | null;
  selectedSectionId: string | null;
  onToggleItem: (itemId: string, enabled: boolean) => void;
  onInspectEvidence: (item: ChecklistItem | null, sectionId?: string) => void;
  onSelectSectionId: (secId: string) => void;
  readOnly?: boolean;
  fullWidth?: boolean;
}

export const InspectorPane: React.FC<InspectorPaneProps> = ({
  projectId,
  activeTab,
  onChangeTab,
  checklist,
  report,
  deterministicFindings,
  outline,
  isRunning,
  selectedItem,
  selectedSectionId,
  onToggleItem,
  onInspectEvidence,
  onSelectSectionId,
  readOnly = false,
  fullWidth = false,
}) => {
  const tabs: { key: InspectorTab; label: string; badge?: number }[] = [
    { key: 'live', label: '实况', badge: checklist.length || undefined },
    {
      key: 'report',
      label: '报告',
      badge: report ? report.partial_count + report.missing_count : undefined,
    },
    { key: 'evidence', label: '原文' },
  ];

  return (
    <aside
      className={
        fullWidth
          ? 'flex-1 min-w-0 bg-[#F6F6F8] dark:bg-[#18181B] flex flex-col h-full'
          : 'w-[45%] max-w-[660px] min-w-[320px] bg-[#F6F6F8] dark:bg-[#18181B] flex flex-col h-full'
      }
    >
      {/* macOS Segmented Control Header */}
      <div className="h-[52px] px-3.5 border-b border-black/[0.065] dark:border-white/[0.075] flex items-center justify-center bg-white/60 dark:bg-[#1E1E22]/60 backdrop-blur-md shrink-0">
        <div className="w-full max-w-[300px] macos-segmented p-[2px] rounded-[8px] grid grid-cols-3 gap-0.5">
          {tabs.map((t) => {
            const active = activeTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => onChangeTab(t.key)}
                className={`h-[25px] rounded-[6px] text-[12px] font-medium flex items-center justify-center gap-1.5 transition-all tabular-nums ${
                  active
                    ? 'macos-segmented-active text-[#1D1D1F] dark:text-[#F5F5F7]'
                    : 'text-[#6E6E73] dark:text-[#98989D] hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]'
                }`}
              >
                <span>{t.label}</span>
                {t.badge !== undefined && t.badge > 0 && (
                  <span
                    className={`px-1.5 py-[0.5px] rounded-full text-[10px] font-semibold ${
                      t.key === 'report'
                        ? 'bg-[#FF9500]/15 dark:bg-[#FF9F0A]/20 text-[#B45309] dark:text-[#FFB340]'
                        : 'bg-black/[0.06] dark:bg-white/[0.1] text-[#515154] dark:text-[#AEAEB2]'
                    }`}
                  >
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === 'live' && (
        <LiveRunView
          checklist={checklist}
          deterministicFindings={deterministicFindings}
          isRunning={isRunning}
          readOnly={readOnly}
          onToggleItem={onToggleItem}
          onInspectEvidence={onInspectEvidence}
        />
      )}

      {activeTab === 'report' && (
        <ReportView
          report={report}
          checklist={checklist}
          onInspectEvidence={onInspectEvidence}
        />
      )}

      {activeTab === 'evidence' && (
        <EvidenceView
          projectId={projectId}
          selectedItem={selectedItem}
          selectedSectionId={selectedSectionId}
          outline={outline}
          onSelectSectionId={onSelectSectionId}
        />
      )}
    </aside>
  );
};
