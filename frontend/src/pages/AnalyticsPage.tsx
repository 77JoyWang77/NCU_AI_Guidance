import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import 'echarts-wordcloud';
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
import { analyticsAPI, type AnalyticsData, type AnalyticsGeneralEdu } from '../api/services';

// ── 學院 → 學術領域對照 ─────────────────────────────────────────
const COLLEGE_TO_DOMAIN: Record<string, string> = {
  '理學院':                   '理工',
  '工學院':                   '理工',
  '地球科學學院':             '地科',
  '永續與綠能科技研究學院':   '理工',
  '資訊電機學院':             '資訊',
  '生醫理工學院':             '生醫',
  '文學院':                   '人文',
  '客家學院':                 '人文',
  '管理學院':                 '商管',
  '中心、處室':               '通識',
};
const DOMAIN_ORDER = ['理工', '資訊', '地科', '生醫', '人文', '商管'];
const DOMAIN_COLORS: Record<string, string> = {
  理工: '#6366f1', 資訊: '#0ea5e9', 地科: '#a16207',
  生醫: '#10b981', 人文: '#f59e0b', 商管: '#ef4444',
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
  const domainsActive = domainAxes.filter(a => ((a as { pct?: number }).pct ?? a.value) >= 15).length;

  const hasPlanningFocus = topTools.some(t => planningTools.includes(t));
  if (hasPlanningFocus) return EXPLORE_TYPES[0];
  if (domainsActive >= 3)        return EXPLORE_TYPES[1];
  if (topDeptPct > 50)           return EXPLORE_TYPES[2];
  if (deptCount >= 5 && topDeptPct < 35) return EXPLORE_TYPES[3];
  return EXPLORE_TYPES[4];
}

// ── 雷達圖 (SVG) ────────────────────────────────────────────────
function RadarChart({ axes }: { axes: { label: string; value: number; pct?: number }[] }) {
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
              fill={DOMAIN_COLORS[ax.label] ?? '#94a3b8'} fontFamily="system-ui,sans-serif" opacity="0.7">
              {ax.value}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const DONUT_COLORS = [
  '#6366f1', '#8b5cf6', '#06b6d4', '#10b981',
  '#f59e0b', '#f97316', '#ec4899', '#14b8a6',
];

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
    void (async () => {
      await Promise.resolve();
      setLoading(true);
      setError('');
      try {
        const result = await analyticsAPI.get();
        setData(result);
      } catch {
        setError('載入分析資料失敗，請稍後再試');
      } finally {
        setLoading(false);
      }
    })();
  }, [user]);

  const domainAxes = useMemo(() => {
    if (!data?.college_distribution.length) return [];
    const totals: Record<string, number> = {};
    for (const item of data.college_distribution) {
      const d = COLLEGE_TO_DOMAIN[item.name] ?? '其他';
      totals[d] = (totals[d] ?? 0) + item.count;
    }
    const nonGeTotal = DOMAIN_ORDER.reduce((s, d) => s + (totals[d] ?? 0), 0) || 1;
    const maxVal = Math.max(...DOMAIN_ORDER.map(d => totals[d] ?? 0)) || 1;

    return DOMAIN_ORDER.map(d => {
      const raw = totals[d] ?? 0;
      const pct = Math.round((raw / nonGeTotal) * 1000) / 10;        // 佔總量 %（顯示用）
      const rel = Math.round((raw / maxVal) * 100);                   // 相對最大值（雷達圖用）
      return { label: d, value: rel, pct };
    });
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
                  {/* 圖例：顯示實際佔比 % */}
                  <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                    {domainAxes.map(ax => (
                      <span key={ax.label} className="flex items-center gap-1.5 text-xs text-slate-500">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_COLORS[ax.label] ?? '#94a3b8' }} />
                        {ax.label} <span className="font-medium text-slate-700">{ax.pct}%</span>
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
                        <span className="font-medium">{domainAxes.filter(a => ((a as { pct?: number }).pct ?? a.value) >= 15).length} 個主要領域</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Row 2：domain_tags WordCloud + 課程領域 WordCloud */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {data.top_domain_tags.length > 0 && (
              <EChartsWordCloud tags={data.top_domain_tags} title="課程探索領域" />
            )}
            {data.top_course_domains.length > 0 && (
              <EChartsWordCloud
                tags={data.top_course_domains.map(d => ({ tag: d.domain, count: d.count }))}
                title="課程領域分佈"
              />
            )}
          </div>

          {/* Row 3：探索系所 Pie + 通識與一般選修 */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {data.dept_distribution.length > 0 && (
              <EChartsPie items={data.dept_distribution} title="探索系所分佈" />
            )}
            <GeneralEduRings ge={data.general_edu} />
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// ECharts 圖表元件
// ══════════════════════════════════════════════════════════════════

// ── ECharts WordCloud：domain_tags ────────────────────────────────
function EChartsWordCloud({ tags, title = '課程探索領域' }: { tags: { tag: string; count: number }[]; title?: string }) {
  const option = {
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      left: 'center', top: 'center',
      width: '95%', height: '95%',
      sizeRange: [13, 52],
      rotationRange: [0, 0],       // 全部水平，中文更易讀
      gridSize: 10,
      drawOutOfBound: false,
      textStyle: {
        fontFamily: 'system-ui, sans-serif',
        fontWeight: 'bold',
        color() {
          const palette = [
            '#6366f1','#8b5cf6','#0ea5e9','#10b981',
            '#f59e0b','#ec4899','#14b8a6','#f97316',
          ];
          return palette[Math.floor(Math.random() * palette.length)];
        },
      },
      emphasis: { focus: 'self', textStyle: { shadowBlur: 10, shadowColor: '#333' } },
      data: tags.map(t => ({ name: t.tag, value: t.count })),
    }],
  };
  return (
    <div className="card flex flex-col p-6">
      <SectionTitle>{title}</SectionTitle>
      <p className="mb-3 text-xs text-slate-400">字體大小反映探索頻率</p>
      <ReactECharts option={option} style={{ flex: 1, minHeight: 200 }} />
    </div>
  );
}

// ── ECharts Pie：學院分佈 ─────────────────────────────────────────
function EChartsPie({
  items,
  title = '探索分佈',
}: {
  items: { name: string; count: number; pct: number }[];
  title?: string;
}) {
  // 系所名稱比學院長，legend 欄位要更寬
  const nmWidth = items.some(i => i.name.length > 6) ? 136 : 108;
  const option = {
    tooltip: { trigger: 'item', formatter: '{b}：{d}%', confine: true },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      itemWidth: 8,
      itemHeight: 8,
      formatter: (name: string) => {
        const it = items.find(i => i.name === name);
        return `{nm|${name}}{pt|${it?.pct ?? 0}%}`;
      },
      textStyle: {
        rich: {
          nm: { width: nmWidth, align: 'left',  fontSize: 11, color: '#475569' },
          pt: { width: 36,      align: 'right', fontSize: 11, color: '#94a3b8' },
        },
      },
    },
    series: [{
      type: 'pie',
      radius: ['40%', '66%'],
      center: ['30%', '50%'],
      label: { show: false },
      labelLine: { show: false },
      emphasis: {
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.15)' },
      },
      data: items.map((it, i) => ({
        name: it.name,
        value: it.count,
        itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] },
      })),
    }],
  };
  return (
    <div className="card flex flex-col p-6">
      <SectionTitle>{title}</SectionTitle>
      <ReactECharts option={option} style={{ flex: 1, minHeight: 200 }} />
    </div>
  );
}

const DOMAIN_TREEMAP_COLORS = [
  '#6366f1','#8b5cf6','#0ea5e9','#10b981',
  '#f59e0b','#ec4899','#f97316','#14b8a6',
  '#64748b','#a855f7','#06b6d4','#84cc16',
];

// ── 通識與一般選修：圓形進度環 + 分類標籤 ──────────────────────
const GE_CAT_COLORS: Record<string, string> = {
  通識: '#8b5cf6', 外語: '#0ea5e9', 體育: '#10b981', 服務學習: '#f59e0b',
};

function GeneralEduRings({ ge }: { ge: AnalyticsGeneralEdu }) {
  const top = ge.top_topic_tags.slice(0, 6);
  const maxCount = top[0]?.count ?? 1;
  const C = 2 * Math.PI * 28;

  const hasData = top.length > 0 || ge.categories.length > 0;
  if (!hasData) return null;

  return (
    <div className="card p-6">
      <SectionTitle>通識與一般選修</SectionTitle>

      {/* 分類計數標籤 */}
      {ge.categories.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {ge.categories.map(cat => {
            const color = GE_CAT_COLORS[cat.name] ?? '#94a3b8';
            return (
              <span key={cat.name}
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
                style={{ background: color + '18', color }}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
                {cat.name}
                <span className="font-semibold ml-0.5">{cat.count} 門</span>
              </span>
            );
          })}
        </div>
      )}

      {/* 通識 topic_tags 圓形環 */}
      {top.length > 0 ? (
        <div className="grid grid-cols-3 gap-3">
          {top.map((t, i) => {
            const pct = t.count / maxCount;
            const color = DOMAIN_TREEMAP_COLORS[i % DOMAIN_TREEMAP_COLORS.length];
            const dash = pct * C;
            const gap  = C - dash;
            return (
              <div key={t.tag} className="flex flex-col items-center gap-1.5">
                <div className="relative h-[68px] w-[68px]">
                  <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
                    <circle cx="32" cy="32" r="28" fill="none" stroke="#f1f5f9" strokeWidth="7" />
                    <circle cx="32" cy="32" r="28" fill="none"
                      stroke={color} strokeWidth="7" strokeLinecap="round"
                      strokeDasharray={`${dash} ${gap}`} />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-[11px] font-bold"
                    style={{ color }}>
                    {Math.round(pct * 100)}%
                  </div>
                </div>
                <span className="max-w-[72px] text-center text-[10px] leading-tight text-slate-600">
                  {t.tag}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-slate-400">尚無通識課程探索記錄</p>
      )}
    </div>
  );
}
