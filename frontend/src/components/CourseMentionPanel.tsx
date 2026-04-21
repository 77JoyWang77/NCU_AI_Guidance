import { useState } from 'react';
import { HiChevronDown, HiChevronUp, HiInformationCircle } from 'react-icons/hi';
import type { CourseCard } from '../types';

interface CourseMentionPanelProps {
  courseCards:     CourseCard[];
  coursePoolCount: number;
  hasLargeResult:  boolean;
}

function CourseCardItem({ course }: { course: CourseCard }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="cursor-pointer rounded-xl border border-gray-200 bg-white p-3 transition-shadow hover:shadow-md"
      onClick={() => setExpanded((prev) => !prev)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-gray-800">{course.name}</div>
          <div className="mt-1 text-sm text-gray-500">
            {[course.dept, course.credits ? `${course.credits} 學分` : '', course.type]
              .filter(Boolean)
              .join(' · ')}
          </div>
          {course.teacher && (
            <div className="mt-0.5 text-xs text-gray-400">授課：{course.teacher}</div>
          )}
        </div>
        <div className="flex-shrink-0 text-gray-400">
          {expanded ? <HiChevronUp className="h-4 w-4" /> : <HiChevronDown className="h-4 w-4" />}
        </div>
      </div>
      {expanded && course.summary && (
        <div className="mt-2 border-t border-gray-100 pt-2 text-sm leading-relaxed text-gray-600">
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
}: CourseMentionPanelProps) {
  if (courseCards.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {hasLargeResult && (
        <div className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
          <HiInformationCircle className="h-4 w-4 flex-shrink-0" />
          共搜尋到 {coursePoolCount} 門課程，以下僅顯示回答中提到的相關課程
        </div>
      )}
      <div className="space-y-2">
        {courseCards.map((course, i) => (
          <CourseCardItem key={course.code || `${course.name}-${i}`} course={course} />
        ))}
      </div>
    </div>
  );
}
