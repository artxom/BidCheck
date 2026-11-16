import React from 'react';
import { Plus, Trash2, FolderCheck, HardDrive } from 'lucide-react';
import type { ProjectListItem } from '../types';

interface SidebarProps {
  projects: ProjectListItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  cacheMb: number;
  onClearCache: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  projects,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  cacheMb,
  onClearCache,
}) => {
  return (
    <aside className="w-[224px] shrink-0 bg-[#ECECEF]/90 backdrop-blur-xl border-r border-black/[0.08] flex flex-col h-full">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-wide text-[#8E8E93] uppercase">
          核查项目
        </span>
        <button
          onClick={onCreate}
          title="新建项目"
          className="p-1 rounded-[5px] text-[#515154] hover:bg-black/[0.07] active:bg-black/[0.12] transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {projects.map((p) => {
          const isActive = p.id === activeId;
          const dot =
            p.stage === 'completed'
              ? 'bg-[#34C759]'
              : p.stage === 'inspecting' || p.stage === 'planning'
                ? 'bg-[#007AFF]'
                : p.stage === 'awaiting_confirm'
                  ? 'bg-[#FF9500]'
                  : 'bg-[#C7C7CC]';

          return (
            <div
              key={p.id}
              onClick={() => onSelect(p.id)}
              className={`group flex items-center justify-between px-2.5 py-2 rounded-[7px] cursor-pointer transition-colors ${
                isActive
                  ? 'bg-[#007AFF] text-white shadow-[0_1px_2px_rgba(0,122,255,0.25)]'
                  : 'text-[#1D1D1F] hover:bg-black/[0.05]'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <FolderCheck
                  className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-white/90' : 'text-[#007AFF]'}`}
                />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate leading-tight">{p.name}</div>
                  <div
                    className={`text-[10.5px] flex items-center gap-1.5 mt-0.5 tabular-nums ${
                      isActive ? 'text-white/75' : 'text-[#8E8E93]'
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white' : dot}`} />
                    <span>{p.target_lot ? `${p.target_lot}标段` : '未定标段'}</span>
                    {p.progress_pct > 0 && <span>· {p.progress_pct.toFixed(0)}%</span>}
                  </div>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(p.id);
                }}
                title="删除项目"
                className={`opacity-0 group-hover:opacity-100 p-1 rounded-[5px] transition-opacity ${
                  isActive
                    ? 'text-white/80 hover:bg-white/20 hover:text-white'
                    : 'text-[#8E8E93] hover:bg-black/[0.08] hover:text-[#FF3B30]'
                }`}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="px-3 py-2.5 border-t border-black/[0.06] flex items-center justify-between text-[11px] text-[#8E8E93] tabular-nums">
        <span className="flex items-center gap-1.5">
          <HardDrive className="w-3 h-3" />
          <span>缓存 {cacheMb.toFixed(1)} MB</span>
        </span>
        {cacheMb > 0.1 && (
          <button
            onClick={onClearCache}
            className="text-[#007AFF] hover:underline font-medium"
          >
            清理
          </button>
        )}
      </div>
    </aside>
  );
};
