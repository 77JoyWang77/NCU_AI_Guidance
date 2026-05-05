import { useEffect, useState } from 'react';
import {
  HiX,
  HiLightBulb, HiBookOpen, HiClipboardList, HiShieldCheck, HiTag,
} from 'react-icons/hi';
import { apiClient } from '../api/client';
import type { CourseCard } from '../types';

interface SimplifiedConcept {
  original: string;
  display:  string;
}

interface DomainTag {
  field:     string;
  relevance: 'high' | 'medium' | 'low';
}

interface SectionInfo {
  section:          string;
  teacher:          string;
  dept:             string;
  college:          string;
  type:             string;
  eligibility_text: string;
}

interface WhenEntry {
  dept_id:   string;
  dept_name: string;
  when:      string;
}

interface CourseDetail {
  name:                string;
  name_en:             string;
  dept:                string;
  college:             string;
  credits:             number;
  type:                string;
  teacher:             string;
  code:                string;
  is_grad:             boolean;
  course_objective:    string;
  course_content:      string;
  textbook:            string;
  when_schedule:       WhenEntry[];
  prereq_codes:        string;
  coreq_codes:         string;
  // 分發條件：單班為字串，多班為空（看 sections）
  eligibility_text:    string;
  sections:            SectionInfo[];
  // NLP（全部 list）
  concepts:            string[];
  languages:           string[];
  tools:               string[];
  topic_tags:          string[];
  core_questions:      string[];
  simplified_concepts: SimplifiedConcept[];
  domain_tags:         DomainTag[];
}

interface Props {
  course:  CourseCard | null;
  onClose: () => void;
}

interface EligibilityRule {
  priority: number | null;
  text:     string;
}

function groupWhenSchedule(schedule: WhenEntry[]): { when: string; depts: string[] }[] {
  const map = new Map<string, string[]>();
  for (const e of schedule) {
    const label = e.dept_name.replace(/_/g, '·');
    if (!map.has(e.when)) map.set(e.when, []);
    map.get(e.when)!.push(label);
  }
  return Array.from(map.entries()).map(([when, depts]) => ({ when, depts }));
}

function parseEligibilityRules(raw: string): EligibilityRule[] {
  const normalized = raw.replace(/\r\n/g, '\n').replace(/[ \t]+/g, ' ').trim();
  if (!normalized) return [];
  const chunks = normalized
    .split(/\n+/)
    .flatMap(line => line.split(/\s*\|\s*/))
    .map(l => l.trim())
    .filter(Boolean);
  return chunks.map((chunk, i) => {
    const m = chunk.match(/^(?:P\s*)?(\d+)\s*[:：]?\s*(.*)$/i);
    return m
      ? { priority: Number(m[1]), text: (m[2] || '').trim() }
      : { priority: i + 1, text: chunk };
  });
}

function ExpandableSection({
  icon, title, children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(p => !p)}
        className="flex w-full items-center justify-between py-2 text-left group"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-600 group-hover:text-gray-900 transition-colors">
          {icon}
          {title}
        </span>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
          open
            ? 'bg-primary-100 text-primary-600'
            : 'bg-gray-100 text-gray-400 group-hover:bg-primary-50 group-hover:text-primary-500'
        }`}>
          {open ? '收合' : '展開'}
        </span>
      </button>
      {open && (
        <div className="ml-1 border-l-2 border-primary-100 pl-4 pt-2 pb-1">
          {children}
        </div>
      )}
    </div>
  );
}

const TAG_STYLES: Record<DomainTag['relevance'], string> = {
  high:   'bg-primary-100 text-primary-700 font-semibold ring-1 ring-primary-200',
  medium: 'bg-gray-100 text-gray-600',
  low:    'bg-gray-50 text-gray-400',
};

export default function CourseDetailModal({ course, onClose }: Props) {
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [onClose]);

  useEffect(() => {
    if (!course) { setDetail(null); return; }
    setLoading(true);
    apiClient
      .post('/chat/course_detail', { name: course.name, code: course.code ?? '' })
      .then(r => setDetail(r.data as CourseDetail))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [course?.name, course?.code]);

  if (!course) return null;
  const d = detail;

  const displayDept    = d?.dept    || course.dept    || '';
  const displayTeacher = d?.teacher || course.teacher || '';
  const displayCredits = d?.credits ?? course.credits ?? 0;
  const displayType    = d?.type    || course.type    || '';
  const courseCode     = (d?.code   || course.code    || '').trim();
  const typeIsRequired = displayType === '必修';

  const hasMultiSections = (d?.sections?.length ?? 0) > 0;

  // 單班分發條件
  const singleEligRules = d?.eligibility_text
    ? parseEligibilityRules(d.eligibility_text)
    : [];

  const techs = [...(d?.languages ?? []), ...(d?.tools ?? [])];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />

      <div
        className="relative z-10 flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex-shrink-0 border-b border-gray-100 px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-bold leading-snug text-gray-900">{course.name}</h2>
              {d?.name_en && (
                <p className="mt-0.5 text-xs text-gray-400">{d.name_en}</p>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {courseCode && (
                  <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-600">
                    {courseCode}
                  </span>
                )}
                {displayDept && (
                  <>
                    {courseCode && <span className="text-gray-200">·</span>}
                    <span className="text-xs text-gray-400">{displayDept}</span>
                  </>
                )}
                {displayCredits > 0 && (
                  <>
                    <span className="text-gray-200">·</span>
                    <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-600">
                      {displayCredits} 學分
                    </span>
                  </>
                )}
                {displayType && (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    typeIsRequired ? 'bg-red-50 text-red-500' : 'bg-emerald-50 text-emerald-600'
                  }`}>
                    {displayType}
                  </span>
                )}
                {d?.is_grad && (
                  <span className="rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-600">
                    研究所
                  </span>
                )}
                {!hasMultiSections && displayTeacher && (
                  <>
                    <span className="text-gray-200">·</span>
                    <span className="text-xs text-gray-400">{displayTeacher}</span>
                  </>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="flex-shrink-0 rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            >
              <HiX className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-primary-500" />
              <span className="ml-3 text-sm text-gray-400">載入中…</span>
            </div>
          ) : !d ? (
            <p className="text-sm text-gray-400">暫無詳細資料。</p>
          ) : (
            <>
              {/* ── 修習資訊卡 ── */}
              {(singleEligRules.length > 0 || d.when_schedule?.length > 0 || d.prereq_codes || hasMultiSections) && (
                <div className="flex items-start gap-2.5 rounded-xl bg-primary-50 px-3.5 py-3">
                  <HiShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary-400" />
                  <div className="min-w-0 w-full space-y-1.5">

                    {/* 單班：分發條件 */}
                    {!hasMultiSections && singleEligRules.length > 0 && (
                      <ul className="space-y-1.5">
                        {singleEligRules.map((rule, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="mt-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary-100 px-1 text-[10px] font-semibold text-primary-700">
                              {rule.priority ?? i + 1}
                            </span>
                            <p className="whitespace-pre-line text-xs leading-relaxed text-primary-900">{rule.text}</p>
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* 多班：各班別條件 */}
                    {hasMultiSections && (
                      <div className="space-y-2">
                        <p className="text-xs font-semibold text-primary-700">
                          此課程共 {d.sections.length} 個班別，各班分發條件不同：
                        </p>
                        {d.sections.map((sec, i) => (
                          <div key={i} className="rounded-lg bg-white/70 px-3 py-2">
                            <div className="flex flex-wrap items-center gap-1.5 mb-1">
                              {sec.section && (
                                <span className="rounded bg-primary-100 px-1.5 py-0.5 text-[10px] font-bold text-primary-700">
                                  {sec.section} 班
                                </span>
                              )}
                              {sec.dept && <span className="text-xs text-gray-500">{sec.dept}</span>}
                              {sec.teacher && <span className="text-xs text-gray-400">· {sec.teacher}</span>}
                            </div>
                            {sec.eligibility_text ? (
                              <ul className="space-y-1">
                                {parseEligibilityRules(sec.eligibility_text).map((rule, j) => (
                                  <li key={j} className="flex items-start gap-2">
                                    <span className="mt-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary-100 px-1 text-[10px] font-semibold text-primary-700">
                                      {rule.priority ?? j + 1}
                                    </span>
                                    <p className="whitespace-pre-line text-xs leading-relaxed text-primary-900">{rule.text}</p>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-xs text-gray-400">不限修課條件</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {d.when_schedule?.length > 0 && (
                      <div className="space-y-1">
                        <span className="text-xs font-medium text-gray-500">建議修習</span>
                        {groupWhenSchedule(d.when_schedule).map(({ when, depts }) => (
                          <div key={when} className="flex flex-wrap items-center gap-1">
                            <span className="text-xs font-semibold text-primary-700">{when}</span>
                            {depts.map((dept, i) => (
                              <span key={i} className="rounded bg-primary-50 px-1.5 py-0.5 text-[11px] text-primary-600">
                                {dept}
                              </span>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                    {d.prereq_codes && (
                      <p className="text-xs text-primary-600">先修：{d.prereq_codes}</p>
                    )}
                    {d.coreq_codes && (
                      <p className="text-xs text-primary-600">同修：{d.coreq_codes}</p>
                    )}
                  </div>
                </div>
              )}

              {/* ── 主題標籤 ── */}
              {d.topic_tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {d.topic_tags.map((t, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-600">
                      <HiTag className="h-3 w-3" />
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* ── 核心議題 ── */}
              {d.core_questions.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">核心議題</p>
                  <ul className="space-y-2">
                    {d.core_questions.map((q, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-gray-700">
                        <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-violet-400" />
                        {q}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── 概念白話說明 ── */}
              {d.simplified_concepts.length > 0 && (
                <div className="space-y-2">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    <HiLightBulb className="h-3.5 w-3.5 text-amber-400" />
                    概念說明
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {d.simplified_concepts.map((c, i) => (
                      <div key={i} className="flex gap-2.5 rounded-xl border border-gray-100 bg-white px-3 py-2.5 shadow-sm">
                        <div className="mt-0.5 w-0.5 flex-shrink-0 rounded-full bg-primary-300" />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-800">{c.original}</p>
                          <p className="mt-0.5 text-xs leading-relaxed text-gray-400">{c.display}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── 技術工具 ── */}
              {techs.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">技術工具</p>
                  <div className="flex flex-wrap gap-1.5">
                    {techs.map((t, i) => (
                      <span key={i} className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600 ring-1 ring-indigo-100">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* ── 領域標籤 ── */}
              {d.domain_tags.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">領域標籤</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.domain_tags.map((t, i) => (
                      <span key={i} className={`rounded-full px-2.5 py-0.5 text-xs ${TAG_STYLES[t.relevance]}`}>
                        {t.field}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* ── 概念 fallback（無白話說明時） ── */}
              {d.concepts.length > 0 && d.simplified_concepts.length === 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {d.concepts.map((c, i) => (
                    <span key={i} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-600">
                      {c}
                    </span>
                  ))}
                </div>
              )}

              {/* ── 課程目標 ── */}
              {d.course_objective && (
                <ExpandableSection
                  icon={<HiBookOpen className="h-4 w-4 text-primary-400" />}
                  title="課程目標"
                >
                  <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">
                    {d.course_objective}
                  </p>
                </ExpandableSection>
              )}

              {/* ── 授課內容 ── */}
              {d.course_content && (
                <ExpandableSection
                  icon={<HiClipboardList className="h-4 w-4 text-primary-400" />}
                  title="授課內容"
                >
                  <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">
                    {d.course_content}
                  </p>
                </ExpandableSection>
              )}

              {/* ── 教科書 ── */}
              {d.textbook && (
                <ExpandableSection
                  icon={<HiBookOpen className="h-4 w-4 text-gray-300" />}
                  title="教科書 / 參考書"
                >
                  <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">
                    {d.textbook}
                  </p>
                </ExpandableSection>
              )}

              {!d.course_objective && !d.course_content
                && d.simplified_concepts.length === 0
                && d.topic_tags.length === 0 && (
                <p className="text-sm text-gray-400">此課程暫無詳細資料。</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
