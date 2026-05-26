import { HiBookOpen } from 'react-icons/hi';
import type { CourseCard } from '../types';

type DomainTag = { field: string; relevance: 'high' | 'medium' | 'low' };

function parseDomainTags(raw: string | undefined): DomainTag[] {
  if (!raw) return [];
  return raw.split('||').flatMap((part) => {
    const trimmed = part.trim();
    if (!trimmed) return [];
    if (trimmed.includes('::')) {
      const [field, rel] = trimmed.split('::');
      return [{ field: field.trim(), relevance: (rel?.trim() || 'medium') as DomainTag['relevance'] }];
    }
    return [{ field: trimmed, relevance: 'medium' as const }];
  });
}

const TAG_STYLES: Record<DomainTag['relevance'], string> = {
  high:   'bg-primary-100 text-primary-700 font-medium',
  medium: 'bg-slate-100 text-slate-500',
  low:    'bg-slate-50 text-slate-400',
};

interface CourseSidePanelProps {
  courses:       CourseCard[];
  onCourseClick: (c: CourseCard) => void;
}

function SidePanelCard({ course, onCourseClick }: { course: CourseCard; onCourseClick: (c: CourseCard) => void }) {
  const typeColor =
    course.type === '必修'
      ? 'text-red-600 bg-red-50 border-red-200'
      : course.type
      ? 'text-green-600 bg-green-50 border-green-200'
      : '';

  const tags = parseDomainTags(course.domain_tags)
    .filter(t => t.relevance === 'high' || t.relevance === 'medium')
    .slice(0, 3);

  return (
    <button
      type="button"
      onClick={() => onCourseClick(course)}
      className="w-full rounded-xl border border-gray-200 bg-white p-2.5 text-left shadow-sm transition hover:border-primary-200 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium leading-snug text-gray-800 hover:text-primary-700">
            {course.name}
          </div>
          <div className="mt-0.5 text-[11px] text-gray-400">
            {[course.dept, course.credits ? `${course.credits} 學分` : '']
              .filter(Boolean)
              .join(' · ')}
          </div>
          {tags.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {tags.map((t, i) => (
                <span key={i} className={`rounded-full px-1.5 py-px text-[10px] leading-tight ${TAG_STYLES[t.relevance]}`}>
                  {t.field}
                </span>
              ))}
            </div>
          )}
        </div>
        {course.type && (
          <span className={`flex-shrink-0 rounded-full border px-1.5 py-px text-[10px] font-medium ${typeColor}`}>
            {course.type}
          </span>
        )}
      </div>
    </button>
  );
}

export default function CourseSidePanel({ courses, onCourseClick }: CourseSidePanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <HiBookOpen className="h-4 w-4 text-primary-600" />
          <span className="text-sm font-semibold text-gray-800">推薦課程</span>
        </div>
        {courses.length > 0 && (
          <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700">
            {courses.length}
          </span>
        )}
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {courses.length === 0 ? (
          <div className="mt-8 flex flex-col items-center gap-3 text-center">
            <HiBookOpen className="h-10 w-10 text-gray-200" />
            <p className="text-xs leading-relaxed text-gray-400">
              問問我課程相關問題，<br />推薦課程會出現在這裡！
            </p>
          </div>
        ) : (
          courses.map((c, i) => (
            <SidePanelCard
              key={c.code || `${c.name}-${i}`}
              course={c}
              onCourseClick={onCourseClick}
            />
          ))
        )}
      </div>
    </div>
  );
}
