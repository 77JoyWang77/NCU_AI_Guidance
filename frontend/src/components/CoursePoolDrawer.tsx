import { useState } from 'react';
import { HiX, HiSearch, HiChevronDown, HiChevronUp } from 'react-icons/hi';
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

interface CoursePoolDrawerProps {
  courses:       CourseCard[];
  onClose:       () => void;
  onCourseClick: (course: CourseCard) => void;
}

function PoolCard({ course, onClick }: { course: CourseCard; onClick: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const typeColor =
    course.type === '必修'
      ? 'text-red-600 bg-red-50 border-red-200'
      : course.type
      ? 'text-green-600 bg-green-50 border-green-200'
      : 'text-gray-500 bg-gray-50 border-gray-200';

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onClick}
          className="min-w-0 flex-1 text-left"
        >
          <div className="font-medium text-gray-800 hover:text-primary-700">{course.name}</div>
          <div className="mt-0.5 text-xs text-gray-500">
            {[course.dept, course.credits ? `${course.credits} 學分` : '']
              .filter(Boolean)
              .join(' · ')}
          </div>
        </button>
        <div className="flex flex-shrink-0 items-center gap-1.5">
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
              {expanded ? <HiChevronUp className="h-4 w-4" /> : <HiChevronDown className="h-4 w-4" />}
            </button>
          )}
        </div>
      </div>
      {course.domain_tags && (() => {
        const tags = parseDomainTags(course.domain_tags)
          .filter(t => t.relevance === 'high' || t.relevance === 'medium')
          .slice(0, 4);
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
      {expanded && course.summary && (
        <p className="mt-2 border-t border-gray-100 pt-2 text-xs leading-relaxed text-gray-500">
          {course.summary}
        </p>
      )}
    </div>
  );
}

export default function CoursePoolDrawer({ courses, onClose, onCourseClick }: CoursePoolDrawerProps) {
  const [query, setQuery] = useState('');

  const filtered = query
    ? courses.filter(
        (c) =>
          c.name.includes(query) ||
          c.dept.includes(query) ||
          (c.teacher && c.teacher.includes(query))
      )
    : courses;

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* drawer */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col bg-white shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-4 py-3">
          <div>
            <h3 className="font-semibold text-gray-900">全部課程</h3>
            <p className="text-xs text-gray-500">{courses.length} 門課程</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl p-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900"
          >
            <HiX className="h-5 w-5" />
          </button>
        </div>

        {/* search */}
        <div className="border-b border-gray-200 px-4 py-3">
          <div className="flex items-center gap-2 rounded-xl border border-gray-300 bg-gray-50 px-3 py-2">
            <HiSearch className="h-4 w-4 flex-shrink-0 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="篩選課名、系所或教師..."
              className="flex-1 bg-transparent text-sm text-gray-800 placeholder-gray-400 focus:outline-none"
            />
            {query && (
              <button onClick={() => setQuery('')} className="text-gray-400 hover:text-gray-600">
                <HiX className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          {query && (
            <p className="mt-1.5 text-xs text-gray-500">
              顯示 {filtered.length} / {courses.length} 門
            </p>
          )}
        </div>

        {/* list */}
        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <p className="mt-8 text-center text-sm text-gray-400">找不到符合的課程</p>
          ) : (
            filtered.map((c, i) => (
              <PoolCard
                key={c.code || `${c.name}-${i}`}
                course={c}
                onClick={() => { onCourseClick(c); }}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}
