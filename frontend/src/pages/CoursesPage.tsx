import { useEffect, useMemo, useState } from 'react';
import type { ComponentType, Dispatch, SetStateAction } from 'react';
import {
  HiBeaker,
  HiBookOpen,
  HiBriefcase,
  HiChevronLeft,
  HiChevronRight,
  HiChip,
  HiCog,
  HiGlobeAlt,
  HiHeart,
  HiLibrary,
  HiOfficeBuilding,
  HiSearch,
  HiX,
} from 'react-icons/hi';
import { courseAPI } from '../api/services';
import CourseDetailPanel from '../components/CourseDetailPanel';
import HighlightText from '../components/HighlightText';
import type { Course } from '../types';

const COLLEGE_ORDER = ['文學院', '理學院', '工學院', '管理學院', '資訊電機學院', '地球科學學院', '客家學院', '生醫理工學院', '中心、處室'] as const;
const FALLBACK_COLLEGE = '中心、處室';
const FALLBACK_DEPARTMENT = '未分類系所';
const COLLEGE_CONFIG: Record<string, { icon: ComponentType<{ className?: string }>; gradient: string }> = {
  文學院: { icon: HiBookOpen, gradient: 'from-blue-400 to-violet-500' },
  理學院: { icon: HiBeaker, gradient: 'from-cyan-400 to-blue-500' },
  工學院: { icon: HiCog, gradient: 'from-orange-400 to-red-500' },
  管理學院: { icon: HiBriefcase, gradient: 'from-green-400 to-emerald-500' },
  資訊電機學院: { icon: HiChip, gradient: 'from-indigo-400 to-purple-600' },
  地球科學學院: { icon: HiGlobeAlt, gradient: 'from-teal-400 to-cyan-500' },
  客家學院: { icon: HiLibrary, gradient: 'from-rose-400 to-pink-500' },
  生醫理工學院: { icon: HiHeart, gradient: 'from-pink-400 to-rose-500' },
  '中心、處室': { icon: HiOfficeBuilding, gradient: 'from-slate-400 to-slate-500' },
};

type NavigationLevel = 'colleges' | 'departments' | 'courses';
type ResultTab = 'course_name' | 'detail_info';
type GroupedCourses = Record<string, Record<string, Course[]>>;

const normalize = (value?: string | null) => (value ?? '').trim();
const courseKey = (course: Course) => `${course.serial_no}-${course.course_id}`;

const getDetailPreview = (course: Course, keyword: string) => {
  const text = [course.course_objective, course.course_content, course.course_field, course.textbooks, course.note, course.instructor].filter(Boolean).join(' ');
  if (!text) return '';
  const query = keyword.trim().toLowerCase();
  if (!query) return text.slice(0, 80);
  const hit = text.toLowerCase().indexOf(query);
  if (hit === -1) return text.slice(0, 80);
  const start = Math.max(0, hit - 18);
  const end = Math.min(text.length, hit + query.length + 36);
  return `${start > 0 ? '...' : ''}${text.slice(start, end)}${end < text.length ? '...' : ''}`;
};

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-2 text-sm font-medium transition ${
        active ? 'border-primary-700 bg-primary-900 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  );
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedCredits, setSelectedCredits] = useState<string[]>([]);
  const [selectedSemesters, setSelectedSemesters] = useState<string[]>([]);
  const [selectedCollege, setSelectedCollege] = useState<string | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null);
  const [showSearchPanel, setShowSearchPanel] = useState(false);
  const [navigationLevel, setNavigationLevel] = useState<NavigationLevel>('colleges');
  const [resultTab, setResultTab] = useState<ResultTab>('course_name');
  const [expandedDepartments, setExpandedDepartments] = useState<string[]>([]);

  useEffect(() => {
    courseAPI
      .getCourses()
      .then(setCourses)
      .catch((error) => console.error('Failed to load courses:', error))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!showSearchPanel) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [showSearchPanel]);

  const groupedCourses = useMemo(() => {
    const grouped: GroupedCourses = {};
    courses.forEach((course) => {
      const college = normalize(course.college) || FALLBACK_COLLEGE;
      const department = normalize(course.department) || FALLBACK_DEPARTMENT;
      grouped[college] ??= {};
      grouped[college][department] ??= [];
      grouped[college][department].push(course);
    });
    return grouped;
  }, [courses]);

  const sortedColleges = useMemo(
    () =>
      Object.keys(groupedCourses).sort((a, b) => {
        const ai = COLLEGE_ORDER.indexOf(a as (typeof COLLEGE_ORDER)[number]);
        const bi = COLLEGE_ORDER.indexOf(b as (typeof COLLEGE_ORDER)[number]);
        if (ai === -1 && bi === -1) return a.localeCompare(b, 'zh-Hant');
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      }),
    [groupedCourses]
  );

  const currentDepartments = useMemo(
    () => (!selectedCollege ? [] : Object.keys(groupedCourses[selectedCollege] || {}).sort((a, b) => a.localeCompare(b, 'zh-Hant'))),
    [groupedCourses, selectedCollege]
  );
  const departmentCourses = useMemo(
    () => (!selectedCollege || !selectedDepartment ? [] : groupedCourses[selectedCollege]?.[selectedDepartment] || []),
    [groupedCourses, selectedCollege, selectedDepartment]
  );

  const hasActiveFilters =
    Boolean(searchQuery.trim()) || selectedTypes.length > 0 || selectedCredits.length > 0 || selectedSemesters.length > 0;
  const hasSearchQuery = Boolean(searchQuery.trim());

  const searchableFields = (course: Course) =>
    resultTab === 'course_name'
      ? [course.course_name_zh, course.course_name_en]
      : [
          course.course_name_zh,
          course.course_name_en,
          course.course_objective,
          course.course_content,
          course.course_field,
          course.textbooks,
          course.grading,
          course.note,
          course.instructor,
          course.department,
          course.college,
        ];

  const matchesFilters = (course: Course) => {
    const query = searchQuery.trim().toLowerCase();
    const matchesType = selectedTypes.length === 0 || selectedTypes.includes(normalize(course.required_elective));
    const matchesCredits = selectedCredits.length === 0 || selectedCredits.includes(String(course.credits));
    const matchesSemester = selectedSemesters.length === 0 || selectedSemesters.includes(normalize(course.semester_display));
    const matchesQuery =
      !query ||
      searchableFields(course)
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(query));
    return matchesType && matchesCredits && matchesSemester && matchesQuery;
  };

  const currentCourses = useMemo(
    () => departmentCourses.filter(matchesFilters),
    [departmentCourses, searchQuery, selectedTypes, selectedCredits, selectedSemesters, resultTab]
  );
  const filteredCourses = useMemo(
    () => courses.filter(matchesFilters),
    [courses, searchQuery, selectedTypes, selectedCredits, selectedSemesters, resultTab]
  );

  const groupedSearchResults = useMemo(() => {
    const map = new Map<string, Map<string, Course[]>>();
    filteredCourses.forEach((course) => {
      const college = normalize(course.college) || FALLBACK_COLLEGE;
      const department = normalize(course.department) || FALLBACK_DEPARTMENT;
      if (!map.has(college)) map.set(college, new Map<string, Course[]>());
      const deptMap = map.get(college)!;
      if (!deptMap.has(department)) deptMap.set(department, []);
      deptMap.get(department)!.push(course);
    });
    return Array.from(map.entries())
      .sort((a, b) => {
        const ai = COLLEGE_ORDER.indexOf(a[0] as (typeof COLLEGE_ORDER)[number]);
        const bi = COLLEGE_ORDER.indexOf(b[0] as (typeof COLLEGE_ORDER)[number]);
        if (ai === -1 && bi === -1) return a[0].localeCompare(b[0], 'zh-Hant');
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      })
      .map(([college, departments]) => ({
        college,
        count: Array.from(departments.values()).reduce((sum, list) => sum + list.length, 0),
        departments: Array.from(departments.entries())
          .sort((a, b) => a[0].localeCompare(b[0], 'zh-Hant'))
          .map(([name, list]) => ({ name, count: list.length, courses: list })),
      }));
  }, [filteredCourses]);

  const typeOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => normalize(course.required_elective)).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [courses]
  );
  const creditOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => String(course.credits)).filter(Boolean))).sort((a, b) => Number(a) - Number(b)),
    [courses]
  );
  const semesterOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => normalize(course.semester_display)).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [courses]
  );

  useEffect(() => {
    if (!selectedCollege && sortedColleges.length > 0) setSelectedCollege(sortedColleges[0]);
  }, [sortedColleges, selectedCollege]);

  useEffect(() => {
    if (!selectedCollege) return;
    const departments = Object.keys(groupedCourses[selectedCollege] || {});
    if (!departments.length) return setSelectedDepartment(null);
    if (selectedDepartment && departments.includes(selectedDepartment)) return;
    setSelectedDepartment(null);
    setSelectedCourse(null);
  }, [groupedCourses, selectedCollege, selectedDepartment]);

  useEffect(() => {
    const source = hasActiveFilters ? filteredCourses : currentCourses;
    if (source.length === 0) return setSelectedCourse(null);
    if (selectedCourse && source.some((course) => courseKey(course) === courseKey(selectedCourse))) return;
    if (hasActiveFilters) return setSelectedCourse(null);
    setSelectedCourse(source[0]);
  }, [currentCourses, filteredCourses, hasActiveFilters, selectedCourse]);

  const toggleValue = (value: string, setter: Dispatch<SetStateAction<string[]>>) =>
    setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]));

  const clearAllFilters = () => {
    setSearchQuery('');
    setSelectedTypes([]);
    setSelectedCredits([]);
    setSelectedSemesters([]);
  };

  const toggleExpandedDepartment = (key: string) => {
    setExpandedDepartments((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const activeTags = [
    ...(searchQuery.trim() ? [{ key: `search-${searchQuery}`, label: `搜尋：${searchQuery.trim()}`, onRemove: () => setSearchQuery('') }] : []),
    ...selectedTypes.map((value) => ({ key: `type-${value}`, label: value, onRemove: () => setSelectedTypes((current) => current.filter((item) => item !== value)) })),
    ...selectedCredits.map((value) => ({ key: `credit-${value}`, label: `${value} 學分`, onRemove: () => setSelectedCredits((current) => current.filter((item) => item !== value)) })),
    ...selectedSemesters.map((value) => ({ key: `semester-${value}`, label: value, onRemove: () => setSelectedSemesters((current) => current.filter((item) => item !== value)) })),
  ];

  const navigationTitle = navigationLevel === 'colleges' ? '選擇學院' : navigationLevel === 'departments' ? selectedCollege || '選擇系所' : selectedDepartment || '選擇課程';
  const navigationHint = navigationLevel === 'colleges' ? '從學院開始瀏覽' : navigationLevel === 'departments' ? '查看各系所課程' : '選擇一門課程';

  return (
    <>
      <div className="h-full bg-gray-50">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-primary-600"></div>
              <p className="text-gray-600">正在載入課程資料...</p>
            </div>
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col md:flex-row">
            <aside className="relative z-10 flex w-full shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white md:min-h-0 md:w-[24rem] md:min-w-[24rem] md:max-w-[24rem]">
              <div className="sticky top-0 z-10 border-b border-slate-200 bg-white">
                <div className="flex items-center justify-between gap-3 px-4 py-3">
                  <h2 className="text-sm font-bold tracking-wide text-slate-900">課程導航</h2>
                  <button type="button" onClick={() => setShowSearchPanel(true)} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50" aria-label="開啟搜尋與篩選">
                    <HiSearch className="h-5 w-5" />
                  </button>
                </div>

                {hasActiveFilters ? (
                  <div className="space-y-3 border-t border-slate-200 px-4 py-3">
                    {activeTags.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {activeTags.map((tag) => (
                          <button key={tag.key} type="button" onClick={tag.onRemove} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100">
                            <span>{tag.label}</span>
                            <HiX className="h-3.5 w-3.5" />
                          </button>
                        ))}
                      </div>
                    ) : null}

                    {hasSearchQuery ? (
                      <div className="flex w-full overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
                        <button
                          type="button"
                          onClick={() => setResultTab('course_name')}
                          className={`min-w-0 flex-1 px-4 py-2 text-sm font-medium leading-none transition ${
                            resultTab === 'course_name' ? 'bg-slate-600 text-white' : 'text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          課程名稱
                        </button>
                        <button
                          type="button"
                          onClick={() => setResultTab('detail_info')}
                          className={`min-w-0 flex-1 border-l border-slate-200 px-4 py-2 text-sm font-medium leading-none transition ${
                            resultTab === 'detail_info' ? 'bg-slate-600 text-white border-l-slate-600' : 'text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          詳細資訊
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="border-t border-slate-200 bg-gradient-to-r from-primary-50 to-primary-100 px-4 py-3">
                    <div className="flex items-center gap-2">
                      {navigationLevel !== 'colleges' ? (
                        <button type="button" onClick={() => {
                          if (navigationLevel === 'courses') {
                            setSelectedCourse(null);
                            setNavigationLevel('departments');
                            return;
                          }
                          setSelectedDepartment(null);
                          setSelectedCourse(null);
                          setNavigationLevel('colleges');
                        }} className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm" aria-label="返回上一層">
                          <HiChevronLeft className="h-5 w-5" />
                        </button>
                      ) : null}
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-slate-900">{navigationTitle}</div>
                        <div className="mt-0.5 text-xs text-slate-500">{navigationHint}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-y-auto">
                {hasActiveFilters ? (
                  <div className="bg-white">
                    {groupedSearchResults.length > 0 ? (
                      groupedSearchResults.map((group) => (
                        <div key={group.college} className="border-b border-slate-200">
                          <div className="bg-slate-50 px-4 py-2 text-sm text-slate-500">{group.college} · {group.count} 門</div>
                          {group.departments.map((department) => {
                            const departmentKey = `${group.college}-${department.name}`;
                            const isExpanded = expandedDepartments.includes(departmentKey);
                            return (
                              <div key={departmentKey} className="border-t border-slate-100">
                                <button type="button" onClick={() => toggleExpandedDepartment(departmentKey)} className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-slate-50">
                                  <div className="truncate text-sm font-medium text-slate-900">{department.name}</div>
                                  <div className="ml-3 flex items-center gap-3 text-sm text-slate-400">
                                    <span>{department.count} 門</span>
                                    <HiChevronRight className={`h-4 w-4 transition ${isExpanded ? 'rotate-90' : ''}`} />
                                  </div>
                                </button>
                                {isExpanded ? (
                                  <div className="border-t border-slate-100">
                                    {department.courses.map((course) => {
                                      const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                                      const isRequired = normalize(course.required_elective) === '必修';
                                      const preview = getDetailPreview(course, searchQuery);
                                      return (
                                        <button
                                          key={courseKey(course)}
                                          type="button"
                                          onClick={() => {
                                            setSelectedCollege(group.college);
                                            setSelectedDepartment(department.name);
                                            setSelectedCourse(course);
                                          }}
                                          className={`w-full border-t border-slate-100 px-4 py-3 text-left transition hover:bg-primary-50 ${isSelected ? 'border-l-4 border-primary-600 bg-primary-50' : ''}`}
                                        >
                                          <div className="text-sm font-semibold leading-snug text-slate-900">
                                            <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                          </div>
                                          {resultTab === 'course_name' ? (
                                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                              {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                              <span>{course.credits} 學分</span>
                                              {course.instructor ? <span>{course.instructor}</span> : null}
                                            </div>
                                          ) : (
                                            <div className="mt-1 space-y-1 text-xs text-slate-500">
                                              <div className="flex flex-wrap items-center gap-2">
                                                {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                                <span>{course.credits} 學分</span>
                                                {course.instructor ? <span>{course.instructor}</span> : null}
                                              </div>
                                              {preview ? (
                                                <p className="line-clamp-2 leading-5 text-slate-500">
                                                  <HighlightText text={preview} keyword={searchQuery} />
                                                </p>
                                              ) : null}
                                            </div>
                                          )}
                                        </button>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      ))
                    ) : (
                      <div className="p-8 text-center text-sm text-slate-500">目前沒有符合條件的課程，請調整搜尋或篩選。</div>
                    )}
                  </div>
                ) : navigationLevel === 'colleges' ? (
                  <div className="bg-white">
                    {sortedColleges.map((college) => {
                      const config = COLLEGE_CONFIG[college] || COLLEGE_CONFIG[FALLBACK_COLLEGE];
                      const Icon = config.icon;
                      return (
                        <button key={college} type="button" onClick={() => { setSelectedCollege(college); setSelectedDepartment(null); setSelectedCourse(null); setNavigationLevel('departments'); }} className="flex w-full items-center gap-3 border-b border-slate-200 px-4 py-3 text-left transition hover:bg-slate-50">
                          <div className={`flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br ${config.gradient} shadow-sm`}>
                            <Icon className="h-5 w-5 text-white" />
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-900">{college}</div>
                            <div className="text-xs text-slate-500">{Object.keys(groupedCourses[college] || {}).length} 系所</div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : navigationLevel === 'departments' ? (
                  <div className="bg-white">
                    {currentDepartments.length > 0 ? (
                      currentDepartments.map((department) => {
                        const departmentCount = (groupedCourses[selectedCollege!]?.[department] || []).length;
                        return (
                          <button key={department} type="button" onClick={() => { const nextCourses = groupedCourses[selectedCollege || '']?.[department] || []; setSelectedDepartment(department); setSelectedCourse(nextCourses[0] ?? null); setNavigationLevel('courses'); }} className="flex w-full items-center justify-between border-b border-slate-200 px-4 py-3 text-left transition hover:bg-primary-50">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-slate-900">{department}</div>
                              <div className="text-xs text-slate-500">{departmentCount} 門課程</div>
                            </div>
                            <HiChevronRight className="h-5 w-5 shrink-0 text-slate-400" />
                          </button>
                        );
                      })
                    ) : (
                      <div className="px-4 py-6 text-sm text-slate-500">目前沒有可瀏覽的系所。</div>
                    )}
                  </div>
                ) : (
                  <div className="bg-white">
                    {currentCourses.length > 0 ? (
                      <div className="divide-y divide-slate-200">
                        {currentCourses.map((course) => {
                          const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                          const isRequired = normalize(course.required_elective) === '必修';
                          return (
                            <button key={courseKey(course)} type="button" onClick={() => setSelectedCourse(course)} className={`w-full px-4 py-3 text-left transition hover:bg-primary-50 ${isSelected ? 'border-l-4 border-primary-600 bg-primary-50' : ''}`}>
                              <div className="mb-1 text-sm font-semibold leading-snug text-slate-900">
                                <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                <span>{course.credits} 學分</span>
                                {course.instructor ? <span>{course.instructor}</span> : null}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-8 text-center text-slate-500">
                        <HiSearch className="mx-auto mb-3 h-10 w-10 text-slate-400" />
                        <p className="text-sm font-medium">這個系所目前沒有符合條件的課程</p>
                        <p className="mt-1 text-sm text-slate-400">你可以回上一層重新選擇，或打開搜尋與篩選。</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </aside>
            <div className="relative z-0 min-w-0 flex-1 overflow-y-auto bg-gray-50 p-4">
              <CourseDetailPanel course={selectedCourse} searchKeyword={searchQuery} />
            </div>
          </div>
        )}
      </div>

      {showSearchPanel ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" onClick={() => setShowSearchPanel(false)}>
          <div className="w-full max-w-2xl rounded-[2rem] bg-white p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">搜尋與篩選課程</h3>
                <p className="mt-1 text-sm text-slate-500">輸入關鍵字，或用按鈕快速縮小課程範圍。</p>
              </div>
              <button type="button" onClick={() => setShowSearchPanel(false)} className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200" aria-label="關閉搜尋與篩選">
                <HiX className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-5">
              <label className="mb-2 block text-sm font-medium text-slate-700">搜尋關鍵字</label>
              <div className="relative">
                <HiSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input type="text" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="輸入課名、教師、課程內容或系所" className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500" />
              </div>
            </div>

            <div className="mt-5 space-y-5">
              <div><label className="mb-2 block text-sm font-medium text-slate-700">類型</label><div className="flex flex-wrap gap-2">{typeOptions.map((option) => <FilterPill key={option} label={option} active={selectedTypes.includes(option)} onClick={() => toggleValue(option, setSelectedTypes)} />)}</div></div>
              <div><label className="mb-2 block text-sm font-medium text-slate-700">學分</label><div className="flex flex-wrap gap-2">{creditOptions.map((option) => <FilterPill key={option} label={`${option} 學分`} active={selectedCredits.includes(option)} onClick={() => toggleValue(option, setSelectedCredits)} />)}</div></div>
              <div><label className="mb-2 block text-sm font-medium text-slate-700">學期</label><div className="flex flex-wrap gap-2">{semesterOptions.map((option) => <FilterPill key={option} label={option} active={selectedSemesters.includes(option)} onClick={() => toggleValue(option, setSelectedSemesters)} />)}</div></div>
            </div>

            <div className="mt-6 flex gap-3">
              <button type="button" onClick={clearAllFilters} className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50">清除全部</button>
              <button type="button" onClick={() => setShowSearchPanel(false)} className="flex-1 rounded-xl bg-primary-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-primary-800">套用條件</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
