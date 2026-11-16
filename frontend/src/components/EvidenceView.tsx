import React, { useState, useEffect } from 'react';
import { Loader2, Image as ImageIcon, X, FileSearch } from 'lucide-react';
import { api } from '../api';
import type { ChecklistItem, OutlineSectionLite, SectionDetail } from '../types';

interface EvidenceViewProps {
  projectId: string;
  selectedItem: ChecklistItem | null;
  selectedSectionId: string | null;
  outline: OutlineSectionLite[];
  onSelectSectionId: (secId: string) => void;
}

export const EvidenceView: React.FC<EvidenceViewProps> = ({
  projectId,
  selectedItem,
  selectedSectionId,
  outline,
  onSelectSectionId,
}) => {
  const [section, setSection] = useState<SectionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [lightboxMediaId, setLightboxMediaId] = useState<string | null>(null);

  useEffect(() => {
    const targetId =
      selectedSectionId ||
      selectedItem?.matched_sections[0]?.section_id ||
      outline[0]?.section_id ||
      null;
    if (!targetId) {
      setSection(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    api
      .getSection(projectId, targetId)
      .then((res) => {
        if (!cancelled) setSection(res.section);
      })
      .catch(() => {
        if (!cancelled) setSection(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, selectedSectionId, selectedItem, outline]);

  if (!selectedItem && outline.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-[12.5px] text-[#8E8E93]">
        点击任意检查项或挂载响应文件后预览原文与扫描件
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
      {/* Clause Requirement Summary Card */}
      {selectedItem && (
        <div className="rounded-[10px] bg-white border border-black/[0.07] p-3 space-y-1.5 selectable-text">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] font-semibold text-[#1D1D1F]">
              {selectedItem.item_id} · {selectedItem.title}
            </span>
            {selectedItem.tender_source && (
              <span className="text-[10.5px] text-[#6E6E73] bg-[#F5F5F7] px-1.5 py-0.5 rounded-[4px] shrink-0">
                {selectedItem.tender_source}
              </span>
            )}
          </div>
          <div className="text-[11.5px] text-[#515154] leading-relaxed">
            要求：{selectedItem.requirement_text}
          </div>
          {selectedItem.conclusion && (
            <div className="text-[11.5px] font-medium text-[#007AFF] pt-1 border-t border-black/[0.05]">
              结论：{selectedItem.conclusion}
            </div>
          )}

          {selectedItem.matched_sections.length > 1 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {selectedItem.matched_sections.map((ms) => (
                <button
                  key={ms.section_id}
                  onClick={() => onSelectSectionId(ms.section_id)}
                  className={`px-2 py-0.5 rounded-[5px] text-[11px] transition-colors ${
                    section?.section_id === ms.section_id
                      ? 'bg-[#007AFF] text-white'
                      : 'bg-[#F5F5F7] text-[#515154] hover:bg-black/[0.08]'
                  }`}
                >
                  {ms.page_label} · {ms.breadcrumb.split(' > ').pop()}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Outline Quick Selector */}
      {outline.length > 0 && (
        <div className="flex items-center gap-2">
          <FileSearch className="w-3.5 h-3.5 text-[#8E8E93] shrink-0" />
          <select
            value={section?.section_id || ''}
            onChange={(e) => onSelectSectionId(e.target.value)}
            className="flex-1 h-[28px] rounded-[7px] bg-white border border-black/[0.1] px-2 text-[11.5px] text-[#1D1D1F] outline-none focus:border-[#007AFF]"
          >
            {outline.map((s) => (
              <option key={s.section_id} value={s.section_id}>
                {'　'.repeat(Math.max(0, s.level - 1))}
                [{s.page_label}] {s.title}
                {s.image_count > 0 ? ` (${s.image_count}图)` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Section Content Body */}
      {loading ? (
        <div className="py-12 flex items-center justify-center text-[#8E8E93] gap-2 text-[12px]">
          <Loader2 className="w-4 h-4 animate-spin text-[#007AFF]" />
          <span>读取章节原文…</span>
        </div>
      ) : section ? (
        <div className="rounded-[10px] bg-white border border-black/[0.07] p-3.5 space-y-3 selectable-text">
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-black/[0.06]">
            <div className="text-[12px] font-semibold text-[#1D1D1F] leading-snug">
              {section.breadcrumb}
            </div>
            <span className="px-2 py-0.5 rounded-[5px] bg-[#007AFF]/10 text-[#007AFF] text-[11px] font-semibold shrink-0 tabular-nums">
              {section.page_label}
            </span>
          </div>

          {section.deterministic_findings.length > 0 && (
            <div className="space-y-1">
              {section.deterministic_findings.map((d) => (
                <div
                  key={d.finding_id}
                  className="px-2.5 py-1.5 rounded-[6px] bg-[#FFFBEB] border border-[#FDE68A] text-[11.5px] text-[#92400E]"
                >
                  {d.title}：{d.detail}
                </div>
              ))}
            </div>
          )}

          {/* Paragraphs */}
          {section.paragraphs.length > 0 && (
            <div className="space-y-1.5 text-[12.5px] text-[#2C2C2E] leading-relaxed">
              {section.paragraphs.map((p, idx) => (
                <p key={idx}>{p}</p>
              ))}
            </div>
          )}

          {/* Tables */}
          {section.tables.map((tbl) => (
            <div key={tbl.table_id} className="overflow-x-auto border border-black/[0.08] rounded-[7px]">
              <table className="w-full text-[11.5px] border-collapse">
                <tbody>
                  {tbl.rows.slice(0, 35).map((row, rIdx) => (
                    <tr
                      key={rIdx}
                      className={rIdx === 0 ? 'bg-[#F5F5F7] font-semibold' : 'border-t border-black/[0.06]'}
                    >
                      {row.map((cell, cIdx) => (
                        <td
                          key={cIdx}
                          className="px-2 py-1.5 border-r last:border-r-0 border-black/[0.05] align-top"
                        >
                          {cell || <span className="text-[#FF3B30]/60 italic">空</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {/* Embedded Scanned Images Gallery */}
          {section.media_ids.length > 0 && (
            <div className="space-y-2 pt-1">
              <div className="text-[11px] font-semibold text-[#6E6E73] flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-[#007AFF]" />
                <span>内嵌扫描件 / 图片 ({section.media_ids.length})</span>
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                {section.media_ids.map((mid) => (
                  <div
                    key={mid}
                    onClick={() => setLightboxMediaId(mid)}
                    className="group rounded-[8px] border border-black/[0.08] bg-[#F5F5F7] overflow-hidden cursor-zoom-in"
                  >
                    <img
                      src={`/api/projects/${projectId}/media/${mid}`}
                      alt={mid}
                      loading="lazy"
                      className="w-full h-40 object-contain bg-white group-hover:scale-[1.02] transition-transform"
                    />
                    <div className="px-2 py-1 text-[10.5px] text-[#8E8E93] flex justify-between tabular-nums">
                      <span>{mid}</span>
                      <span>点击放大</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {section.paragraphs.length === 0 &&
            section.tables.length === 0 &&
            section.media_ids.length === 0 && (
              <div className="py-6 text-center text-[12px] text-[#8E8E93]">
                该章节下无直接正文或图片（可能为上级目录容器或空白章节）
              </div>
            )}
        </div>
      ) : null}

      {/* Fullscreen Lightbox for Certificate / Contract Scans */}
      {lightboxMediaId && (
        <div
          onClick={() => setLightboxMediaId(null)}
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        >
          <button
            onClick={() => setLightboxMediaId(null)}
            className="absolute top-5 right-5 w-9 h-9 rounded-full bg-white/15 hover:bg-white/25 text-white flex items-center justify-center"
          >
            <X className="w-5 h-5" />
          </button>
          <img
            src={`/api/projects/${projectId}/media/${lightboxMediaId}`}
            alt={lightboxMediaId}
            onClick={(e) => e.stopPropagation()}
            className="max-w-full max-h-full rounded-[10px] shadow-2xl bg-white"
          />
        </div>
      )}
    </div>
  );
};
