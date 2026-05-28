import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import CourseDetailModal from '../components/CourseDetailModal';
import type { CourseCard } from '../types';

// ══════════════════════════════════════════════════════════════════════════
// 型別
// ══════════════════════════════════════════════════════════════════════════

interface CourseEntry {
  code: string;
  name: string;
  credits: number;
  when?: string;
  mandatory?: boolean;
}

interface ElectiveGroup {
  name: string;
  select?: number;
  select_credits?: number;
  group_rule?: string;
  description?: string;
  courses?: CourseEntry[];
  option_a?: CourseEntry[];
  option_b?: CourseEntry[];
  option_c?: CourseEntry[];
  slots?: { slot_name: string; slot_rule?: string; courses: CourseEntry[] }[];
}

interface GraduationRule {
  type: string;
  category: string;
  description?: string;
  credits?: number;
  select?: number;
  books?: number;
  cert?: string;
  course_codes?: string[];
  courses?: CourseEntry[];
  options?: { name: string; credits?: number }[];
  [key: string]: unknown;
}

interface DeptNode {
  id: string;
  name: string;
  program_type: string;
  min_credits: number;
  groups?: { id: string; name: string; group_label: string }[];
  specialization_tracks?: { id: string; name: string }[];
}

interface CollegeNode {
  id: string;
  name: string;
  departments: DeptNode[];
  college_bachelor_programs: (DeptNode & { specialization_tracks?: { id: string; name: string }[] })[];
}

interface DeptDetail {
  id: string;
  name: string;
  program_type: string;
  min_credits: number;
  required_credits?: number;
  graduation_rules: GraduationRule[];
  // 各種「必修」欄位名稱（不同系所用不同 key）
  required_courses?: CourseEntry[];
  foundation_courses?: CourseEntry[];
  college_required_courses?: CourseEntry[];
  common_required_courses?: CourseEntry[];
  dept_required_courses?: CourseEntry[];
  required_electives?: CourseEntry[];
  cross_domain_required?: CourseEntry[];
  earth_system_courses?: CourseEntry[];
  cross_group_required?: CourseEntry[];
  application_courses?: CourseEntry[];
  first_domain_electives?: CourseEntry[];
  // 領域選修（可從中選修以達到選修學分要求）
  elective_courses?: CourseEntry[];
  // 選修群
  elective_groups?: ElectiveGroup[];
  core_elective_groups?: ElectiveGroup[];
  college_required_elective_groups?: ElectiveGroup[];
  science_ability_groups?: ElectiveGroup[];
  other_elective_groups?: ElectiveGroup[];
  groups?: DeptDetail[];
  graduation_notes?: string;
}

interface NotesEntry {
  key: string;
  raw_text: string;
  source?: string;
}

// ══════════════════════════════════════════════════════════════════════════
// 樹狀節點元件
// ══════════════════════════════════════════════════════════════════════════

const INDENT = 20; // px per level

function TreeNode({
  label,
  badge,
  badgeColor = 'bg-slate-100 text-slate-500',
  icon,
  depth = 0,
  defaultOpen = false,
  children,
  leaf = false,
  dimmed = false,
}: {
  label: React.ReactNode;
  badge?: string | number;
  badgeColor?: string;
  icon?: string;
  depth?: number;
  defaultOpen?: boolean;
  children?: React.ReactNode;
  leaf?: boolean;
  dimmed?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = !!children;

  return (
    <div className="mb-0.5">
      <div
        className={`flex items-center gap-2 py-1.5 pr-2 rounded-xl cursor-pointer select-none transition-all duration-200 ease-in-out border border-transparent
          ${hasChildren ? 'hover:bg-white hover:shadow-sm hover:border-slate-100' : 'hover:bg-slate-50'} ${dimmed ? 'opacity-50' : ''}`}
        style={{ paddingLeft: depth * INDENT + 8 }}
        onClick={() => hasChildren && setOpen((v) => !v)}
      >
        {/* expand icon */}
        <span className={`w-5 shrink-0 flex items-center justify-center text-[10px] text-slate-400 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>
          {!leaf && hasChildren ? '▶' : ''}
        </span>
        {icon && <span className="text-base drop-shadow-sm">{icon}</span>}
        <span className={`flex-1 text-[13px] ${dimmed ? 'text-slate-400 font-normal' : 'text-slate-700 font-medium'}`}>{label}</span>
        {badge !== undefined && badge !== '' && (
          <span className={`shrink-0 rounded-lg px-3.5 py-[5.5px] text-[10px] font-bold leading-none tracking-wide shadow-sm border border-black/5 ${badgeColor}`}>
            {badge}
          </span>
        )}
      </div>
      {open && hasChildren && <div className="mt-0.5 relative">{children}</div>}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 學期分組工具
// ══════════════════════════════════════════════════════════════════════════

const SEM_ORDER = ['大一上', '大一下', '大二上', '大二下', '大三上', '大三下', '大四上', '大四下'];

function semKey(when: string): string {
  // 範圍取起始，例如 "大一上~大二下" → "大一上"
  return (when || '').split('~')[0].trim();
}

function groupBySem(courses: CourseEntry[]): Map<string, CourseEntry[]> {
  const map = new Map<string, CourseEntry[]>();
  for (const c of courses) {
    const k = c.when ? semKey(c.when) : '未分配';
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(c);
  }
  // 排序：依 SEM_ORDER 順序
  const sorted = new Map<string, CourseEntry[]>();
  for (const sem of SEM_ORDER) {
    if (map.has(sem)) sorted.set(sem, map.get(sem)!);
  }
  if (map.has('未分配')) sorted.set('未分配', map.get('未分配')!);
  return sorted;
}

// ══════════════════════════════════════════════════════════════════════════
// 課程節點
// ══════════════════════════════════════════════════════════════════════════

function CourseLeaf({ c, depth, hideIndent = false }: { c: CourseEntry; depth: number, hideIndent?: boolean }) {
  const handleShowDetail = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.dispatchEvent(
      new CustomEvent('SHOW_COURSE_DETAIL', {
        detail: {
          id: c.code || c.name,
          code: c.code || '',
          name: c.name,
          credits: c.credits || 0,
          type: c.mandatory ? '必修' : '選修',
          teacher: '',
        },
      })
    );
  };

  return (
    <div
      onClick={handleShowDetail}
      className="flex items-center p-2.5 bg-slate-50 rounded border-l-[3px] border-teal-500 hover:bg-teal-50 transition-colors mb-3.5 cursor-pointer"
      style={!hideIndent ? { marginLeft: depth * INDENT } : {}}
    >
      <div className="flex-grow flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
        <div className="flex items-center gap-2.5">
          <h4 className="text-[13px] font-bold text-slate-700 group-hover:text-teal-700 transition-colors">{c.name}</h4>
          {c.mandatory && <span className="px-1 py-[1px] rounded text-[8px] font-bold bg-teal-100 border border-teal-200 text-teal-800">必修</span>}
          <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2.5 py-[5.5px] rounded-lg leading-none uppercase tracking-wide">{c.credits} 學分</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-slate-500">代碼: {c.code}</span>
          {c.when && <span className="bg-emerald-100 text-emerald-800 text-[9px] font-semibold px-1.5 py-0.5 rounded">{c.when}</span>}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 選修群樹
// ══════════════════════════════════════════════════════════════════════════

function ElectiveGroupTree({ g, depth }: { g: ElectiveGroup; depth: number }) {
  const [showCourses, setShowCourses] = useState(false);
  const selectLabel = g.select
    ? `選 ${g.select} 門`
    : g.select_credits
      ? `選 ${g.select_credits} 學分`
      : '';

  const allCourses = g.courses ?? [];
  const hasOptions = !!(g.option_a || g.option_b || g.option_c);
  const hasSlots = !!(g.slots && g.slots.length > 0);
  const isEmpty = allCourses.length === 0 && !hasOptions && !hasSlots;

  return (
    <div className="mb-4 bg-white/95 rounded-lg shadow-soft transition-all duration-300 hover:shadow-medium overflow-hidden" style={{ marginLeft: depth * INDENT }}>
      <div className="p-4 bg-white/95 flex flex-col md:flex-row md:items-center justify-between gap-3 leading-relaxed">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[15px] font-bold text-slate-800 tracking-tight">{g.name || '選修群組'}</span>
            {selectLabel && <span className="px-2.5 py-[5.5px] rounded-lg text-[10px] font-bold leading-none bg-teal-50 border border-teal-100 text-teal-700">{selectLabel}</span>}
          </div>
          {isEmpty && <div className="text-[11px] text-slate-400 mt-1 italic">（課程清單未收錄）</div>}
        </div>
        {allCourses.length > 0 && (
          <button
            onClick={() => setShowCourses(!showCourses)}
            className="text-[11px] px-3 py-1 bg-white/95 border border-slate-200/60 shadow-soft rounded-lg hover:bg-teal-50/60 hover:text-teal-700 font-semibold text-slate-700 transition-colors shrink-0"
          >
            {showCourses ? '隱藏課程' : `查看適用課程 (${allCourses.length})`}
          </button>
        )}
      </div>
      {showCourses && allCourses.length > 0 && (
        <div className="border-t border-slate-200/25 p-3 bg-slate-50/30">
          <SemesterGroup courses={allCourses} depth={0} hideSemesters />
        </div>
      )}
      {/* slots */}
      {hasSlots && g.slots!.map((slot, i) => (
        <div key={i} className="border-t border-slate-200/25 p-3 bg-slate-50/30">
          <div className="text-[11px] font-bold text-teal-600 mb-2 flex items-center gap-2">
            <span>{slot.slot_name || `Slot ${i + 1}`}</span>
          </div>
          <SemesterGroup courses={slot.courses} depth={0} hideSemesters />
        </div>
      ))}
      {/* options (sub groups) */}
      {hasOptions && (
        <div className="border-t border-slate-200/25 p-3 bg-slate-50/30 space-y-4">
          {g.option_a && (
            <div>
              <div className="text-[11px] font-bold text-slate-600 mb-2">▪ 選項 A</div>
              <SemesterGroup courses={g.option_a} depth={0} hideSemesters />
            </div>
          )}
          {g.option_b && (
            <div>
              <div className="text-[11px] font-bold text-slate-600 mb-2">▪ 選項 B</div>
              <SemesterGroup courses={g.option_b} depth={0} hideSemesters />
            </div>
          )}
          {g.option_c && (
            <div>
              <div className="text-[11px] font-bold text-slate-600 mb-2">▪ 選項 C</div>
              <SemesterGroup courses={g.option_c} depth={0} hideSemesters />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 畢業規定節點
// ══════════════════════════════════════════════════════════════════════════

const CATEGORY_ICON: Record<string, string> = {};

const CATEGORY_COLOR: Record<string, string> = {
  '學分規定': 'bg-blue-50 text-blue-700',
  '指定選課': 'bg-purple-50 text-purple-700',
  '先修條件': 'bg-yellow-50 text-yellow-700',
  '外部認證': 'bg-green-50 text-green-700',
  '特殊規定': 'bg-orange-50 text-orange-700',
  '其他規定': 'bg-gray-50 text-gray-600',
};

function RuleTree({ rule, depth }: { rule: GraduationRule; depth: number }) {
  const hasCourses =
    (rule.course_codes && rule.course_codes.length > 0) ||
    (rule.courses && rule.courses.length > 0);
  const hasOptions = !!(rule.options && rule.options.length > 0);
  const isLeaf = !hasCourses && !hasOptions;

  const isEnglishKey = /^[a-zA-Z_]+$/.test(rule.type);
  const label = (
    <span className="flex items-center gap-2">
      {!isEnglishKey && rule.type && (
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold shadow-sm border border-slate-100 ${CATEGORY_COLOR[rule.category] ?? 'bg-slate-50 text-slate-500'}`}>
          {rule.type}
        </span>
      )}
      <span className="text-slate-700 font-medium">
        {rule.description ?? (rule.cert ? `認證：${rule.cert}` : '')}
      </span>
    </span>
  );

  const creditBadge = rule.credits !== undefined
    ? `${rule.credits} 學分`
    : rule.select !== undefined
      ? `選${rule.select}門`
      : undefined;

  if (isLeaf) {
    return (
      <div className="flex items-start gap-2 py-1.5 pr-2 rounded-xl hover:bg-slate-50 transition-colors duration-200"
        style={{ paddingLeft: depth * INDENT + 8 }}>
        <span className="w-5 shrink-0 text-center text-[10px] text-slate-300 flex items-center justify-center mt-1">•</span>
        <span className="flex-1 text-[13px]">{label}</span>
        {creditBadge && (
          <span className="shrink-0 rounded-lg bg-slate-100 px-3.5 py-[5.5px] text-[10px] font-bold leading-none text-slate-500 shadow-sm border border-slate-200/60">
            {creditBadge}
          </span>
        )}
      </div>
    );
  }

  return (
    <TreeNode label={label} badge={creditBadge} depth={depth} defaultOpen={false} icon="•">
      {rule.course_codes?.map((code) => (
        <div key={code} style={{ paddingLeft: (depth + 1) * INDENT + 4 }}
          className="py-0.5 font-mono text-xs text-gray-500 hover:bg-gray-50 rounded">
          <span className="w-4 inline-block" /> {code}
        </div>
      ))}
      {rule.courses?.map((c) => (
        <CourseLeaf key={c.code} c={c} depth={depth + 1} />
      ))}
      {rule.options?.map((opt, i) => (
        <div key={i} style={{ paddingLeft: (depth + 1) * INDENT + 4 }}
          className="py-0.5 text-sm text-gray-600 hover:bg-gray-50 rounded">
          <span className="w-4 inline-block" /> {opt.name}
          {opt.credits && <span className="ml-1 text-xs text-gray-400">{opt.credits}cr</span>}
        </div>
      ))}
    </TreeNode>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 系所詳情樹（核心元件）
// ══════════════════════════════════════════════════════════════════════════

const CATEGORIES_ORDER = ['學分規定', '指定選課', '外部認證', '先修條件', '特殊規定', '其他規定'];

// 所有可能的「必修課程」欄位，順序即顯示順序（elective_courses 獨立處理）
const REQUIRED_COURSE_FIELDS: Array<{ key: keyof DeptDetail; label: string }> = [
  { key: 'required_courses', label: '必修課程' },
  { key: 'foundation_courses', label: '基礎必修' },
  { key: 'college_required_courses', label: '院訂必修' },
  { key: 'common_required_courses', label: '共同必修' },
  { key: 'dept_required_courses', label: '系訂必修' },
  { key: 'required_electives', label: '必選修' },
  { key: 'cross_domain_required', label: '跨域必修' },
  { key: 'earth_system_courses', label: '地球系統科學' },
  { key: 'cross_group_required', label: '跨組必修' },
  { key: 'application_courses', label: '應用課程' },
  { key: 'first_domain_electives', label: '第一領域選修' },
];

function SemesterGroup({
  courses,
  depth,
  hideSemesters = false,
}: {
  courses: CourseEntry[];
  depth: number;
  hideSemesters?: boolean;
}) {
  if (hideSemesters) {
    return (
      <div style={{ marginLeft: depth * INDENT }}>
        <div className="bg-white rounded-xl overflow-hidden shadow-soft">
          {courses.map((c) => <CourseLeaf key={c.code} c={c} depth={0} hideIndent />)}
        </div>
      </div>
    );
  }

  const semMap = groupBySem(courses);
  return (
    <div className="space-y-7">
      {Array.from(semMap.entries()).map(([sem, cs]) => (
        <div key={sem} style={{ marginLeft: depth * INDENT }}>
          <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2 leading-6">
            <span>{sem}</span>
          </div>
          <div className="bg-white rounded-xl overflow-hidden shadow-soft">
            {cs.map((c) => <CourseLeaf key={c.code} c={c} depth={0} hideIndent />)}
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionCard({ children, hasProgress, current, max }: { children: React.ReactNode, hasProgress?: boolean, current?: number, max?: number }) {
  return (
    <div className="bg-white/95 rounded-xl shadow-soft px-8 py-8 mb-8 transition-shadow duration-300 hover:shadow-medium relative overflow-hidden group">
      {hasProgress && max && max > 0 && current !== undefined && (
        <div className="absolute top-0 left-0 w-full h-1 bg-slate-100">
          <div className="h-full bg-gradient-to-r from-indigo-500 to-blue-500 rounded-r-full transition-all duration-1000 ease-out" style={{ width: `${Math.min((current / max) * 100, 100)}%` }}></div>
        </div>
      )}
      {children}
    </div>
  );
}

function getDefaultTab(detail: DeptDetail): 'required' | 'elective' | 'rules' {
  const hasRequired = REQUIRED_COURSE_FIELDS.some(({ key }) => {
    const courses = detail[key] as CourseEntry[] | undefined;
    return Array.isArray(courses) && courses.length > 0;
  });

  const hasElective =
    (detail.elective_courses?.length ?? 0) > 0 ||
    (detail.elective_groups?.length ?? 0) > 0 ||
    (detail.core_elective_groups?.length ?? 0) > 0 ||
    (detail.college_required_elective_groups?.length ?? 0) > 0 ||
    (detail.science_ability_groups?.length ?? 0) > 0 ||
    (detail.other_elective_groups?.length ?? 0) > 0;

  if (!hasRequired && hasElective) return 'elective';
  return 'required';
}

function DeptTree({
  detail,
  depth = 0,
  defaultTab,
  showNotes,
  setShowNotes,
}: {
  detail: DeptDetail;
  depth?: number;
  defaultTab?: 'required' | 'elective' | 'rules';
  showNotes?: boolean;
  setShowNotes?: React.Dispatch<React.SetStateAction<boolean>>;
}) {
  const [activeTab, setActiveTab] = useState<'required' | 'elective' | 'rules'>(defaultTab ?? getDefaultTab(detail));

  // 收集所有有課程的必修區塊
  const reqSections = REQUIRED_COURSE_FIELDS
    .map(({ key, label }) => ({
      label,
      courses: (detail[key] as CourseEntry[] | undefined) ?? [],
    }))
    .filter(({ courses }) => courses.length > 0);

  const rulesByCategory: Record<string, GraduationRule[]> = {};
  for (const cat of CATEGORIES_ORDER) rulesByCategory[cat] = [];
  for (const rule of detail.graduation_rules ?? []) {
    const cat = rule.category ?? '其他規定';
    if (!rulesByCategory[cat]) rulesByCategory[cat] = [];
    rulesByCategory[cat].push(rule);
  }
  const totalRules = (detail.graduation_rules ?? []).length;

  return (
    <div className="font-sans pb-10 leading-relaxed">
      {/* ── Tabs 標籤列與切換按鈕 ── */}
      <div className="flex items-center justify-between border-b border-slate-200/80 mt-2 px-1 mb-6">
        <div className="flex items-center gap-1">
          <button onClick={() => setActiveTab('required')} className={`px-5 py-3 text-[13px] font-extrabold border-b-[3px] transition-colors duration-200 ${activeTab === 'required' ? 'border-teal-600 text-teal-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
            核心必修
          </button>
          <button onClick={() => setActiveTab('elective')} className={`px-5 py-3 text-[13px] font-extrabold border-b-[3px] transition-colors duration-200 ${activeTab === 'elective' ? 'border-teal-600 text-teal-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
            領域與分組選修
          </button>
          <button onClick={() => setActiveTab('rules')} className={`px-5 py-3 text-[13px] font-extrabold border-b-[3px] transition-colors duration-200 ${activeTab === 'rules' ? 'border-emerald-600 text-emerald-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
            畢業規定與其他
          </button>
        </div>

        {depth === 0 && showNotes !== undefined && setShowNotes !== undefined && (
          <div className="pb-1.5">
            <button
              onClick={() => setShowNotes((v) => !v)}
              className={`flex items-center gap-1.5 rounded-xl border px-4 py-2 text-xs font-bold transition-all duration-200 shadow-sm ${
                showNotes
                  ? 'bg-amber-50/50 border-amber-200 text-amber-700 hover:bg-amber-100/70 shadow-amber-100/20'
                  : 'bg-transparent border-slate-200 text-slate-600 hover:bg-slate-50/80 hover:text-amber-600 hover:border-amber-200'
              }`}
            >
              <span>{showNotes ? '▶' : '◀'}</span>
              {showNotes ? '隱藏參考文字' : '顯示參考文字'}
            </button>
          </div>
        )}
      </div>

      {activeTab === 'required' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* ── 必修課程（所有欄位彙整）────────────── */}
          {reqSections.length > 0 ? (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">必修課程</span>}
                depth={depth}
                defaultOpen={true}
              >
                <div className="space-y-4 mt-2">
                  {reqSections.length === 1 ? (
                    /* 只有一種欄位：直接展開學期 */
                    <SemesterGroup courses={reqSections[0].courses} depth={depth + 1} />
                  ) : (
                    /* 多種欄位：先顯示欄位標籤，再展學期 */
                    reqSections.map(({ label, courses }) => {
                      return (
                        <div key={label} style={{ marginLeft: (depth + 1) * INDENT }}>
                          <div className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                            <span>▪ {label}</span>
                          </div>
                          <SemesterGroup courses={courses} depth={depth + 2} />
                        </div>
                      );
                    })
                  )}
                </div>
              </TreeNode>
            </SectionCard>
          ) : (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無必修課程資料</div>
          )}
        </div>
      )}

      {activeTab === 'elective' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 space-y-6">
          {/* ── 核心必選群 ───────────────────────────── */}
          {detail.core_elective_groups && detail.core_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">核心必選群</span>}
                badge={detail.core_elective_groups.length}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.core_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 院訂必選群 ───────────────────────────── */}
          {detail.college_required_elective_groups && detail.college_required_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">院訂必選群</span>}
                badge={detail.college_required_elective_groups.length}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.college_required_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 科學能力群 ───────────────────────────── */}
          {detail.science_ability_groups && detail.science_ability_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">科學能力必選</span>}
                badge={detail.science_ability_groups.length}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.science_ability_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 選修群 ───────────────────────────────── */}
          {detail.elective_groups && detail.elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">選修群</span>}
                badge={detail.elective_groups.length}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 領域選修課程 ── */}
          {detail.elective_courses && detail.elective_courses.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">領域選修課程</span>}
                badge={`${detail.elective_courses.length}門可選`}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  <SemesterGroup courses={detail.elective_courses} depth={depth + 1} hideSemesters />
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 其他選修群 ───────────────────────────── */}
          {detail.other_elective_groups && detail.other_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">其他選修群</span>}
                badge={detail.other_elective_groups.length}
                badgeColor="bg-slate-50 text-slate-500"
                depth={depth}
                defaultOpen={false}
              >
                <div className="mt-4 space-y-2">
                  {detail.other_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {(!detail.core_elective_groups?.length && !detail.elective_groups?.length && !detail.elective_courses?.length && !detail.other_elective_groups?.length) && (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無選修分組資料</div>
          )}
        </div>
      )}

      {activeTab === 'rules' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 space-y-6">
          {/* ── 畢業規定 ─────────────────────────────── */}
          {totalRules > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">畢業規定</span>}
                depth={depth}
                defaultOpen={true}
                leaf={true}
              >
                <div className="mt-4 space-y-1">
                  {CATEGORIES_ORDER.map((cat) => {
                    const rules = rulesByCategory[cat];
                    if (!rules || rules.length === 0) return null;
                    return (
                      <TreeNode
                        key={cat}
                        label={<span className="font-bold text-slate-800">{cat}</span>}
                        icon={CATEGORY_ICON[cat]}
                        depth={depth + 1}
                        defaultOpen={true}
                        leaf={true}
                      >
                        {rules.map((r, i) => (
                          <RuleTree key={`${r.type}-${i}`} rule={r} depth={depth + 2} />
                        ))}
                      </TreeNode>
                    );
                  })}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── dept_with_groups 的子群組 ────────────── */}
          {detail.groups && detail.groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">分組課程</span>}
                badge={detail.groups.length + '組'}
                badgeColor="bg-teal-50 text-teal-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.groups.map((g) => (
                    <TreeNode
                      key={g.id}
                      label={<span className="font-bold text-slate-800">{g.name}</span>}
                      icon="▸"
                      depth={depth + 1}
                      defaultOpen={false}
                    >
                      <DeptTree detail={g} depth={depth + 2} />
                    </TreeNode>
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 畢業備註 ────────────────────────────── */}
          {detail.graduation_notes && (
            <SectionCard>
              <TreeNode label={<span className="text-base font-black text-teal-900 tracking-wide drop-shadow-sm">畢業說明</span>} depth={depth} defaultOpen={false}>
                <div
                  className="mt-4 mx-2 rounded-xl bg-amber-50/50 border border-amber-100 p-5 text-sm leading-relaxed text-slate-700 shadow-sm"
                  style={{ marginLeft: (depth + 1) * INDENT }}
                >
                  {detail.graduation_notes}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {(!totalRules && (!detail.groups || detail.groups.length === 0) && !detail.graduation_notes) && (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無畢業規定資料</div>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 系所 Header
// ══════════════════════════════════════════════════════════════════════════

function DeptHeader({ detail }: { detail: DeptDetail }) {
  return (
    <div className="sticky top-0 z-20 border-b border-slate-200/60 bg-white/80 backdrop-blur-xl px-8 py-5 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-extrabold tracking-tight text-teal-800 drop-shadow-sm">
          {detail.name}
        </h2>
        {detail.min_credits > 0 && (
          <span className="rounded-lg bg-amber-50/80 border border-amber-100 px-3.5 py-[7px] text-[11px] font-bold leading-none text-amber-800 shadow-sm">
            最低 {detail.min_credits} 學分
          </span>
        )}
        {detail.required_credits !== undefined && (
          <span className="rounded-lg bg-teal-50/80 border border-teal-100 px-3.5 py-[7px] text-[11px] font-bold leading-none text-teal-800 shadow-sm">
            必修 {detail.required_credits} 學分
          </span>
        )}
      </div>
      <button
        onClick={() => {
          const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
          window.open(`${baseUrl}/curriculum/pdf/${detail.id}`, '_blank');
        }}
        className="shrink-0 flex items-center gap-2 rounded-xl bg-white border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 shadow-sm hover:bg-slate-50 hover:text-teal-600 hover:border-teal-200 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        查看原始應修科目表
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 參考文字面板
// ══════════════════════════════════════════════════════════════════════════

function NotesPanel({ deptId }: { deptId: string }) {
  const [entries, setEntries] = useState<NotesEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!deptId) return;
    void (async () => { await Promise.resolve(); setLoading(true); })();
    apiClient
      .get(`/curriculum/notes/by-id/${deptId}`)
      .then((res) => setEntries(res.data.entries ?? []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [deptId]);

  if (loading) return <div className="p-5 text-xs text-slate-400">載入參考資料…</div>;
  if (entries.length === 0)
    return <div className="p-5 text-xs text-slate-400 font-medium">（無對應的原始規定文字）</div>;

  return (
    <div className="space-y-4 p-5">
      <div className="flex items-center gap-2 mb-2">
        <div className="text-[12px] font-bold uppercase tracking-widest text-amber-800/70">
          原始規定參考文字
        </div>
      </div>
      {entries.map((e) => (
        <div key={e.key} className="rounded-xl bg-white/95 backdrop-blur-sm p-5 shadow-soft transition-all duration-300">
          {entries.length > 1 && (
            <div className="mb-2 text-[12px] font-bold text-amber-700 border-b border-amber-200/50 pb-1">{e.key}</div>
          )}
          <div className="text-[12px] leading-relaxed text-slate-700" style={{ whiteSpace: 'pre-wrap' }}>
            {e.raw_text}
          </div>
          {e.source && e.source !== 'pdfplumber_fixed' && (
            <div className="mt-3 text-[10px] font-medium text-amber-500/80 flex justify-end">來源：{e.source}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 學院風格定義
// ══════════════════════════════════════════════════════════════════════════

type CollegeStyle = { iconBg: string; badge: string; icon: React.ReactNode };
const COLLEGE_STYLES: Record<string, CollegeStyle> = {
  '文學院': { 
    iconBg: 'bg-violet-500', 
    badge: 'bg-violet-50 text-violet-600 border-violet-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg> 
  },
  '理學院': { 
    iconBg: 'bg-sky-500', 
    badge: 'bg-sky-50 text-sky-600 border-sky-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M9.75 3h4.5m-4.5 0v3.75L4.5 16.5a2.25 2.25 0 002.25 2.25h10.5a2.25 2.25 0 002.25-2.25L14.25 6.75V3m-4.5 0h4.5" /></svg> 
  },
  '工學院': { 
    iconBg: 'bg-orange-500', 
    badge: 'bg-orange-50 text-orange-600 border-orange-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><circle cx="12" cy="12" r="3" strokeWidth={2.2} /></svg> 
  },
  '管理學院': { 
    iconBg: 'bg-emerald-500', 
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg> 
  },
  '資訊電機學院': { 
    iconBg: 'bg-indigo-500', 
    badge: 'bg-indigo-50 text-indigo-600 border-indigo-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 5h10a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V7a2 2 0 012-2zM9 9h6v6H9V9z" /></svg> 
  },
  '地球科學學院': { 
    iconBg: 'bg-teal-600', 
    badge: 'bg-teal-50 text-teal-600 border-teal-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> 
  },
  '客家學院': { 
    iconBg: 'bg-pink-500', 
    badge: 'bg-pink-50 text-pink-600 border-pink-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg> 
  },
  '生醫理工學院': { 
    iconBg: 'bg-rose-500', 
    badge: 'bg-rose-50 text-rose-600 border-rose-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M6 2c0 6 12 14 12 20 M18 2c0 6-12 14-12 20 M7 3.5h10 M8 6h8 M9 8.5h6 M11 10.5h2 M11 13.5h2 M9 15.5h6 M8 18h8 M7 20.5h10" /></svg> 
  },
  'default': { 
    iconBg: 'bg-slate-500', 
    badge: 'bg-slate-50 text-slate-600 border-slate-100/50',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg> 
  }
};

// ══════════════════════════════════════════════════════════════════════════
// 主頁面
// ══════════════════════════════════════════════════════════════════════════

export default function CurriculumPage() {
  const [tree, setTree] = useState<CollegeNode[]>([]);
  const [childDeptIds, setChildDeptIds] = useState<Set<string>>(new Set());
  const [expandedColleges, setExpandedColleges] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DeptDetail | null>(null);
  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [selectedCourse, setSelectedCourse] = useState<CourseCard | null>(null);

  useEffect(() => {
    const handleShowCourse = (e: Event) => {
      setSelectedCourse((e as CustomEvent<CourseCard>).detail);
    };
    window.addEventListener('SHOW_COURSE_DETAIL', handleShowCourse);
    return () => window.removeEventListener('SHOW_COURSE_DETAIL', handleShowCourse);
  }, []);

  useEffect(() => {
    apiClient
      .get('/curriculum/tree')
      .then((res) => {
        setTree(res.data);
        const ids = new Set<string>();
        res.data.forEach((college: CollegeNode) => {
          if (college.id !== 'college_liberal_arts') return;
          college.college_bachelor_programs.forEach((cbp) => {
            cbp.specialization_tracks?.forEach((t) => ids.add(t.id));
          });
        });
        setChildDeptIds(ids);
      })
      .catch(console.error)
      .finally(() => setLoadingTree(false));
  }, []);

  const selectDept = useCallback((id: string) => {
    setSelectedId(id);
    setDetail(null);
    setLoadingDetail(true);
    apiClient
      .get(`/curriculum/dept/${id}`)
      .then((res) => setDetail(res.data))
      .catch(console.error)
      .finally(() => setLoadingDetail(false));
  }, []);

  const toggleCollege = (id: string) => {
    setExpandedColleges((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  function getProgramBadge(dept: { name: string; program_type?: string }) {
    const type = dept.program_type || '';
    if (type.includes('bachelor') || dept.name.includes('學士班')) {
      return { label: '學士班', className: 'bg-indigo-50 text-indigo-500 border-indigo-100/50' };
    }
    return { label: '系所', className: 'bg-slate-100 text-slate-400 border-slate-200/50' };
  }

  function DeptCard({ 
    dept 
  }: { 
    dept: { id: string; name: string; program_type?: string; groups: { id: string; name: string }[] }
  }) {
    const hasGroups = dept.groups.length > 0;
    const isDeptSelected = selectedId === dept.id;
    const isChildSelected = hasGroups && dept.groups.some(g => g.id === selectedId);
    const isActive = isDeptSelected || isChildSelected;
    const isExpanded = isActive;

    const badgeInfo = getProgramBadge(dept);

    return (
      <div
        className={`w-full bg-white rounded-[16px] border text-left transition-all duration-300 shadow-[0_4px_12px_rgba(0,0,0,0.03)] hover:shadow-[0_8px_20px_rgba(0,0,0,0.06)] overflow-hidden ${
          isActive
            ? 'border-indigo-100 bg-gradient-to-b from-white to-indigo-50/10 ring-1 ring-indigo-500/10'
            : 'border-slate-100 hover:border-slate-200'
        }`}
      >
        {/* 卡片主體按鈕 */}
        <div
          onClick={() => selectDept(dept.id)}
          className="w-full flex items-center justify-between py-3.5 px-4 cursor-pointer select-none"
        >
          <div className="flex items-center gap-2.5">
            <span className={`text-[14px] leading-tight transition-colors ${
              isActive ? 'font-bold text-indigo-700' : 'font-semibold text-slate-700'
            }`}>
              {dept.name}
            </span>
            <span className={`shrink-0 rounded-lg px-3 py-[5.5px] text-[10px] font-bold leading-none tracking-wide shadow-sm border ${badgeInfo.className}`}>
              {badgeInfo.label}
            </span>
          </div>
          
          <div className="flex items-center gap-1.5">
            <svg 
              className={`w-3.5 h-3.5 shrink-0 transition-all duration-300 ${
                isActive 
                  ? 'text-indigo-500 translate-x-0.5' 
                  : 'text-slate-300 group-hover:translate-x-0.5'
              }`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>

        {/* 展開的子分組區域 */}
        {hasGroups && isExpanded && (
          <div className="px-5 pb-4 pt-3 border-t border-slate-50 animate-in fade-in slide-in-from-top-1 duration-200">
            <div className="flex items-center justify-between text-slate-400 text-[11px] font-bold tracking-wider mb-2">
              <span>專業分組 / 領域</span>
              <span className="bg-blue-50 text-blue-500 text-[10px] font-bold px-2 py-0.5 rounded-full border border-blue-100/50">
                {dept.groups.length}
              </span>
            </div>
            
            <div className="relative pl-4 mt-2.5 space-y-3">
              {/* 垂直樹狀引導線 */}
              <div className="absolute left-[3px] top-0 bottom-[12px] w-[1px] bg-slate-200" />
              
              {dept.groups.map((g) => {
                const isSelected = selectedId === g.id;
                return (
                  <div
                    key={g.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      selectDept(g.id);
                    }}
                    className="relative flex items-center group/item cursor-pointer"
                  >
                    {/* 水平引導線 */}
                    <div className="absolute left-[-13px] top-[50%] w-[10px] h-[1px] bg-slate-200" />
                    
                    {/* 精緻圓點 */}
                    <div className={`absolute left-[-5px] w-2 h-2 rounded-full border transition-all duration-300 ${
                      isSelected
                        ? 'bg-indigo-600 border-indigo-200 scale-110 shadow-[0_0_6px_rgba(99,102,241,0.6)]'
                        : 'bg-slate-300 border-white group-hover/item:bg-slate-400'
                    }`} />
                    
                    {/* 項目名稱 */}
                    <span className={`text-[12.5px] pl-1.5 transition-all duration-200 ${
                      isSelected
                        ? 'font-bold text-indigo-600 translate-x-0.5'
                        : 'text-slate-500 group-hover/item:text-slate-700'
                    }`}>
                      {g.name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-slate-50/50 font-sans leading-7 text-slate-900 relative">

      {/* 側邊欄縮放把手 */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`absolute z-30 top-24 transition-all duration-300 flex items-center justify-center w-5 h-20 bg-slate-50/95 backdrop-blur-md border-y border-r border-slate-300 rounded-r-xl shadow-[4px_0_12px_-2px_rgba(0,0,0,0.1)] hover:bg-teal-50 hover:border-teal-400 hover:text-teal-600 text-slate-500 ${isSidebarOpen ? 'left-[340px]' : 'left-0'}`}
      >
        <svg className={`w-4 h-4 transition-transform duration-300 ${isSidebarOpen ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
      </button>

      {/* ── 左側 Sidebar ── */}
      <div className={`shrink-0 transition-all duration-300 ${isSidebarOpen ? 'w-[340px]' : 'w-0'} bg-slate-50/50 relative z-20`}>
        <aside className={`w-[340px] h-full flex flex-col overflow-y-auto border-r border-slate-200/60 ${isSidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'} transition-opacity duration-300`}>
          <div className="sticky top-0 z-10 border-b border-slate-200/60 bg-white/95 backdrop-blur-md px-6 py-5 shadow-sm">
            <h1 className="text-base font-bold text-slate-800 drop-shadow-sm pr-6">選擇學院</h1>
          </div>
          <div className="flex-1 py-4 pr-4 pl-8">
            <h2 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-3 ml-0">學院導覽</h2>
            {loadingTree && <div className="py-6 text-center text-xs text-slate-400">載入中…</div>}
            {tree.map((college) => {
              const isOpen = expandedColleges.has(college.id);
              const style = COLLEGE_STYLES[college.name] || COLLEGE_STYLES['default'];

              const depts = [
                ...college.departments.map(d => ({
                  id: d.id,
                  name: d.name,
                  program_type: d.program_type,
                  groups: (d.groups || []).map(g => ({ id: g.id, name: g.group_label || g.name }))
                })),
                ...college.college_bachelor_programs.map(c => ({
                  id: c.id,
                  name: c.name,
                  program_type: c.program_type || 'bachelor_program',
                  groups: (c.specialization_tracks || []).map(t => ({ id: t.id, name: t.name }))
                }))
              ];

              const deptCount = depts.length;

              return (
                <div key={college.id} className="relative mb-2">
                  {/* 學院卡片 - 與所有子卡片同寬 (w-full) */}
                  <div
                    onClick={() => toggleCollege(college.id)}
                    className={`w-full bg-white border border-slate-100 rounded-[16px] text-left transition-all duration-300 shadow-[0_4px_12px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:border-slate-200/80 overflow-hidden cursor-pointer ${
                      isOpen ? 'ring-1 ring-indigo-500/5' : ''
                    }`}
                  >
                    <div className="w-full flex items-center justify-between py-2.5 px-4 select-none">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 ${style.iconBg} rounded-xl flex items-center justify-center shrink-0 shadow-sm text-white [&>svg]:w-5 [&>svg]:h-5`}>
                          {style.icon}
                        </div>
                        <div className="flex flex-col gap-0.5 text-left">
                          <h3 className="text-[15px] font-bold text-slate-800 transition-colors">
                            {college.name}
                          </h3>
                          <div className="flex items-center gap-2">
                            {deptCount > 0 && (
                              <span className={`shrink-0 rounded-lg px-3 py-[5.5px] text-[10px] font-bold leading-none tracking-wide border ${style.badge}`}>
                                {deptCount} 系所
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center">
                        <div className={`transition-transform duration-300 text-slate-300 ${isOpen ? 'rotate-90' : ''} mr-0.5`}>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M9 5l7 7-7 7"></path></svg>
                        </div>
                      </div>
                    </div>
                  </div>

                  {isOpen && depts.length > 0 && (
                    <div className="relative mt-2 space-y-2.5">
                      {depts.map((dept) => (
                        <DeptCard key={dept.id} dept={dept} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      {/* ── 主內容 ── */}
      {!selectedId ? (
        <div className="flex flex-1 items-center justify-center text-slate-400">
          <div className="text-center animate-pulse">
            <p className="text-base font-semibold tracking-wide">請從左側選擇系所</p>
          </div>
        </div>
      ) : loadingDetail ? (
        <div className="flex flex-1 items-center justify-center text-slate-400 text-sm font-medium">載入中…</div>
      ) : detail ? (
        <div className="flex flex-1 overflow-hidden relative">
          {/* 樹狀主區 */}
          <div className="flex flex-1 flex-col overflow-hidden bg-white/40">
            <DeptHeader detail={detail} />
            <div className="flex-1 overflow-y-auto px-6 pt-6 pb-20">
              <div className="max-w-5xl mx-auto">
                <DeptTree 
                  key={detail.id} 
                  detail={detail} 
                  depth={0} 
                  defaultTab={childDeptIds.has(detail.id) ? 'elective' : undefined} 
                  showNotes={showNotes}
                  setShowNotes={setShowNotes}
                />
              </div>
            </div>
          </div>

          {/* 參考文字面板 */}
          {showNotes && (
            <aside className="w-80 shrink-0 overflow-y-auto border-l border-amber-200/50 bg-gradient-to-br from-amber-50/80 to-orange-50/80 backdrop-blur-lg z-10 relative shadow-[-4px_0_24px_-12px_rgba(0,0,0,0.05)]">
              <NotesPanel deptId={detail.id} />
            </aside>
          )}
        </div>
      ) : null}

      {selectedCourse && (
        <CourseDetailModal
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
        />
      )}
    </div>
  );
}
