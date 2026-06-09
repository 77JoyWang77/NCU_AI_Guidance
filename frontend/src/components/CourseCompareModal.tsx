import type { ReactNode } from 'react';
import { HiTrash, HiX } from 'react-icons/hi';
import type { Course } from '../types';

interface CourseCompareModalProps {
  courses: Course[];
  onClose: () => void;
  onRemove: (course: Course) => void;
  onClear: () => void;
}

const splitFields = (value?: string | null) =>
  (value ?? '')
    .split(/[、,;；／/]/)
    .map((item) => item.trim())
    .filter(Boolean);

const uniqueItems = (items?: string[]) =>
  Array.from(new Set((items ?? []).map((item) => item.trim()).filter(Boolean)));

const shortText = (value?: string | null, limit = 260) => {
  const text = (value ?? '').replace(/\s+/g, ' ').trim();
  if (!text) return '未提供';
  return text.length > limit ? `${text.slice(0, limit).trim()}...` : text;
};

const listText = (items: string[]) => (items.length > 0 ? items.join('、') : '未提供');

const courseKey = (course: Course) => `${course.serial_no}-${course.course_id}`;

const rows: Array<{ label: string; render: (course: Course) => ReactNode; tall?: boolean }> = [
  { label: '開課系所', render: (course) => course.department || '未提供' },
  { label: '授課教師', render: (course) => course.instructor || '未提供' },
  { label: '學分', render: (course) => `${course.credits} 學分` },
  { label: '修別', render: (course) => course.required_elective || '未提供' },
  { label: '學期', render: (course) => course.semester_display || '未提供' },
  { label: '學制', render: (course) => course.course_system || '未提供' },
  { label: '課程領域', render: (course) => listText(splitFields(course.course_field)) },
  {
    label: '知識標籤',
    render: (course) => listText(uniqueItems([...(course.concepts ?? []), ...(course.topic_tags ?? []), ...(course.domain_tags ?? [])]).slice(0, 12)),
    tall: true,
  },
  {
    label: '工具與語言',
    render: (course) => listText(uniqueItems([...(course.tools ?? []), ...(course.languages ?? [])]).slice(0, 12)),
    tall: true,
  },
  { label: '修課資格', render: (course) => shortText(course.eligibility_summary, 220), tall: true },
  { label: '課程目標', render: (course) => shortText(course.course_objective), tall: true },
  { label: '課程內容', render: (course) => shortText(course.course_content), tall: true },
  { label: '教材與參考書', render: (course) => shortText(course.textbooks, 220), tall: true },
  { label: '備註', render: (course) => shortText(course.note, 180), tall: true },
];

export default function CourseCompareModal({ courses, onClose, onRemove, onClear }: CourseCompareModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="flex w-full max-w-6xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl" style={{ maxHeight: 'calc(94dvh - env(safe-area-inset-bottom))' }} onClick={(event) => event.stopPropagation()}>
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-950">課程對比</h2>
            <p className="mt-1 text-sm text-slate-500">並排比較課程基本資訊、內容、標籤與修課資格。</p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClear} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
              <HiTrash className="h-4 w-4" />
              清空
            </button>
            <button type="button" onClick={onClose} className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200" aria-label="關閉課程對比">
              <HiX className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto overscroll-contain p-4">

          {/* 手機版：欄位卡片佈局，課程並排在同一列 */}
          <div className="space-y-3 sm:hidden">
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${courses.length}, minmax(0, 1fr))` }}>
              {courses.map((course) => (
                <div key={courseKey(course)} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <div className="text-sm font-bold leading-snug text-slate-950 break-words">{course.course_name_zh || '未命名課程'}</div>
                      <div className="mt-0.5 text-[11px] text-slate-500 break-all">{course.course_name_en || course.course_id}</div>
                    </div>
                    <button type="button" onClick={() => onRemove(course)} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-slate-400 transition hover:bg-red-50 hover:text-red-600" aria-label={`移除 ${course.course_name_zh}`}>
                      <HiX className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {rows.map((row) => (
              <div key={row.label} className="rounded-xl border border-slate-100 bg-white">
                <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-500">{row.label}</div>
                <div className="grid divide-x divide-slate-100" style={{ gridTemplateColumns: `repeat(${courses.length}, minmax(0, 1fr))` }}>
                  {courses.map((course) => (
                    <div key={`${courseKey(course)}-${row.label}`} className="p-3 text-sm leading-6 text-slate-700 break-words">
                      {row.render(course)}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* 桌機版：原有 table 佈局 */}
          <table className="hidden w-full min-w-[820px] border-separate border-spacing-0 text-left text-sm sm:table">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-20 w-32 border-b border-slate-200 bg-white p-3 text-xs font-semibold text-slate-500">比較項目</th>
                {courses.map((course) => (
                  <th key={courseKey(course)} className="sticky top-0 z-10 min-w-[220px] border-b border-slate-200 bg-white p-3 align-top">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-base font-bold leading-snug text-slate-950">{course.course_name_zh || '未命名課程'}</div>
                        <div className="mt-1 text-xs font-medium text-slate-500">{course.course_name_en || course.course_id}</div>
                      </div>
                      <button type="button" onClick={() => onRemove(course)} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition hover:bg-red-50 hover:text-red-600" aria-label={`移除 ${course.course_name_zh}`}>
                        <HiX className="h-4 w-4" />
                      </button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th className="sticky left-0 z-10 border-b border-slate-100 bg-slate-50 p-3 align-top text-xs font-semibold text-slate-600">{row.label}</th>
                  {courses.map((course) => (
                    <td key={`${courseKey(course)}-${row.label}`} className={`border-b border-slate-100 p-3 align-top leading-6 text-slate-700 ${row.tall ? 'max-w-[280px]' : ''}`}>
                      {row.render(course)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
