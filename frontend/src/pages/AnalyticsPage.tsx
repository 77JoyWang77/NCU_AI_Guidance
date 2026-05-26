import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  HiAcademicCap,
  HiChat,
  HiBookOpen,
  HiOfficeBuilding,
  HiChevronRight,
  HiLogout,
  HiClipboardList,
  HiGlobeAlt,
  HiZoomIn,
  HiMap,
  HiAdjustments,
} from 'react-icons/hi';
import { useAuth } from '../auth/AuthContext';
import { analyticsAPI, type AnalyticsData } from '../api/services';

// ── 學院 → 學術領域對照 ─────────────────────────────────────────
const COLLEGE_TO_DOMAIN: Record<string, string> = {
  '理學院':                   '理工',
  '工學院':                   '理工',
  '地球科學學院':             '理工',
  '永續與綠能科技研究學院':   '理工',
  '資訊電機學院':             '資訊',
  '生醫理工學院':             '生醫',
  '文學院':                   '人文',
  '客家學院':                 '人文',
  '管理學院':                 '商管',
  '中心、處室':               '通識',
};
const DOMAIN_ORDER = ['理工', '資訊', '生醫', '人文', '商管'];
const DOMAIN_COLORS: Record<string, string> = {
  理工: '#6366f1', 資訊: '#0ea5e9', 生醫: '#10b981', 人文: '#f59e0b', 商管: '#ef4444',
};

// ── 探索型態診斷 ─────────────────────────────────────────────────
const EXPLORE_TYPES = [
  {
    id: 'planning',
    label: '規劃導向型',
    Icon: HiClipboardList,
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-100',
    desc: '你常查詢學程規定與畢業門檻，展現清晰的修課規劃意識。',
    color: 'from-amber-50 to-orange-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
  },
  {
    id: 'cross',
    label: '跨域探索型',
    Icon: HiGlobeAlt,
    iconColor: 'text-violet-600',
    iconBg: 'bg-violet-100',
    desc: '你的興趣橫跨三個以上學術領域，善於尋找跨領域的知識連結。',
    color: 'from-violet-50 to-purple-50 border-violet-200',
    badge: 'bg-violet-100 text-violet-700',
  },
  {
    id: 'deep',
    label: '專注深挖型',
    Icon: HiZoomIn,
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-100',
    desc: '你深度探索特定領域的課程，方向清晰、目標明確。',
    color: 'from-blue-50 to-indigo-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
  },
  {
    id: 'wide',
    label: '廣泛探索型',
    Icon: HiMap,
    iconColor: 'text-emerald-600',
    iconBg: 'bg-emerald-100',
    desc: '你對多元課程保持開放，探索範圍廣泛，善於發掘新可能。',
    color: 'from-emerald-50 to-teal-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700',
  },
  {
    id: 'balanced',
    label: '均衡探索型',
    Icon: HiAdjustments,
    iconColor: 'text-slate-600',
    iconBg: 'bg-slate-100',
    desc: '你的探索模式均衡，兼顧深度與廣度，靈活應對各類需求。',
    color: 'from-slate-50 to-gray-50 border-slate-200',
    badge: 'bg-slate-100 text-slate-600',
  },
];

function diagnoseType(
  data: AnalyticsData,
  domainAxes: { label: string; value: number }[],
): typeof EXPLORE_TYPES[0] {
  const topDeptPct = data.dept_distribution[0]?.pct ?? 0;
  const deptCount  = data.dept_distribution.length;
  const topTools   = data.tool_usage.slice(0, 6).map(t => t.tool);
  const planningTools = ['get_graduation_requirements', 'get_graduation_rules',
    'get_program_info', 'get_program_courses', 'get_requirements_notes'];
  const domainsActive = domainAxes.filter(a => a.value >= 15).length;

  const hasPlanningFocus = topTools.some(t => planningTools.includes(t));
  if (hasPlanningFocus) return EXPLORE_TYPES[0];
  if (domainsActive >= 3)        return EXPLORE_TYPES[1];
  if (topDeptPct > 50)           return EXPLORE_TYPES[2];
  if (deptCount >= 5 && topDeptPct < 35) return EXPLORE_TYPES[3];
  return EXPLORE_TYPES[4];
}

// ── 雷達圖 (SVG) ────────────────────────────────────────────────
function RadarChart({ axes }: { axes: { label: string; value: number }[] }) {
  const SIZE = 200;
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const R = SIZE * 0.33;
  const LABEL_R = R + 26;
  const n = axes.length;

  const angle = (i: number) => (i * 2 * Math.PI) / n - Math.PI / 2;
  const pt = (i: number, frac: number) => ({
    x: cx + R * frac * Math.cos(angle(i)),
    y: cy + R * frac * Math.sin(angle(i)),
  });
  const polyStr = (fn: (i: number) => number) =>
    axes.map((_, i) => { const p = pt(i, fn(i)); return `${p.x},${p.y}`; }).join(' ');

  const labelPts = axes.map((_, i) => ({
    x: cx + LABEL_R * Math.cos(angle(i)),
    y: cy + LABEL_R * Math.sin(angle(i)),
  }));
  const pad = 22;
  const minX = Math.min(...labelPts.map(p => p.x)) - pad;
  const minY = Math.min(...labelPts.map(p => p.y)) - pad;
  const maxX = Math.max(...labelPts.map(p => p.x)) + pad;
  const maxY = Math.max(...labelPts.map(p => p.y)) + pad;

  return (
    <svg viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} className="w-full max-w-[240px]">
      {[0.25, 0.5, 0.75, 1.0].map((lv, gi) => (
        <polygon key={gi} points={polyStr(() => lv)}
          fill="none" stroke="#e2e8f0" strokeWidth={gi === 3 ? 1.5 : 0.8} />
      ))}
      {axes.map((_, i) => {
        const end = pt(i, 1);
        return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#e2e8f0" strokeWidth="1" />;
      })}
      <polygon
        points={polyStr(i => Math.max(axes[i].value / 100, 0.04))}
        fill="rgba(99,102,241,0.15)" stroke="#6366f1" strokeWidth="2"
      />
      {axes.map((ax, i) => {
        const p = pt(i, Math.max(ax.value / 100, 0.04));
        const color = DOMAIN_COLORS[ax.label] ?? '#6366f1';
        return <circle key={i} cx={p.x} cy={p.y} r="4" fill={color} />;
      })}
      {axes.map((ax, i) => {
        const lx = cx + LABEL_R * Math.cos(angle(i));
        const ly = cy + LABEL_R * Math.sin(angle(i));
        const color = DOMAIN_COLORS[ax.label] ?? '#334155';
        return (
          <g key={i}>
            <text x={lx} y={ly - 5} textAnchor="middle" fontSize="11"
              fill={color} fontFamily="system-ui,sans-serif" fontWeight="700">
              {ax.label}
            </text>
            <text x={lx} y={ly + 9} textAnchor="middle" fontSize="9.5"
              fill="#94a3b8" fontFamily="system-ui,sans-serif">
              {ax.value}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── 甜甜圈圖 (SVG) ───────────────────────────────────────────────
const DONUT_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b'];

function DonutChart({ items }: { items: { name: string; pct: number }[] }) {
  const R = 56;
  const STROKE = 18;
  const SIZE = 160;
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const C = 2 * Math.PI * R;

  let cumPct = 0;

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-36 h-36 shrink-0">
      <circle cx={cx} cy={cy} r={R} fill="none" stroke="#f1f5f9" strokeWidth={STROKE} />
      {items.map((item, i) => {
        const segLen = (item.pct / 100) * C;
        const dashoffset = C * 0.25 - (cumPct / 100) * C;
        cumPct += item.pct;
        return (
          <circle
            key={item.name}
            cx={cx} cy={cy} r={R}
            fill="none"
            stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
            strokeWidth={STROKE}
            strokeDasharray={`${segLen} ${C - segLen}`}
            strokeDashoffset={dashoffset}
            strokeLinecap="butt"
          />
        );
      })}
    </svg>
  );
}

// ── 標籤雲 ─────────────────────────────────────────────────────
const TAG_COLORS = [
  'bg-primary-50 text-primary-700',
  'bg-violet-50 text-violet-700',
  'bg-sky-50 text-sky-700',
  'bg-emerald-50 text-emerald-700',
  'bg-amber-50 text-amber-700',
  'bg-rose-50 text-rose-700',
];

function TagCloud({ tags }: { tags: { tag: string; count: number }[] }) {
  const max = tags[0]?.count || 1;
  return (
    <div className="flex flex-wrap gap-2 leading-snug">
      {tags.map((t, i) => {
        const ratio = t.count / max;
        const size =
          ratio > 0.75 ? 'text-xl font-bold px-4 py-1.5' :
          ratio > 0.5  ? 'text-base font-semibold px-3 py-1' :
          ratio > 0.3  ? 'text-sm font-medium px-2.5 py-1' :
                         'text-xs px-2 py-0.5';
        return (
          <span key={t.tag}
            className={`inline-flex items-center rounded-full ${size} ${TAG_COLORS[i % TAG_COLORS.length]} transition-transform hover:scale-105`}
            title={`出現 ${t.count} 次`}
          >
            {t.tag}
          </span>
        );
      })}
    </div>
  );
}

// ── 系所橫條 ────────────────────────────────────────────────────
function DeptBar({ name, count, pct, rank }: { name: string; count: number; pct: number; rank: number }) {
  const opacity = rank < 3 ? 'opacity-100' : rank < 6 ? 'opacity-80' : 'opacity-60';
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-slate-700">{name}</span>
        <span className="shrink-0 text-xs text-slate-400">{count} 次</span>
      </div>
      <div className="h-2 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full bg-primary-500 transition-all duration-700 ${opacity}`}
          style={{ width: `${Math.max(pct, 1)}%` }} />
      </div>
    </div>
  );
}

// ── 概覽卡片 ────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string | number; sub?: string;
}) {
  return (
    <div className="card flex items-start gap-4 p-5">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className="mt-0.5 truncate text-2xl font-bold text-primary-900">{value}</p>
        {sub && <p className="mt-0.5 truncate text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

// ── 區塊標題 ────────────────────────────────────────────────────
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-wide text-primary-900 uppercase">
      <span className="inline-block h-1 w-4 rounded-full bg-accent-400" />
      {children}
    </h2>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-100 ${className ?? ''}`} />;
}

function NotLoggedIn() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
        <HiAcademicCap className="h-8 w-8 text-slate-400" />
      </div>
      <h2 className="text-lg font-semibold text-slate-700">請先登入</h2>
      <p className="mt-1 text-sm text-slate-400">登入後即可查看你的課程探索分析</p>
      <Link to="/course-search" className="btn-primary mt-6 inline-flex items-center gap-1.5 text-sm">
        前往課程搜尋 <HiChevronRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
        <HiBookOpen className="h-8 w-8 text-slate-300" />
      </div>
      <h2 className="text-lg font-semibold text-slate-600">還沒有使用記錄</h2>
      <p className="mt-1 text-sm text-slate-400">開始使用課程搜尋，分析結果將在這裡呈現</p>
      <Link to="/course-search" className="btn-primary mt-6 inline-flex items-center gap-1.5 text-sm">
        開始搜尋課程 <HiChevronRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

// ── 主頁面 ──────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError('');
    analyticsAPI.get()
      .then(setData)
      .catch(() => setError('載入分析資料失敗，請稍後再試'))
      .finally(() => setLoading(false));
  }, [user]);

  const domainAxes = useMemo(() => {
    if (!data?.college_distribution.length) return [];
    const totals: Record<string, number> = {};
    for (const item of data.college_distribution) {
      const d = COLLEGE_TO_DOMAIN[item.name] ?? '其他';
      totals[d] = (totals[d] ?? 0) + item.count;
    }
    const grand = Object.values(totals).reduce((a, b) => a + b, 0) || 1;
    return DOMAIN_ORDER.map(d => ({
      label: d,
      value: Math.round(((totals[d] ?? 0) / grand) * 100),
    }));
  }, [data]);

  const exploreType = useMemo(
    () => (data ? diagnoseType(data, domainAxes) : null),
    [data, domainAxes],
  );

  const hasData = data && data.overview.total_turns > 0;

  if (authLoading) {
    return (
      <div className="page-container py-12">
        <Skeleton className="mb-8 h-16 w-64" />
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Skeleton className="h-72" /><Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  if (!user) return <div className="page-container py-12 page-animate"><NotLoggedIn /></div>;

  return (
    <div className="page-container py-10 page-animate">
      {/* 頁首 */}
      <div className="mb-8 flex items-start justify-between">
        <div className="flex items-center gap-4">
          {user.picture ? (
            <img src={user.picture} alt=""
              className="h-14 w-14 rounded-full object-cover ring-4 ring-primary-100" />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-100 text-xl font-bold text-primary-700">
              {user.name?.[0] ?? '?'}
            </div>
          )}
          <div>
            <h1 className="text-xl font-bold text-primary-900">{user.name}</h1>
            <p className="text-sm text-slate-500">{user.email}</p>
            <p className="mt-0.5 text-xs text-slate-400">學習傾向分析</p>
          </div>
        </div>
        <button type="button" onClick={logout}
          className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-500 shadow-sm transition hover:border-red-200 hover:bg-red-50 hover:text-red-600">
          <HiLogout className="h-4 w-4" /> 登出
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <Skeleton className="h-80" /><Skeleton className="h-80" />
            <Skeleton className="h-64" /><Skeleton className="h-64" />
          </div>
        </div>
      ) : !hasData ? (
        <EmptyState />
      ) : (
        <div className="space-y-6">
          {/* 概覽卡片 */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard icon={<HiChat className="h-5 w-5" />} label="對話次數"
              value={data.overview.total_sessions} sub="歷史對話總數" />
            <StatCard icon={<HiBookOpen className="h-5 w-5" />} label="提問輪次"
              value={data.overview.total_turns} sub="累計提問次數" />
            <StatCard icon={<HiAcademicCap className="h-5 w-5" />} label="探索課程"
              value={data.overview.total_courses_explored} sub="不重複課程數" />
            <StatCard icon={<HiOfficeBuilding className="h-5 w-5" />} label="最常探索學院"
              value={data.overview.fav_college || '—'} sub="依出現頻率統計" />
          </div>

          {/* Row 1：學術領域雷達 + 探索型態診斷 */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="card p-6">
              <SectionTitle>學術探索領域分佈</SectionTitle>
              {domainAxes.filter(a => a.value > 0).length < 2 ? (
                <p className="text-sm text-slate-400">需要更多對話資料</p>
              ) : (
                <div className="flex flex-col items-center gap-4">
                  <RadarChart axes={domainAxes} />
                  <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                    {domainAxes.map(ax => (
                      <span key={ax.label} className="flex items-center gap-1.5 text-xs text-slate-500">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_COLORS[ax.label] ?? '#94a3b8' }} />
                        {ax.label} <span className="font-medium text-slate-700">{ax.value}%</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 探索型態診斷 */}
            {exploreType && (
              <div className={`card overflow-hidden border bg-gradient-to-br p-6 ${exploreType.color}`}>
                <SectionTitle>探索型態診斷</SectionTitle>
                <div className="flex flex-col items-center gap-5 pt-2 text-center">
                  <div className={`flex h-20 w-20 items-center justify-center rounded-2xl ${exploreType.iconBg}`}>
                    <exploreType.Icon className={`h-10 w-10 ${exploreType.iconColor}`} />
                  </div>
                  <div>
                    <span className={`rounded-full px-4 py-1 text-sm font-bold ${exploreType.badge}`}>
                      {exploreType.label}
                    </span>
                    <p className="mt-3 text-sm leading-relaxed text-slate-600">{exploreType.desc}</p>
                  </div>
                  <div className="w-full rounded-xl bg-white/60 px-4 py-3 text-left">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">關鍵數據</p>
                    <div className="space-y-1 text-xs text-slate-600">
                      <div className="flex justify-between">
                        <span>探索系所數</span>
                        <span className="font-medium">{data.dept_distribution.length} 個</span>
                      </div>
                      <div className="flex justify-between">
                        <span>最集中系所</span>
                        <span className="font-medium">{data.dept_distribution[0]?.pct.toFixed(1) ?? 0}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span>跨域廣度</span>
                        <span className="font-medium">{domainAxes.filter(a => a.value >= 15).length} 個主要領域</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Row 2：興趣標籤雲 + 學院甜甜圈 */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="card p-6">
              <SectionTitle>課程興趣標籤雲</SectionTitle>
              <p className="mb-4 text-xs text-slate-400">
                標籤字體越大，代表 AI 推薦課程中該領域越常出現
              </p>
              {data.top_domain_tags.length === 0 ? (
                <p className="text-sm text-slate-400">尚無資料（需要更多 AI 推薦記錄）</p>
              ) : (
                <TagCloud tags={data.top_domain_tags} />
              )}
            </div>

            <div className="card p-6">
              <SectionTitle>學院探索分佈</SectionTitle>
              {data.college_distribution.length === 0 ? (
                <p className="text-sm text-slate-400">尚無資料</p>
              ) : (
                <div className="flex items-center gap-6">
                  <DonutChart items={data.college_distribution} />
                  <div className="min-w-0 flex-1 space-y-2.5">
                    {data.college_distribution.map((item, i) => (
                      <div key={item.name} className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                        <span className="min-w-0 flex-1 truncate text-xs text-slate-700">{item.name}</span>
                        <span className="shrink-0 text-xs font-medium text-slate-500">{item.pct}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Row 3：系所分佈 + 最常被推薦課程 */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="card p-6">
              <SectionTitle>最常探索系所 Top 8</SectionTitle>
              {data.dept_distribution.length === 0 ? (
                <p className="text-sm text-slate-400">尚無資料</p>
              ) : (
                <div className="space-y-4">
                  {data.dept_distribution.map((item, idx) => (
                    <DeptBar key={item.name} name={item.name} count={item.count} pct={item.pct} rank={idx} />
                  ))}
                </div>
              )}
            </div>

            <div className="card p-6">
              <SectionTitle>最常被推薦課程 Top 10</SectionTitle>
              <p className="mb-3 text-xs text-slate-400">統計 AI 回答中實際提及的課程</p>
              {data.top_courses.length === 0 ? (
                <p className="text-sm text-slate-400">尚無資料</p>
              ) : (
                <ol className="space-y-2">
                  {data.top_courses.map((item, idx) => (
                    <li key={item.name} className="flex items-center gap-3">
                      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold
                        ${idx < 3 ? 'bg-primary-900 text-white' : 'bg-slate-100 text-slate-500'}`}>
                        {idx + 1}
                      </span>
                      <span className="flex-1 text-sm text-slate-700">{item.name}</span>
                      <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                        ×{item.count}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
