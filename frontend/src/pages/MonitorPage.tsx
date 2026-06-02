import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {
  HiCheckCircle, HiXCircle, HiRefresh,
  HiTrendingUp, HiTrendingDown,
  HiDatabase, HiServer, HiChip, HiChatAlt2,
} from 'react-icons/hi';
import { useAuth } from '../auth/AuthContext';
import { isDeveloper } from '../auth/developerUtils';
import {
  monitorAPI,
  type MonitorStats, type MonitorTrend,
  type LLMLatency, type DBStats,
} from '../api/services';

type TipParam = { marker: string; seriesName: string; value: number; name: string; axisValue: string; seriesIndex: number };

// ── 日期工具 ─────────────────────────────────────────────────────
function toISO(d: Date) { return d.toISOString().split('T')[0]; }
function weekToRange(w: string) {
  const [yr, wn] = w.split('-W');
  const year = parseInt(yr), week = parseInt(wn);
  const jan4 = new Date(year, 0, 4);
  const mon = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (week - 1) * 7);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  return { start: toISO(mon), end: toISO(sun) };
}
function monthToRange(m: string) {
  const [yr, mo] = m.split('-').map(Number);
  return { start: toISO(new Date(yr, mo - 1, 1)), end: toISO(new Date(yr, mo, 0)) };
}
function todayISO() { return toISO(new Date()); }

// ── ECharts 深色共用 ──────────────────────────────────────────────
const TIP = { backgroundColor: '#0f172a', borderColor: '#334155', textStyle: { color: '#e2e8f0' } };
const AX  = {
  axisLine: { lineStyle: { color: '#334155' } },
  splitLine: { lineStyle: { color: '#1e293b' } },
  axisLabel: { color: '#94a3b8', fontSize: 11 },
};

function fmt(n: number) {
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n/1_000).toFixed(1)}K`;
  return String(n);
}
function ms(n: number) {
  if (n >= 60_000) return `${(n/60_000).toFixed(1)}m`;
  if (n >= 1_000)  return `${(n/1_000).toFixed(1)}s`;
  return `${n}ms`;
}

// ── 共用組件 ──────────────────────────────────────────────────────
function Trend({ t }: { t: MonitorTrend }) {
  const p = t.change_pct;
  if (p === null) return <span className="text-slate-600 text-[11px]">— 前期無資料</span>;
  const up = p >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up?'text-emerald-400':'text-red-400'}`}>
      {up ? <HiTrendingUp className="h-3 w-3"/> : <HiTrendingDown className="h-3 w-3"/>}
      {up?'+':''}{p}% vs 前期
    </span>
  );
}

function Stat({ label, value, sub, trend }: {
  label: string; value: string|number; sub?: string; trend?: MonitorTrend;
}) {
  return (
    <div className="flex flex-col gap-1 py-4 px-5 border-r border-slate-800 last:border-r-0">
      <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-2xl font-semibold text-slate-100 tabular-nums leading-tight">
        {typeof value==='number'?value.toLocaleString():value}
      </span>
      <div className="flex items-center gap-2 min-h-[16px]">
        {trend && <Trend t={trend}/>}
        {sub && <span className="text-[11px] text-slate-600">{sub}</span>}
      </div>
    </div>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-sm font-medium text-slate-300">{title}</span>
        {sub && <span className="text-xs text-slate-600">{sub}</span>}
      </div>
      {children}
    </div>
  );
}

function ServiceDot({ label, ok, extra }: { label: string; ok: boolean; extra?: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <span className={`h-1.5 w-1.5 rounded-full ${ok?'bg-emerald-500':'bg-red-500'}`}/>
      {label}
      {extra && <span className={ok?'text-slate-600':'text-red-400'}>{extra}</span>}
    </span>
  );
}

function LatencyGrid({ lat }: { lat: LLMLatency }) {
  const items = [
    { label: 'avg', value: lat.avg_ms },
    { label: 'P95', value: lat.p95_ms },
    { label: 'P99', value: lat.p99_ms },
    { label: 'min', value: lat.min_ms },
    { label: 'max', value: lat.max_ms },
  ];
  return (
    <div className="grid grid-cols-5 divide-x divide-slate-800 rounded-xl border border-slate-800 bg-slate-900">
      {items.map(i => (
        <div key={i.label} className="flex flex-col items-center py-3 gap-0.5">
          <span className="text-[11px] uppercase text-slate-500">{i.label}</span>
          <span className="text-lg font-semibold text-slate-100 tabular-nums">{ms(i.value)}</span>
        </div>
      ))}
    </div>
  );
}

// ── ECharts 圖表 ──────────────────────────────────────────────────
function TokenChart({ daily_trend, isHourly }: { daily_trend: MonitorStats['daily_trend']; isHourly: boolean }) {
  const xData = isHourly
    ? Array.from({length:24},(_,i)=>`${String(i).padStart(2,'0')}:00`)
    : daily_trend.map(r=>r.date??'');
  const inp = daily_trend.map(r=>r.input);
  const out = daily_trend.map(r=>r.output);
  const hasData = inp.some(v=>v>0)||out.some(v=>v>0);
  const opt = {
    backgroundColor:'transparent', grid:{left:54,right:16,top:12,bottom:36},
    legend:{data:['Input','Output'],bottom:0,textStyle:{color:'#94a3b8',fontSize:11}},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>p.map(x=>`${x.marker}${x.seriesName}: <b>${fmt(x.value)}</b>`).join('<br/>')},
    xAxis:{type:'category',data:xData,boundaryGap:false,...AX},
    yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
    series:[
      {name:'Input',type:'line',smooth:true,data:inp,symbol:'none',lineStyle:{color:'#6366f1',width:2},itemStyle:{color:'#6366f1'},
       areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(99,102,241,.25)'},{offset:1,color:'rgba(99,102,241,.02)'}]}}},
      {name:'Output',type:'line',smooth:true,data:out,symbol:'none',lineStyle:{color:'#0ea5e9',width:2},itemStyle:{color:'#0ea5e9'},
       areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(14,165,233,.2)'},{offset:1,color:'rgba(14,165,233,.02)'}]}}},
    ],
  };
  return hasData
    ? <ReactECharts option={opt} style={{height:180}}/>
    : <div className="flex h-28 items-center justify-center text-sm text-slate-600">對話後開始記錄</div>;
}

function LatencyTrendChart({ trend, isHourly }: { trend: {date?:string;hour?:number;avg_ms:number}[]; isHourly: boolean }) {
  if (!trend.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料（需有 llm_latency_ms &gt; 0 的對話）</div>;
  const xData = isHourly ? trend.map(r=>`${String(r.hour).padStart(2,'0')}:00`) : trend.map(r=>r.date??'');
  const data  = trend.map(r=>r.avg_ms);
  const opt = {
    backgroundColor:'transparent', grid:{left:54,right:16,top:12,bottom:36},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>`${p[0].axisValue} &nbsp;<b>${ms(p[0].value)}</b>`},
    xAxis:{type:'category',data:xData,boundaryGap:false,...AX},
    yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:(v:number)=>ms(v)}},
    series:[{type:'line',smooth:true,data,symbol:'none',lineStyle:{color:'#f59e0b',width:2},itemStyle:{color:'#f59e0b'},
      areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(245,158,11,.25)'},{offset:1,color:'rgba(245,158,11,.02)'}]}}}],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}

function PeakChart({ data }: { data: {hour:number;turns:number}[] }) {
  const mx = Math.max(...data.map(h=>h.turns),1);
  const opt = {
    backgroundColor:'transparent', grid:{left:28,right:8,top:8,bottom:36},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>`${String(p[0].name).padStart(2,'0')}:00 &nbsp;<b>${p[0].value} 輪</b>`},
    xAxis:{type:'category',data:data.map(h=>h.hour),...AX,axisLabel:{...AX.axisLabel,fontSize:10,formatter:(v:number)=>v%6===0?String(v).padStart(2,'0'):''}},
    yAxis:{type:'value',...AX,minInterval:1},
    series:[{type:'bar',barMaxWidth:16,data:data.map(h=>({value:h.turns,itemStyle:{color:`rgba(99,102,241,${Math.max(.12,h.turns/mx)})`,borderRadius:[2,2,0,0]}}))}],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}


function ActivityChart({ data }: { data:{date:string;sessions:number;turns:number}[] }) {
  if (!data.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  const opt = {
    backgroundColor:'transparent', grid:{left:28,right:8,top:8,bottom:52},
    legend:{data:['Sessions','Turns'],bottom:4,textStyle:{color:'#94a3b8',fontSize:11}},
    tooltip:{...TIP,trigger:'axis'},
    xAxis:{type:'category',data:data.map(r=>r.date),...AX},
    yAxis:{type:'value',...AX,minInterval:1},
    series:[
      {name:'Sessions',type:'bar',data:data.map(r=>r.sessions),barMaxWidth:16,itemStyle:{color:'#10b981',borderRadius:[2,2,0,0]}},
      {name:'Turns',   type:'bar',data:data.map(r=>r.turns),   barMaxWidth:16,itemStyle:{color:'#6366f1',borderRadius:[2,2,0,0]}},
    ],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}

// ── Tab 內容組件 ──────────────────────────────────────────────────

type PickerMode = 'preset'|'day'|'week'|'month';

interface TimeRangeState {
  mode: PickerMode;
  preset: '1d'|'7d'|'30d';
  dayVal: string;
  weekVal: string;
  monthVal: string;
}

interface TimeRangeProps {
  state: TimeRangeState;
  onChange: (s: TimeRangeState) => void;
  dateRange?: { start: string; end: string };
}

function TimeRangeSelector({ state, onChange, dateRange }: TimeRangeProps) {
  const { mode, preset, dayVal, weekVal, monthVal } = state;
  const set = (patch: Partial<TimeRangeState>) => onChange({ ...state, ...patch });
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
        {(['preset','day','week','month'] as PickerMode[]).map(m => (
          <button key={m} type="button" onClick={() => set({mode:m})}
            className={`px-3 py-1 rounded-md text-xs font-medium transition
              ${mode===m?'bg-indigo-700 text-white':'text-slate-500 hover:text-slate-300'}`}>
            {m==='preset'?'預設':m==='day'?'單日':m==='week'?'週':'月'}
          </button>
        ))}
      </div>
      {mode === 'preset' && (
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
          {(['1d','7d','30d'] as const).map(p => (
            <button key={p} type="button" onClick={() => set({preset:p})}
              className={`px-3 py-1 rounded-md text-xs font-medium transition
                ${preset===p?'bg-slate-700 text-slate-100':'text-slate-500 hover:text-slate-300'}`}>
              {p==='1d'?'今天':p==='7d'?'近 7 天':'近 30 天'}
            </button>
          ))}
        </div>
      )}
      {mode === 'day' && (
        <input type="date" value={dayVal} max={todayISO()}
          onChange={e => set({dayVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {mode === 'week' && (
        <input type="week" value={weekVal} onChange={e => set({weekVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {mode === 'month' && (
        <input type="month" value={monthVal} onChange={e => set({monthVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {dateRange && (
        <span className="text-[11px] text-slate-600">
          {dateRange.start===dateRange.end ? dateRange.start : `${dateRange.start} ~ ${dateRange.end}`}
        </span>
      )}
    </div>
  );
}

function OverviewTab({ stats, timeState, onTimeChange }: {
  stats: MonitorStats; timeState: TimeRangeState; onTimeChange: (s: TimeRangeState) => void;
}) {
  const isHourly = stats.date_range.start === stats.date_range.end;
  return (
    <div className="space-y-5">
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">全時期統計</p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-x divide-y md:divide-y-0 divide-slate-800">
          <Stat label="總用戶數"   value={stats.all_time.total_users}    sub="已註冊"/>
          <Stat label="總對話"     value={fmt(stats.all_time.total_sessions)} sub={`${fmt(stats.all_time.total_turns)} 輪`}/>
          <Stat label="即時在線"   value={stats.all_time.online_now}     sub="15 分鐘內"/>
          <Stat label="累計 Token" value={fmt(stats.all_time.total_input+stats.all_time.total_output)} sub="input + output"/>
          <Stat label="累計費用"   value={`$${stats.all_time.estimated_cost_usd.toFixed(4)}`} sub={stats.model_name}/>
          <Stat label="總 Input"   value={fmt(stats.all_time.total_input)} sub="tokens"/>
        </div>
        <p className="mt-1.5 text-[10px] text-slate-700">
          {stats.model_name} Global：Input $0.75 · Output $4.50 per 1M（以 Azure 帳單為準）
        </p>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between flex-wrap gap-2">
          <p className="text-[11px] uppercase tracking-wide text-slate-600">時段統計</p>
          <TimeRangeSelector state={timeState} onChange={onTimeChange} dateRange={stats.date_range}/>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-slate-800">
          <Stat label="活躍用戶" value={stats.period.active_users}
            sub={`新增 ${stats.period.new_users} 人`} trend={stats.trends.active_users}/>
          <Stat label="對話輪數" value={stats.period.turns}
            sub={`${stats.period.sessions} sessions`} trend={stats.trends.turns}/>
          <Stat label="Token 用量" value={fmt(stats.period.input_tokens+stats.period.output_tokens)}
            sub={`≈ $${stats.period.estimated_cost_usd.toFixed(4)}`} trend={stats.trends.tokens}/>
          <Stat label="平均深度" value={`${stats.period.avg_turns_per_session} 輪`} sub="每 session"/>
        </div>
      </div>

      <Section title="Token 用量趨勢" sub={isHourly?'今日（按小時）':'按日'}>
        <TokenChart daily_trend={stats.daily_trend} isHourly={isHourly}/>
      </Section>
    </div>
  );
}

const INPUT_PRICE  = 0.75 / 1_000_000;
const OUTPUT_PRICE = 4.50 / 1_000_000;

function DailyCostChart({ daily_trend, isHourly }: {
  daily_trend: MonitorStats['daily_trend']; isHourly: boolean;
}) {
  if (!daily_trend.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  const xData   = isHourly
    ? Array.from({length:24}, (_,i) => `${String(i).padStart(2,'0')}:00`)
    : daily_trend.map(r => r.date ?? '');
  const costs   = daily_trend.map(r =>
    +(r.input * INPUT_PRICE + r.output * OUTPUT_PRICE).toFixed(6)
  );
  const tokPerTurn = daily_trend.map(r =>
    r.turns > 0 ? +((r.input + r.output) / r.turns).toFixed(0) : 0
  );
  const hasCost = costs.some(v => v > 0);
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 60, right: 60, top: 12, bottom: 52 },
    legend: { data: ['估算費用 (USD)', '每輪 Token'], bottom: 4, textStyle: { color: '#94a3b8', fontSize: 11 } },
    tooltip: {
      ...TIP, trigger: 'axis',
      formatter: (p: TipParam[]) => p.map(x =>
        `${x.marker}${x.seriesName}: <b>${x.seriesIndex === 0 ? `$${x.value.toFixed(5)}` : fmt(x.value)}</b>`
      ).join('<br/>'),
    },
    xAxis: { type: 'category', data: xData, ...AX },
    yAxis: [
      { type: 'value', name: 'USD', nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { ...AX.axisLabel, formatter: (v: number) => `$${v.toFixed(4)}` },
        splitLine: AX.splitLine },
      { type: 'value', name: 'tok/輪', nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { ...AX.axisLabel, formatter: fmt }, splitLine: { show: false } },
    ],
    series: [
      { name: '估算費用 (USD)', type: 'bar', data: costs, yAxisIndex: 0, barMaxWidth: 18,
        itemStyle: { color: '#f59e0b', borderRadius: [2,2,0,0] } },
      { name: '每輪 Token', type: 'line', data: tokPerTurn, yAxisIndex: 1,
        smooth: true, symbol: 'none',
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' } },
    ],
  };
  return hasCost
    ? <ReactECharts option={opt} style={{ height: 200 }}/>
    : <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無 Token 記錄（對話後開始統計）</div>;
}

function AITab({ stats }: { stats: MonitorStats }) {
  const isHourly = stats.date_range.start === stats.date_range.end;
  const lat = stats.period.llm_latency;
  const { input_tokens, output_tokens } = stats.period;
  const ratio = output_tokens > 0 ? (input_tokens / output_tokens).toFixed(1) : '—';

  return (
    <div className="space-y-5">
      {/* Model 資訊 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-slate-500 mb-1">Model</p>
          <p className="text-lg font-semibold text-slate-200">{stats.model_name}</p>
          <p className="text-xs text-slate-600 mt-0.5">Azure OpenAI · Global 端點 · Input $0.75 / Output $4.50 per 1M tokens</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-slate-500 mb-1">Input / Output 比</p>
          <p className="text-lg font-semibold text-slate-200">{ratio} : 1</p>
          <p className="text-xs text-slate-600">每 1 個 output token 對應的 input tokens</p>
        </div>
      </div>

      {/* Model Latency */}
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">
          Model Latency（{lat ? `${lat.count} 次對話` : '無資料'}）
        </p>
        {lat
          ? <LatencyGrid lat={lat}/>
          : <div className="rounded-xl border border-slate-800 bg-slate-900 py-6 text-center text-sm text-slate-600">
              尚無 latency 資料（新對話後即開始記錄）
            </div>
        }
      </div>

      {/* Latency 趨勢 */}
      <Section title="Model Latency 趨勢" sub={isHourly?'今日（按小時）':'按日'}>
        <LatencyTrendChart trend={stats.period.llm_latency_trend} isHourly={isHourly}/>
      </Section>

      {/* Token + 費用 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Section title="Token 用量趨勢" sub={isHourly?'今日（按小時）':'按日'}>
          <TokenChart daily_trend={stats.daily_trend} isHourly={isHourly}/>
        </Section>
        <Section title="每日費用 & 每輪 Token" sub="黃柱：USD 費用（左軸）  紫線：每輪平均 Token（右軸）">
          <DailyCostChart daily_trend={stats.daily_trend} isHourly={isHourly}/>
        </Section>
      </div>
    </div>
  );
}

function fmtUptime(sec: number): string {
  if (sec < 60)   return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec/60)}m ${sec%60}s`;
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
  return `${h}h ${m}m`;
}

function InfraCard({ label, sub, badge, badgeColor, value, valueColor }: {
  label: string; sub: string; badge?: string; badgeColor?: string;
  value?: string; valueColor?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-300">{label}</span>
        {badge && (
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${badgeColor||'bg-emerald-900/50 text-emerald-400'}`}>
            {badge}
          </span>
        )}
      </div>
      {value && <p className="text-2xl font-semibold tabular-nums" style={{color:valueColor||'#e2e8f0'}}>{value}</p>}
      <p className="text-[11px] text-slate-600">{sub}</p>
    </div>
  );
}

function DatabaseTab({ dbStats, loading }: { dbStats: DBStats|null; loading: boolean }) {
  if (loading) return <div className="flex h-40 items-center justify-center text-slate-600 text-sm">載入中…</div>;
  if (!dbStats) return <div className="flex h-40 items-center justify-center text-slate-600 text-sm">載入失敗</div>;

  const { infra, postgres: pg, qdrant: qd, cloudinary: cl, cloudinary_error: clErr } = dbStats;
  const cacheColor = pg.cache_hit_pct >= 95 ? '#10b981' : pg.cache_hit_pct >= 80 ? '#f59e0b' : '#ef4444';

  return (
    <div className="space-y-5">

      {/* ── 基礎設施概覽 ── */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600">基礎設施概覽</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <InfraCard
            label="Render 後端" badge="運行中" badgeColor="bg-emerald-900/50 text-emerald-400"
            value={fmtUptime(infra.server_uptime_seconds)}
            sub="本次伺服器啟動時間（冷啟動後重置）"
          />
          <InfraCard
            label="Neon PostgreSQL" badge="正常" badgeColor="bg-sky-900/50 text-sky-400"
            value={pg.db_size}
            sub={`${infra.neon_region} (AWS) · Cache ${pg.cache_hit_pct}%`}
          />
          <InfraCard
            label="Qdrant Cloud" badge="正常" badgeColor="bg-violet-900/50 text-violet-400"
            value={infra.qdrant_total_points.toLocaleString()}
            sub={`${infra.qdrant_region} (AWS) · ${qd.collections.length} collections`}
          />
          {cl ? (
            <InfraCard
              label="Cloudinary" badge={cl.plan} badgeColor="bg-orange-900/50 text-orange-400"
              value={`${cl.total_resources} PDFs`}
              sub={`${cl.storage_pretty} 已用 · 本月 ${cl.bandwidth_pretty} 流量`}
            />
          ) : (
            <InfraCard
              label="Firebase Hosting" badge="CDN" badgeColor="bg-amber-900/50 text-amber-400"
              sub="靜態 CDN，無需監控"
            />
          )}
        </div>
        {cl && (
          <div className="mt-3">
            <InfraCard
              label="Firebase Hosting" badge="CDN" badgeColor="bg-amber-900/50 text-amber-400"
              sub="靜態前端 CDN，無需監控"
            />
          </div>
        )}
      </div>

      {/* ── PostgreSQL ── */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
          <HiDatabase className="h-3.5 w-3.5"/> PostgreSQL
          <span className="text-slate-700 normal-case">Neon · {infra.neon_region} (AWS)</span>
        </p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">DB 大小</p>
              <p className="text-xl font-semibold text-slate-200 mt-0.5">{pg.db_size}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">連線數</p>
              <p className="text-xl font-semibold text-slate-200 mt-0.5">{pg.connections}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">Cache Hit</p>
              <p className="text-xl font-semibold mt-0.5" style={{color:cacheColor}}>{pg.cache_hit_pct}%</p>
              <div className="mt-1 h-1.5 rounded-full bg-slate-800">
                <div className="h-full rounded-full" style={{width:`${Math.min(pg.cache_hit_pct,100)}%`,backgroundColor:cacheColor}}/>
              </div>
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/40">
                  <th className="text-left px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Table</th>
                  <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Rows</th>
                  <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Size</th>
                </tr>
              </thead>
              <tbody>
                {pg.tables.map(t => (
                  <tr key={t.name} className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30">
                    <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{t.name}</td>
                    <td className="px-4 py-2.5 text-right text-slate-300 tabular-nums">{t.rows.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-slate-500 text-xs">{t.size_pretty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── Qdrant ── */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
          <HiServer className="h-3.5 w-3.5"/> Qdrant Cloud
          <span className="text-slate-700 normal-case">{infra.qdrant_region} (AWS)</span>
        </p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          {qd.collections.length === 0
            ? <p className="text-sm text-slate-600">無法取得 Collection 資料</p>
            : <div className="rounded-lg border border-slate-800 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/40">
                      <th className="text-left px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Collection</th>
                      <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Points</th>
                      <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Segments</th>
                      <th className="text-center px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Optimizer</th>
                      <th className="text-center px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {qd.collections.map(c => (
                      <tr key={c.name} className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30">
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{c.name}</td>
                        <td className="px-4 py-2.5 text-right text-slate-200 tabular-nums font-medium">{c.points_count.toLocaleString()}</td>
                        <td className="px-4 py-2.5 text-right text-slate-500 tabular-nums text-xs">{c.segments_count}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`text-[11px] ${c.optimizer_ok?'text-slate-500':'text-amber-400'}`}>
                            {c.optimizer_ok ? '✓' : '最佳化中'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`inline-flex items-center gap-1 text-[11px] font-medium
                            ${c.status==='green'?'text-emerald-400':c.status==='yellow'?'text-amber-400':'text-slate-600'}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${c.status==='green'?'bg-emerald-500':c.status==='yellow'?'bg-amber-500':'bg-slate-600'}`}/>
                            {c.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
          }
        </div>
      </div>

      {/* ── Cloudinary ── */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600">Cloudinary（PDF 儲存）</p>
        {cl ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">PDF 總數</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.total_resources.toLocaleString()}</p>
              <p className="text-[11px] text-slate-600 mt-0.5">方案：{cl.plan}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">儲存用量</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.storage_pretty}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">本月流量</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.bandwidth_pretty}</p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-red-900/50 bg-red-950/30 px-5 py-4">
            <p className="text-sm text-red-400 mb-1">無法取得 Cloudinary 資料</p>
            {clErr && <p className="text-xs text-slate-500 font-mono break-all">{clErr}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function AllToolsBarChart({ tools }: { tools:{label:string;count:number}[] }) {
  if (!tools.length) return <div className="flex h-24 items-center justify-center text-sm text-slate-600">尚無紀錄</div>;
  const sorted = [...tools].sort((a,b) => b.count - a.count);
  const total  = sorted.reduce((s,t) => s + t.count, 0);
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 140, right: 60, top: 8, bottom: 16 },
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'none' },
      formatter: (p: TipParam[]) => `${p[0].name}<br/>${p[0].marker}<b>${p[0].value}</b> 次（${((p[0].value/total)*100).toFixed(1)}%）` },
    xAxis: { type: 'value', ...AX, axisLabel: { ...AX.axisLabel, fontSize: 10 } },
    yAxis: {
      type: 'category',
      data: sorted.map(t => t.label),
      axisLabel: { color: '#94a3b8', fontSize: 11, width: 128, overflow: 'truncate' },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    series: [{
      type: 'bar', data: sorted.map(t => t.count), barMaxWidth: 14,
      itemStyle: { color: '#6366f1', borderRadius: [0,3,3,0] },
      label: { show: true, position: 'right', color: '#94a3b8', fontSize: 10,
               formatter: (p: { value: number }) => `${p.value}` },
    }],
  };
  const chartHeight = Math.max(160, sorted.length * 28 + 30);
  return <ReactECharts option={opt} style={{ height: chartHeight }}/>;
}

function ActivityTab({ stats }: { stats: MonitorStats }) {
  const { active_users, new_users } = stats.period;
  const returning = Math.max(0, active_users - new_users);
  const newPct     = active_users > 0 ? Math.round(new_users / active_users * 100) : 0;
  const returnPct  = active_users > 0 ? Math.round(returning / active_users * 100) : 0;

  return (
    <div className="space-y-5">

      {/* 用戶概況 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-slate-800">
        <Stat label="時段活躍用戶" value={active_users} sub="有對話紀錄"/>
        <Stat label="新用戶" value={new_users} sub={`佔 ${newPct}%`}/>
        <Stat label="回訪用戶" value={returning} sub={`佔 ${returnPct}%`}/>
        <Stat label="平均對話深度" value={`${stats.period.avg_turns_per_session} 輪`} sub="每 session"/>
      </div>

      {/* 活動趨勢 */}
      <Section title="對話活動趨勢" sub="Sessions & Turns">
        <ActivityChart data={stats.activity_trend}/>
      </Section>

      {/* 工具使用全覽 */}
      <Section title="工具使用全覽" sub={`全部 ${stats.tools_usage.length} 種工具（時段內）`}>
        <AllToolsBarChart tools={stats.tools_usage}/>
      </Section>

      {/* 活躍時段 */}
      <Section title="活躍時段分布" sub="24 小時">
        <PeakChart data={stats.peak_hours}/>
      </Section>

    </div>
  );
}

// ── 主頁面 ────────────────────────────────────────────────────────
type TabId = 'overview'|'ai'|'database'|'activity';
const TABS: { id: TabId; label: string; icon: React.ComponentType<{className?:string}> }[] = [
  { id:'overview',  label:'總覽',    icon: HiChip },
  { id:'ai',        label:'AI 模型', icon: HiChip },
  { id:'database',  label:'資料庫',  icon: HiDatabase },
  { id:'activity',  label:'對話活動', icon: HiChatAlt2 },
];

export default function MonitorPage() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [timeState, setTimeState] = useState<TimeRangeState>({
    mode:'preset', preset:'7d', dayVal:todayISO(), weekVal:'', monthVal:'',
  });
  const [refreshSec, setRefreshSec]   = useState(60);
  const [countdown, setCountdown]     = useState(60);
  const [stats, setStats]             = useState<MonitorStats|null>(null);
  const [dbStats, setDbStats]         = useState<DBStats|null>(null);
  const [dbLoading, setDbLoading]     = useState(false);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string|null>(null);
  const [lastAt, setLastAt]           = useState<Date|null>(null);
  const seqRef   = useRef(0);
  const dbFetched = useRef(false);

  const fetchOpts = useMemo(() => {
    const { mode, preset, dayVal, weekVal, monthVal } = timeState;
    if (mode==='preset') return { preset };
    if (mode==='day'   && dayVal)   return { start:dayVal,    end:dayVal };
    if (mode==='week'  && weekVal)  { const r=weekToRange(weekVal);  return { start:r.start,end:r.end }; }
    if (mode==='month' && monthVal) { const r=monthToRange(monthVal);return { start:r.start,end:r.end }; }
    return { preset:'7d' as const };
  }, [timeState]);

  const fetchStats = useCallback(async (opts: typeof fetchOpts) => {
    const id = ++seqRef.current;
    setLoading(true); setError(null);
    try {
      const d = await monitorAPI.getStats(opts);
      if (seqRef.current===id) { setStats(d); setLastAt(new Date()); }
    } catch (e: unknown) {
      if (seqRef.current===id) setError(e instanceof Error ? e.message : '載入失敗');
    } finally {
      if (seqRef.current===id) setLoading(false);
    }
  }, []);

  // 認證 + 初始 fetch
  useEffect(() => {
    if (authLoading) return;
    if (!isDeveloper(user?.email)) { navigate('/'); return; }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchStats(fetchOpts);
  }, [user, authLoading, navigate, fetchStats, fetchOpts]);

  // auto-refresh
  useEffect(() => {
    const t = setInterval(() => {
      setCountdown(c => { if (c<=1) { fetchStats(fetchOpts); return refreshSec; } return c-1; });
    }, 1000);
    return () => clearInterval(t);
  }, [fetchOpts, refreshSec, fetchStats]);

  // DB stats：切到 database tab 時才 fetch
  useEffect(() => {
    if (activeTab==='database' && !dbFetched.current) {
      dbFetched.current = true;
      setDbLoading(true);
      monitorAPI.getDbStats()
        .then(setDbStats)
        .finally(() => setDbLoading(false));
    }
  }, [activeTab]);

  const doRefresh = () => {
    fetchStats(fetchOpts);
    setCountdown(refreshSec);
    if (activeTab==='database') {
      dbFetched.current = false;
      setDbLoading(true);
      monitorAPI.getDbStats().then(setDbStats).finally(()=>setDbLoading(false));
      dbFetched.current = true;
    }
  };

  if (authLoading) return null;

  const ok = stats
    ? stats.system_health.postgres==='ok' && stats.system_health.qdrant==='ok'
    : null;
  const chatLat = stats?.latency_stats.find(e=>e.endpoint==='/api/chat');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <div className="max-w-[1400px] mx-auto px-5 py-6 space-y-4">

        {/* ── 頁頭 ── */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-semibold text-slate-200">系統監控</h1>
            {ok!==null && (
              <span className={`flex items-center gap-1 text-xs ${ok?'text-emerald-500':'text-red-400'}`}>
                {ok ? <HiCheckCircle className="h-3.5 w-3.5"/> : <HiXCircle className="h-3.5 w-3.5"/>}
                {ok?'全部正常':'異常'}
              </span>
            )}
            {lastAt && !loading && (
              <span className="text-[11px] text-slate-600">
                {lastAt.toLocaleTimeString('zh-TW')} · {countdown}s 後更新
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
              {([30,60,300] as const).map(s => (
                <button key={s} type="button" onClick={() => { setRefreshSec(s); setCountdown(s); }}
                  className={`px-2.5 py-1 rounded-md text-xs transition ${refreshSec===s?'bg-slate-700 text-slate-100':'text-slate-500 hover:text-slate-300'}`}>
                  {s<60?`${s}s`:s===60?'1m':'5m'}
                </button>
              ))}
            </div>
            <button type="button" onClick={doRefresh}
              className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-slate-400 hover:text-slate-200 transition">
              <HiRefresh className={`h-4 w-4 ${loading?'animate-spin':''}`}/>
            </button>
          </div>
        </div>

        {/* ── 健康列 ── */}
        <div className="flex items-center gap-3 flex-wrap">
          {stats ? (
            <>
              <ServiceDot label="Render" ok/>
              <span className="text-slate-700">·</span>
              <ServiceDot label="PostgreSQL" ok={stats.system_health.postgres==='ok'}/>
              <span className="text-slate-700">·</span>
              <ServiceDot label="Qdrant" ok={stats.system_health.qdrant==='ok'}/>
              {chatLat && <>
                <span className="text-slate-700">·</span>
                <ServiceDot label="/api/chat" ok={chatLat.error_rate_pct<=5} extra={`${chatLat.avg_ms.toFixed(0)}ms avg`}/>
              </>}
            </>
          ) : <span className="text-[11px] text-slate-700">檢查中…</span>}
        </div>

        {/* ── 錯誤 ── */}
        {error && (
          <div className="rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            {error} — <button type="button" onClick={doRefresh} className="underline">重試</button>
          </div>
        )}

        {/* ── Tab bar ── */}
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5 w-fit">
          {TABS.map(t => (
            <button key={t.id} type="button" onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium transition
                ${activeTab===t.id?'bg-indigo-700 text-white':'text-slate-500 hover:text-slate-300'}`}>
              <t.icon className="h-3.5 w-3.5"/>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Tab content ── */}
        {stats && activeTab==='overview' && (
          <OverviewTab stats={stats} timeState={timeState} onTimeChange={setTimeState}/>
        )}
        {stats && activeTab==='ai' && <AITab stats={stats}/>}
        {activeTab==='database' && (
          <DatabaseTab dbStats={dbStats} loading={dbLoading}/>
        )}
        {stats && activeTab==='activity' && <ActivityTab stats={stats}/>}

      </div>
    </div>
  );
}
