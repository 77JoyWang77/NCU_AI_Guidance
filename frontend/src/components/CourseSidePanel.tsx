import { HiBookOpen, HiInformationCircle, HiViewList } from 'react-icons/hi';
import type { CourseCard } from '../types';

type DomainTag = { field: string; relevance: 'high' | 'medium' | 'low' };

function parseDomainTags(raw: string | undefined): DomainTag[] {
  if (!raw) return [];
  return raw.split('||').flatMap((part) => {
    const [field, relevance] = part.split('::');
    if (!field) return [];
    return [{ field: field.trim(), relevance: (relevance?.trim() || 'medium') as DomainTag['relevance'] }];
  });
}

const TAG_STYLES: Record<DomainTag['relevance'], string> = {
  high:   'bg-primary-100 text-primary-700 font-medium',
  medium: 'bg-gray-100 text-gray-600',
  low:    'bg-gray-50 text-gray-400',
};

interface CourseSidePanelProps {
  courses:       CourseCard[];
  poolCount:     number;
  hasLarge:      boolean;
  onCourseClick: (c: CourseCard) => void;
  onViewAll?:    () => void;
}

function SidePanelCard({
  course,
  onCourseClick,
}: {
  course: CourseCard;
  onCourseClick: (c: CourseCard) => void;
}) {
  const typeColor =
    course.type === '必修'
      ? 'text-red-600 bg-red-50 border-red-200'
      : course.type
      ? 'text-green-600 bg-green-50 border-green-200'
      : '';

  return (
    <button
      type="button"
      onClick={() => onCourseClick(course)}
      className="w-full rounded-xl border border-gray-200 bg-white p-3 text-left shadow-sm transition hover:border-primary-200 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-medium text-gray-800 hover:text-primary-700">{course.name}</div>
          <div className="mt-0.5 text-xs text-gray-500">
            {[course.dept, course.credits ? `${course.credits} 學分` : '']
              .filter(Boolean)
              .join(' · ')}
          </div>
          {course.teacher && (
            <div className="mt-0.5 text-xs text-gray-400">授課：{course.teacher}</div>
          )}
          {course.domain_tags && (() => {
            const tags = parseDomainTags(course.domain_tags)
              .filter(t => t.relevance === 'high' || t.relevance === 'medium')
              .slice(0, 3);
            return tags.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {tags.map((t, i) => (
                  <span key={i} className={`rounded-full px-2 py-0.5 text-[10px] leading-tight ${TAG_STYLES[t.relevance]}`}>
                    {t.field}
                  </span>
                ))}
              </div>
            ) : null;
          })()}
        </div>
        {course.type && (
          <span className={`flex-shrink-0 rounded-full border px-1.5 py-0.5 text-xs font-medium ${typeColor}`}>
            {course.type}
          </span>
        )}
      </div>
    </button>
  );
}

export default function CourseSidePanel({
  courses,
  poolCount,
  hasLarge,
  onCourseClick,
  onViewAll,
}: CourseSidePanelProps) {
  return (
    <div className="flex h-full flex-col">
      {/* 標題 */}
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

      {/* 大量結果提示 */}
      {hasLarge && poolCount > 0 && (
        <div className="flex flex-shrink-0 items-center gap-1.5 border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-500">
          <HiInformationCircle className="h-3.5 w-3.5 flex-shrink-0" />
          <span>共搜尋到 {poolCount} 門</span>
          {onViewAll && (
            <button
              type="button"
              onClick={onViewAll}
              className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-primary-600 transition hover:bg-primary-50"
            >
              <HiViewList className="h-3 w-3" />
              查看全部
            </button>
          )}
        </div>
      )}

      {/* 課程列表 */}
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

      {/* 查看全部按鈕（非 hasLarge 時） */}
      {!hasLarge && onViewAll && poolCount > courses.length && (
        <div className="flex-shrink-0 border-t border-gray-100 p-3">
          <button
            type="button"
            onClick={onViewAll}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-gray-200 py-2 text-xs text-gray-500 transition hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700"
          >
            <HiViewList className="h-3.5 w-3.5" />
            查看全部 {poolCount} 門課程
          </button>
        </div>
      )}
    </div>
  );
}
