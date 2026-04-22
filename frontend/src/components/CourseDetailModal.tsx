import { useEffect, useState } from 'react';
import { HiX, HiBookOpen, HiAcademicCap, HiUser, HiTag, HiClipboardList } from 'react-icons/hi';
import { apiClient } from '../api/client';
import type { CourseCard } from '../types';

interface CourseDetailModalProps {
  course: CourseCard | null;
  onClose: () => void;
}

interface CourseDetail {
  name:             string;
  dept:             string;
  credits:          number;
  type:             string;
  teacher:          string;
  code:             string;
  summary:          string;
  course_objective: string;
  course_content:   string;
  grading:          string;
  when_raw:         string;
  prereq_codes:     string;
  eligible_years:   string;
}

function Section({ title, content }: { title: string; content: string }) {
  if (!content) return null;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
        <HiClipboardList className="h-4 w-4 text-primary-600" />
        {title}
      </div>
      <p className="whitespace-pre-line text-sm leading-relaxed text-gray-600">{content}</p>
    </div>
  );
}

export default function CourseDetailModal({ course, onClose }: CourseDetailModalProps) {
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    if (!course) { setDetail(null); return; }
    setLoading(true);
    apiClient
      .post('/chat/course_detail', { name: course.name, code: course.code ?? '' })
      .then((r) => setDetail(r.data as CourseDetail))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [course?.name]);

  if (!course) return null;

  const d = detail ?? course;
  const typeColor =
    d.type === '必修'
      ? 'border-red-200 bg-red-50 text-red-700'
      : d.type
      ? 'border-green-200 bg-green-50 text-green-700'
      : '';

  const hasRichContent = !!(
    detail?.course_objective ||
    detail?.course_content ||
    detail?.grading
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      <div
        className="relative z-10 flex max-h-[80vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex-shrink-0 rounded-t-2xl bg-gradient-to-br from-primary-50 via-primary-100 to-primary-200 p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-lg font-bold leading-snug text-gray-900">{d.name}</h2>
              {d.dept && <p className="mt-1 text-sm text-gray-600">{d.dept}</p>}
            </div>
            <button
              onClick={onClose}
              className="flex-shrink-0 rounded-xl p-1.5 text-gray-500 transition hover:bg-white/60 hover:text-gray-900"
            >
              <HiX className="h-5 w-5" />
            </button>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {(d.credits ?? 0) > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-primary-200 bg-white/80 px-3 py-1 text-sm font-medium text-gray-700">
                <HiAcademicCap className="h-3.5 w-3.5" />
                {d.credits} 學分
              </span>
            )}
            {d.type && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm font-medium ${typeColor}`}>
                <HiTag className="h-3.5 w-3.5" />
                {d.type}
              </span>
            )}
            {d.teacher && (
              <span className="inline-flex items-center gap-1 rounded-full border border-primary-200 bg-white/80 px-3 py-1 text-sm font-medium text-gray-700">
                <HiUser className="h-3.5 w-3.5" />
                {d.teacher}
              </span>
            )}
          </div>
        </div>

        {/* body */}
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-primary-500" />
              <span className="ml-3 text-sm text-gray-400">載入課程資料中…</span>
            </div>
          ) : hasRichContent ? (
            <>
              <Section title="課程目標" content={detail!.course_objective} />
              <Section title="課程內容" content={detail!.course_content} />
              <Section title="評分方式" content={detail!.grading} />
              {detail!.when_raw && (
                <div className="text-xs text-gray-400">建議修習：{detail!.when_raw}</div>
              )}
              {detail!.prereq_codes && (
                <div className="text-xs text-gray-400">先修課號：{detail!.prereq_codes}</div>
              )}
            </>
          ) : (
            <div className="space-y-1.5">
              {d.summary ? (
                <>
                  <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                    <HiBookOpen className="h-4 w-4 text-primary-600" />
                    課程摘要
                  </div>
                  <p className="text-sm leading-relaxed text-gray-600">{d.summary}</p>
                </>
              ) : (
                <p className="text-sm text-gray-400">此課程暫無詳細摘要資料。</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
