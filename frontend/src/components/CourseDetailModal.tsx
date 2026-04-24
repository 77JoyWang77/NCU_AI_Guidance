import { useEffect, useState } from 'react';
import {
  HiX, HiChevronDown, HiChevronUp,
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

interface CourseDetail {
  name:                string;
  dept:                string;
  credits:             number;
  type:                string;
  teacher:             string;
  code:                string;
  course_objective:    string;
  course_content:      string;
  concepts:            string;
  languages:           string;
  tools:               string;
  topic_tags:          string;
  core_questions:      string;
  simplified_concepts: SimplifiedConcept[];
  domain_tags?:        DomainTag[];
  eligibility_raw:     string;
  when_raw:            string;
  prereq_codes:        string;
}

interface Props {
  course:  CourseCard | null;
  onClose: () => void;
}

interface EligibilityRule {
  priority: number | null;
  text: string;
}

const normalizeEligibilityText = (value: string) =>
  value
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .trim();

const parseEligibilityRules = (raw: string): EligibilityRule[] => {
  const normalized = normalizeEligibilityText(raw);
  if (!normalized) return [];

  const chunks = normalized
    .split(/\n+/)
    .flatMap((line) => line.split(/\s*\|\s*/))
    .map((line) => line.trim())
    .filter(Boolean);

  return chunks.map((chunk, index) => {
    const matched = chunk.match(/^(?:P\s*)?(\d+)\s*[:：]?\s*(.*)$/i);
    if (matched) {
      return {
        priority: Number(matched[1]),
        text: (matched[2] || '').trim(),
      };
    }

    return {
      priority: index + 1,
      text: chunk,
    };
  });
};

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
  }, [course?.name]);

  if (!course) return null;
  const d = detail;
  const typeIsRequired = (d?.type ?? course.type) === '必修';
  const courseCode = (d?.code ?? course.code ?? '').trim();
  const eligibilityRules = d?.eligibility_raw ? parseEligibilityRules(d.eligibility_raw) : [];

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
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {courseCode && (
                  <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-600">
                    課號：{courseCode}
                  </span>
                )}
                {(d?.dept ?? course.dept) && (
                  <>
                    {courseCode && <span className="text-gray-200">·</span>}
                  <span className="text-xs text-gray-400">{d?.dept ?? course.dept}</span>
                  </>
                )}
                {(d?.credits ?? course.credits ?? 0) > 0 && (
                  <>
                    <span className="text-gray-200">·</span>
                    <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-600">
                      {d?.credits ?? course.credits} 學分
                    </span>
                  </>
                )}
                {(d?.type ?? course.type) && (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    typeIsRequired ? 'bg-red-50 text-red-500' : 'bg-emerald-50 text-emerald-600'
                  }`}>
                    {d?.type ?? course.type}
                  </span>
                )}
                {(d?.teacher ?? course.teacher) && (
                  <>
                    <span className="text-gray-200">·</span>
                    <span className="text-xs text-gray-400">{d?.teacher ?? course.teacher}</span>
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
              {/* 修課資格 */}
              {(d.eligibility_raw || d.when_raw || d.prereq_codes) && (
                <div className="flex items-start gap-2.5 rounded-xl bg-primary-50 px-3.5 py-3 text-primary-800">
                  <HiShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary-400" />
                  <div className="space-y-1 min-w-0">
                    {eligibilityRules.length > 0 && (
                      <ul className="space-y-1.5">
                        {eligibilityRules.map((rule, i) => (
                          <li key={`${rule.priority ?? i}-${rule.text}`} className="flex items-start gap-2">
                            <span className="mt-0.5 inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-primary-100 px-1 text-[10px] font-semibold leading-none text-primary-700">
                              {rule.priority ?? i + 1}
                            </span>
                            <p className="whitespace-pre-line text-xs leading-relaxed text-primary-900">{rule.text}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                    {d.when_raw     && <p className="text-xs text-primary-500">建議修習：{d.when_raw}</p>}
                    {d.prereq_codes && <p className="text-xs text-primary-500">先修：{d.prereq_codes}</p>}
                  </div>
                </div>
              )}

              {/* 主題標籤（通識課） */}
              {d.topic_tags && (
                <div className="flex flex-wrap gap-1.5">
                  {d.topic_tags.split(/[,，]/).filter(Boolean).map((t, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-600">
                      <HiTag className="h-3 w-3" />
                      {t.trim()}
                    </span>
                  ))}
                </div>
              )}

              {/* 核心議題（通識課） */}
              {d.core_questions && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">核心議題</p>
                  <ul className="space-y-2">
                    {d.core_questions.split(' | ').map((q, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-gray-700">
                        <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-violet-400" />
                        {q}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 概念說明 */}
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

              {/* 程式語言 / 技術工具 */}
              {(d.languages || d.tools) && (() => {
                const techs = [
                  ...d.languages.split(/[,，]/).filter(Boolean),
                  ...d.tools.split(/[,，]/).filter(Boolean),
                ];
                return (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">技術工具</p>
                    <div className="flex flex-wrap gap-1.5">
                      {techs.map((t, i) => (
                        <span key={i} className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600 ring-1 ring-indigo-100">
                          {t.trim()}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* 領域標籤 */}
              {d.domain_tags?.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">領域標籤</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.domain_tags.map((t, i) => {
                      const cls =
                        t.relevance === 'high'
                          ? 'bg-primary-100 text-primary-700 font-semibold ring-1 ring-primary-200'
                          : t.relevance === 'medium'
                          ? 'bg-gray-100 text-gray-600'
                          : 'bg-gray-50 text-gray-400';
                      return (
                        <span key={i} className={`rounded-full px-2.5 py-0.5 text-xs ${cls}`}>
                          {t.field}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 技術概念 fallback */}
              {d.concepts && !d.simplified_concepts.length && (
                <div className="flex flex-wrap gap-1.5">
                  {d.concepts.split(/[,，]/).filter(Boolean).map((c, i) => (
                    <span key={i} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-600">
                      {c.trim()}
                    </span>
                  ))}
                </div>
              )}

              {/* 課程目標（展開） */}
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

              {/* 授課內容（展開） */}
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

              {!d.course_objective && !d.course_content && !d.simplified_concepts.length && !d.topic_tags && (
                <p className="text-sm text-gray-400">此課程暫無詳細資料。</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
