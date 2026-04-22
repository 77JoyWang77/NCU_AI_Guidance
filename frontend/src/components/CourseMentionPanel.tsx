import { useState } from 'react';
import { HiChevronDown, HiChevronUp, HiInformationCircle, HiViewList } from 'react-icons/hi';
import type { CourseCard } from '../types';

interface CourseMentionPanelProps {
  courseCards:     CourseCard[];
  coursePoolCount: number;
  hasLargeResult:  boolean;
  onCourseClick?:  (course: CourseCard) => void;
  onViewAll?:      () => void;
}

function CourseCardItem({
  course,
  onCourseClick,
}: {
  course: CourseCard;
  onCourseClick?: (c: CourseCard) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const typeColor =
    course.type === '必修'
      ? 'text-red-600 bg-red-50 border-red-200'
      : course.type
      ? 'text-green-600 bg-green-50 border-green-200'
      : '';

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start gap-2 p-3">
        <button
          type="button"
          onClick={() => onCourseClick?.(course)}
          className="min-w-0 flex-1 text-left"
        >
          <div className="font-medium text-gray-800 hover:text-primary-700">{course.name}</div>
          <div className="mt-0.5 text-sm text-gray-500">
            {[course.dept, course.credits ? `${course.credits} 學分` : '']
              .filter(Boolean)
              .join(' · ')}
          </div>
          {course.teacher && (
            <div className="mt-0.5 text-xs text-gray-400">授課：{course.teacher}</div>
          )}
        </button>
        <div className="flex flex-shrink-0 items-start gap-1.5 pt-0.5">
          {course.type && (
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${typeColor}`}>
              {course.type}
            </span>
          )}
          {course.summary && (
            <button
              type="button"
              onClick={() => setExpanded((p) => !p)}
              className="text-gray-400 hover:text-gray-600"
            >
              {expanded
                ? <HiChevronUp className="h-4 w-4" />
                : <HiChevronDown className="h-4 w-4" />}
            </button>
          )}
        </div>
      </div>
      {expanded && course.summary && (
        <div className="border-t border-gray-100 px-3 pb-3 pt-2 text-sm leading-relaxed text-gray-600">
          {course.summary}
        </div>
      )}
    </div>
  );
}

export default function CourseMentionPanel({
  courseCards,
  coursePoolCount,
  hasLargeResult,
  onCourseClick,
  onViewAll,
}: CourseMentionPanelProps) {
  if (courseCards.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {hasLargeResult && (
        <div className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
          <HiInformationCircle className="h-4 w-4 flex-shrink-0" />
          共搜尋到 {coursePoolCount} 門課程，以下僅顯示回答中提到的相關課程
          {onViewAll && (
            <button
              type="button"
              onClick={onViewAll}
              className="ml-auto flex items-center gap-1 rounded-lg px-2 py-0.5 text-primary-600 transition hover:bg-primary-50"
            >
              <HiViewList className="h-3.5 w-3.5" />
              查看全部
            </button>
          )}
        </div>
      )}

      <div className="space-y-2">
        {courseCards.map((course, i) => (
          <CourseCardItem
            key={course.code || `${course.name}-${i}`}
            course={course}
            onCourseClick={onCourseClick}
          />
        ))}
      </div>

      {!hasLargeResult && onViewAll && coursePoolCount > courseCards.length && (
        <button
          type="button"
          onClick={onViewAll}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-gray-200 py-2 text-sm text-gray-500 transition hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700"
        >
          <HiViewList className="h-4 w-4" />
          查看全部 {coursePoolCount} 門課程
        </button>
      )}
    </div>
  );
}
