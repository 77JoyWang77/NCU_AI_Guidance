import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';

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
  badgeColor = 'bg-gray-100 text-gray-500',
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
    <div>
      <div
        className={`flex items-center gap-1 py-0.5 rounded cursor-pointer select-none
          hover:bg-gray-50 ${dimmed ? 'opacity-50' : ''}`}
        style={{ paddingLeft: depth * INDENT + 4 }}
        onClick={() => hasChildren && setOpen((v) => !v)}
      >
        {/* expand icon */}
        <span className="w-4 shrink-0 text-center text-[10px] text-gray-400">
          {!leaf && hasChildren ? (open ? '▾' : '▸') : ''}
        </span>
        {icon && <span className="text-sm">{icon}</span>}
        <span className={`flex-1 text-sm ${dimmed ? 'text-gray-400' : 'text-gray-800'}`}>{label}</span>
        {badge !== undefined && badge !== '' && (
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeColor}`}>
            {badge}
          </span>
        )}
      </div>
      {open && hasChildren && <div>{children}</div>}
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

function CourseLeaf({ c, depth }: { c: CourseEntry; depth: number }) {
  return (
    <div
      className="flex items-center gap-2 py-0.5 rounded hover:bg-gray-50"
      style={{ paddingLeft: depth * INDENT + 4 }}
    >
      <span className="w-4 shrink-0" />
      <span className="text-xs text-gray-400 font-mono">{c.code}</span>
      <span className="text-sm text-gray-700 flex-1">{c.name}</span>
      {c.when && <span className="text-[10px] text-blue-400">{c.when}</span>}
      {c.credits > 0 && (
        <span className="text-[10px] text-gray-400 shrink-0">{c.credits}cr</span>
      )}
      {c.mandatory && (
        <span className="rounded bg-red-100 px-1 text-[10px] text-red-600">必選</span>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 選修群樹
// ══════════════════════════════════════════════════════════════════════════

function ElectiveGroupTree({ g, depth }: { g: ElectiveGroup; depth: number }) {
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
    <TreeNode
      label={g.name}
      badge={selectLabel || undefined}
      badgeColor="bg-blue-50 text-blue-600"
      icon="📦"
      depth={depth}
      defaultOpen={false}
      dimmed={isEmpty}
    >
      {/* options A/B/C */}
      {hasOptions && (
        <>
          {g.option_a && (
            <TreeNode label="選項 A" icon="▪" depth={depth + 1}>
              {g.option_a.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 2} />)}
            </TreeNode>
          )}
          {g.option_b && (
            <TreeNode label="選項 B" icon="▪" depth={depth + 1}>
              {g.option_b.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 2} />)}
            </TreeNode>
          )}
          {g.option_c && (
            <TreeNode label="選項 C" icon="▪" depth={depth + 1}>
              {g.option_c.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 2} />)}
            </TreeNode>
          )}
        </>
      )}
      {/* 一般課程 */}
      {allCourses.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 1} />)}
      {/* slots */}
      {hasSlots && g.slots!.map((slot, i) => (
        <TreeNode key={i} label={slot.slot_name || `Slot ${i + 1}`}
          badge={`選1`} badgeColor="bg-purple-50 text-purple-600"
          icon="🔀" depth={depth + 1}>
          {slot.courses.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 2} />)}
        </TreeNode>
      ))}
      {isEmpty && (
        <div style={{ paddingLeft: (depth + 1) * INDENT + 4 }}
          className="py-0.5 text-xs text-gray-300 italic">
          （課程列表未收錄）
        </div>
      )}
    </TreeNode>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 畢業規定節點
// ══════════════════════════════════════════════════════════════════════════

const CATEGORY_ICON: Record<string, string> = {
  '學分規定': '📊',
  '指定選課': '🎯',
  '先修條件': '🔗',
  '外部認證': '🏅',
  '特殊規定': '⚙️',
  '其他規定': '📋',
};

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

  const label = (
    <span className="flex items-center gap-1.5">
      <span className={`rounded px-1 py-0.5 text-[10px] font-mono ${CATEGORY_COLOR[rule.category] ?? 'bg-gray-50 text-gray-500'}`}>
        {rule.type}
      </span>
      <span className="text-gray-700">
        {rule.description ?? (rule.cert ? `認證：${rule.cert}` : '')}
      </span>
    </span>
  );

  const creditBadge = rule.credits !== undefined
    ? `${rule.credits}cr`
    : rule.select !== undefined
    ? `選${rule.select}門`
    : undefined;

  if (isLeaf) {
    return (
      <div className="flex items-start gap-1 py-0.5 rounded hover:bg-gray-50"
        style={{ paddingLeft: depth * INDENT + 4 }}>
        <span className="w-4 shrink-0 text-center text-[10px] text-gray-300">•</span>
        <span className="flex-1 text-sm">{label}</span>
        {creditBadge && (
          <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
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
  { key: 'required_courses',          label: '必修課程' },
  { key: 'foundation_courses',        label: '基礎必修' },
  { key: 'college_required_courses',  label: '院訂必修' },
  { key: 'common_required_courses',   label: '共同必修' },
  { key: 'dept_required_courses',     label: '系訂必修' },
  { key: 'required_electives',        label: '必選修' },
  { key: 'cross_domain_required',     label: '跨域必修' },
  { key: 'earth_system_courses',      label: '地球系統科學' },
  { key: 'cross_group_required',      label: '跨組必修' },
  { key: 'application_courses',       label: '應用課程' },
  { key: 'first_domain_electives',    label: '第一領域選修' },
];

function SemesterGroup({ courses, depth }: { courses: CourseEntry[]; depth: number }) {
  const semMap = groupBySem(courses);
  return (
    <>
      {Array.from(semMap.entries()).map(([sem, cs]) => (
        <TreeNode
          key={sem}
          label={sem}
          badge={cs.reduce((s, c) => s + (c.credits || 0), 0) + 'cr'}
          badgeColor="bg-gray-50 text-gray-400"
          depth={depth}
          defaultOpen={true}
        >
          {cs.map((c) => <CourseLeaf key={c.code} c={c} depth={depth + 1} />)}
        </TreeNode>
      ))}
    </>
  );
}

function DeptTree({ detail, depth = 0 }: { detail: DeptDetail; depth?: number }) {
  // 收集所有有課程的必修區塊
  const reqSections = REQUIRED_COURSE_FIELDS
    .map(({ key, label }) => ({
      label,
      courses: (detail[key] as CourseEntry[] | undefined) ?? [],
    }))
    .filter(({ courses }) => courses.length > 0);

  const allRequiredCourses = reqSections.flatMap(({ courses }) => courses);
  const totalReqCr = allRequiredCourses.reduce((s, c) => s + (c.credits || 0), 0);

  const rulesByCategory: Record<string, GraduationRule[]> = {};
  for (const cat of CATEGORIES_ORDER) rulesByCategory[cat] = [];
  for (const rule of detail.graduation_rules ?? []) {
    const cat = rule.category ?? '其他規定';
    if (!rulesByCategory[cat]) rulesByCategory[cat] = [];
    rulesByCategory[cat].push(rule);
  }
  const totalRules = (detail.graduation_rules ?? []).length;

  return (
    <div className="font-sans">
      {/* ── 畢業規定 ─────────────────────────────── */}
      {totalRules > 0 && (
        <TreeNode
          label="畢業規定"
          badge={totalRules}
          badgeColor="bg-gray-100 text-gray-500"
          icon="📜"
          depth={depth}
          defaultOpen={true}
        >
          {CATEGORIES_ORDER.map((cat) => {
            const rules = rulesByCategory[cat];
            if (!rules || rules.length === 0) return null;
            return (
              <TreeNode
                key={cat}
                label={cat}
                icon={CATEGORY_ICON[cat]}
                badge={rules.length}
                badgeColor={CATEGORY_COLOR[cat]}
                depth={depth + 1}
                defaultOpen={true}
              >
                {rules.map((r, i) => (
                  <RuleTree key={`${r.type}-${i}`} rule={r} depth={depth + 2} />
                ))}
              </TreeNode>
            );
          })}
        </TreeNode>
      )}

      {/* ── 必修課程（所有欄位彙整）────────────── */}
      {reqSections.length > 0 && (
        <TreeNode
          label="必修課程"
          badge={`${allRequiredCourses.length}門 · ${totalReqCr}cr`}
          badgeColor="bg-emerald-50 text-emerald-700"
          icon="📚"
          depth={depth}
          defaultOpen={true}
        >
          {reqSections.length === 1 ? (
            /* 只有一種欄位：直接展開學期 */
            <SemesterGroup courses={reqSections[0].courses} depth={depth + 1} />
          ) : (
            /* 多種欄位：先顯示欄位標籤，再展學期 */
            reqSections.map(({ label, courses }) => {
              const cr = courses.reduce((s, c) => s + (c.credits || 0), 0);
              return (
                <TreeNode
                  key={label}
                  label={label}
                  badge={`${courses.length}門 · ${cr}cr`}
                  badgeColor="bg-emerald-50 text-emerald-600"
                  depth={depth + 1}
                  defaultOpen={true}
                >
                  <SemesterGroup courses={courses} depth={depth + 2} />
                </TreeNode>
              );
            })
          )}
        </TreeNode>
      )}

      {/* ── 核心必選群 ───────────────────────────── */}
      {detail.core_elective_groups && detail.core_elective_groups.length > 0 && (
        <TreeNode
          label="核心必選群"
          badge={detail.core_elective_groups.length}
          badgeColor="bg-purple-50 text-purple-600"
          icon="🎯"
          depth={depth}
          defaultOpen={true}
        >
          {detail.core_elective_groups.map((g, i) => (
            <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
          ))}
        </TreeNode>
      )}

      {/* ── 院訂必選群 ───────────────────────────── */}
      {detail.college_required_elective_groups && detail.college_required_elective_groups.length > 0 && (
        <TreeNode
          label="院訂必選群"
          badge={detail.college_required_elective_groups.length}
          badgeColor="bg-teal-50 text-teal-600"
          icon="🎓"
          depth={depth}
          defaultOpen={true}
        >
          {detail.college_required_elective_groups.map((g, i) => (
            <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
          ))}
        </TreeNode>
      )}

      {/* ── 科學能力群 ───────────────────────────── */}
      {detail.science_ability_groups && detail.science_ability_groups.length > 0 && (
        <TreeNode
          label="科學能力必選"
          badge={detail.science_ability_groups.length}
          badgeColor="bg-cyan-50 text-cyan-600"
          icon="🔬"
          depth={depth}
          defaultOpen={true}
        >
          {detail.science_ability_groups.map((g, i) => (
            <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
          ))}
        </TreeNode>
      )}

      {/* ── 選修群 ───────────────────────────────── */}
      {detail.elective_groups && detail.elective_groups.length > 0 && (
        <TreeNode
          label="選修群"
          badge={detail.elective_groups.length}
          badgeColor="bg-blue-50 text-blue-600"
          icon="📖"
          depth={depth}
          defaultOpen={true}
        >
          {detail.elective_groups.map((g, i) => (
            <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
          ))}
        </TreeNode>
      )}

      {/* ── 領域選修課程（可選修達到選修學分要求）── */}
      {detail.elective_courses && detail.elective_courses.length > 0 && (
        <TreeNode
          label="領域選修課程"
          badge={`${detail.elective_courses.length}門可選`}
          badgeColor="bg-violet-50 text-violet-600"
          icon="🔖"
          depth={depth}
          defaultOpen={false}
        >
          <SemesterGroup courses={detail.elective_courses} depth={depth + 1} />
        </TreeNode>
      )}

      {/* ── 其他選修群 ───────────────────────────── */}
      {detail.other_elective_groups && detail.other_elective_groups.length > 0 && (
        <TreeNode
          label="其他選修群"
          badge={detail.other_elective_groups.length}
          badgeColor="bg-gray-50 text-gray-500"
          icon="📂"
          depth={depth}
          defaultOpen={false}
        >
          {detail.other_elective_groups.map((g, i) => (
            <ElectiveGroupTree key={i} g={g} depth={depth + 1} />
          ))}
        </TreeNode>
      )}

      {/* ── dept_with_groups 的子群組 ────────────── */}
      {detail.groups && detail.groups.length > 0 && (
        <TreeNode
          label="分組課程"
          badge={detail.groups.length + '組'}
          badgeColor="bg-indigo-50 text-indigo-600"
          icon="🗂️"
          depth={depth}
          defaultOpen={true}
        >
          {detail.groups.map((g) => (
            <TreeNode
              key={g.id}
              label={g.name}
              icon="▸"
              depth={depth + 1}
              defaultOpen={false}
            >
              <DeptTree detail={g} depth={depth + 2} />
            </TreeNode>
          ))}
        </TreeNode>
      )}

      {/* ── 畢業備註 ────────────────────────────── */}
      {detail.graduation_notes && (
        <TreeNode label="畢業說明" icon="📝" depth={depth} defaultOpen={false}>
          <div
            className="mx-2 rounded bg-amber-50 p-3 text-xs leading-relaxed text-amber-800"
            style={{ marginLeft: (depth + 1) * INDENT }}
          >
            {detail.graduation_notes}
          </div>
        </TreeNode>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 系所 Header
// ══════════════════════════════════════════════════════════════════════════

const PROGRAM_TYPE_LABEL: Record<string, string> = {
  traditional_dept: '傳統學系',
  college_bachelor: '學院學士班',
  dept_with_groups: '系內分組',
  dept_group: '系內組別',
  specialization_track: '專長分流',
};

function DeptHeader({ detail }: { detail: DeptDetail }) {
  return (
    <div className="border-b border-gray-200 bg-white px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-bold text-gray-900">{detail.name}</h2>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
          {PROGRAM_TYPE_LABEL[detail.program_type] ?? detail.program_type}
        </span>
        {detail.min_credits > 0 && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
            最低 {detail.min_credits} 學分
          </span>
        )}
        {detail.required_credits && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
            必修 {detail.required_credits} 學分
          </span>
        )}
      </div>
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
    setLoading(true);
    apiClient
      .get(`/curriculum/notes/by-id/${deptId}`)
      .then((res) => setEntries(res.data.entries ?? []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [deptId]);

  if (loading) return <div className="p-3 text-xs text-gray-400">載入參考資料…</div>;
  if (entries.length === 0)
    return <div className="p-3 text-xs text-gray-300">（無對應的原始規定文字）</div>;

  return (
    <div className="space-y-3 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
        原始規定參考文字
      </div>
      {entries.map((e) => (
        <div key={e.key} className="rounded border border-amber-200 bg-amber-50 p-3">
          {entries.length > 1 && (
            <div className="mb-1 text-[11px] font-medium text-amber-600">{e.key}</div>
          )}
          <div className="text-[11px] leading-relaxed text-amber-900" style={{ whiteSpace: 'pre-wrap' }}>
            {e.raw_text}
          </div>
          {e.source && (
            <div className="mt-1 text-[10px] text-amber-400">來源：{e.source}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 主頁面
// ══════════════════════════════════════════════════════════════════════════

export default function CurriculumPage() {
  const [tree, setTree] = useState<CollegeNode[]>([]);
  const [expandedColleges, setExpandedColleges] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DeptDetail | null>(null);
  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showNotes, setShowNotes] = useState(true);

  useEffect(() => {
    apiClient
      .get('/curriculum/tree')
      .then((res) => setTree(res.data))
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

  function SidebarItem({ id, name, isGroup = false }: { id: string; name: string; isGroup?: boolean }) {
    const selected = selectedId === id;
    return (
      <button
        onClick={() => selectDept(id)}
        className={`block w-full rounded px-2 py-1 text-left transition ${
          selected ? 'bg-blue-600 font-medium text-white' : 'text-gray-700 hover:bg-gray-100'
        } ${isGroup ? 'pl-6 text-[12px]' : 'text-[13px]'}`}
      >
        {name}
      </button>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-white">
      {/* ── 左側 Sidebar ── */}
      <aside className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-gray-200 bg-gray-50">
        <div className="sticky top-0 border-b border-gray-200 bg-gray-50 px-3 py-2">
          <h1 className="text-xs font-bold text-gray-600 uppercase tracking-wider">修課規定</h1>
        </div>
        <div className="flex-1 space-y-0.5 p-1.5">
          {loadingTree && <div className="py-6 text-center text-xs text-gray-400">載入中…</div>}
          {tree.map((college) => {
            const isOpen = expandedColleges.has(college.id);
            const count =
              college.departments.length + college.college_bachelor_programs.length;
            return (
              <div key={college.id}>
                <button
                  onClick={() => toggleCollege(college.id)}
                  className="flex w-full items-center gap-1 rounded px-2 py-1 text-left text-[12px] font-semibold text-gray-600 hover:bg-gray-100"
                >
                  <span className="text-[10px] text-gray-400">{isOpen ? '▾' : '▸'}</span>
                  {college.name}
                  <span className="ml-auto text-[10px] font-normal text-gray-400">{count}</span>
                </button>
                {isOpen && (
                  <div className="mt-0.5 ml-1 space-y-0.5">
                    {college.departments.map((dept) => (
                      <div key={dept.id}>
                        <SidebarItem id={dept.id} name={dept.name} />
                        {dept.groups?.map((g) => (
                          <SidebarItem
                            key={g.id}
                            id={g.id}
                            name={g.group_label || g.name}
                            isGroup
                          />
                        ))}
                      </div>
                    ))}
                    {college.college_bachelor_programs.map((cbp) => (
                      <div key={cbp.id}>
                        <SidebarItem id={cbp.id} name={cbp.name} />
                        {cbp.specialization_tracks?.map((t) => (
                          <SidebarItem key={t.id} id={t.id} name={t.name} isGroup />
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* ── 主內容 ── */}
      {!selectedId ? (
        <div className="flex flex-1 items-center justify-center text-gray-300">
          <div className="text-center">
            <div className="text-5xl mb-3">🌳</div>
            <p className="text-sm">從左側選擇系所</p>
          </div>
        </div>
      ) : loadingDetail ? (
        <div className="flex flex-1 items-center justify-center text-gray-400 text-sm">載入中…</div>
      ) : detail ? (
        <div className="flex flex-1 overflow-hidden">
          {/* 樹狀主區 */}
          <div className="flex flex-1 flex-col overflow-hidden">
            <DeptHeader detail={detail} />
            {/* notes toggle bar */}
            <div className="flex items-center justify-end border-b border-gray-100 bg-gray-50 px-4 py-1.5">
              <button
                onClick={() => setShowNotes((v) => !v)}
                className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-gray-500 hover:bg-gray-100"
              >
                <span>{showNotes ? '◀' : '▶'}</span>
                {showNotes ? '隱藏參考文字' : '顯示參考文字'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-3">
              <DeptTree detail={detail} depth={0} />
            </div>
          </div>

          {/* 參考文字面板 */}
          {showNotes && (
            <aside className="w-72 shrink-0 overflow-y-auto border-l border-gray-200 bg-amber-50/30">
              <NotesPanel deptId={detail.id} />
            </aside>
          )}
        </div>
      ) : null}
    </div>
  );
}
