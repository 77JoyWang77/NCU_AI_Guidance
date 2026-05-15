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
  HiPlus,
  HiSearch,
  HiTrash,
  HiX,
} from 'react-icons/hi';
import { courseAPI } from '../api/services';
import CourseCompareModal from '../components/CourseCompareModal';
import CourseDetailPanel from '../components/CourseDetailPanel';
import HighlightText from '../components/HighlightText';
import type { Course } from '../types';

const COLLEGE_ORDER = ['文學院', '理學院', '工學院', '管理學院', '資訊電機學院', '地球科學學院', '客家學院', '生醫理工學院', '中心、處室'] as const;
const FALLBACK_COLLEGE = '中心、處室';
const FALLBACK_DEPARTMENT = '未分類單位';
const COMPARE_LIMIT = 3;

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
type SearchMode = 'semantic' | 'keyword';
type SemanticSearchMode = 'idle' | 'semantic' | 'fallback';
type GroupedCourses = Record<string, Record<string, Course[]>>;

const normalize = (value?: string | null) => (value ?? '').trim();
const courseKey = (course: Course) => `${course.serial_no}-${course.course_id}`;
const formatScore = (score?: number) => (typeof score === 'number' ? `${Math.round(score * 100)}%` : null);
const sameStringArray = (left: string[], right: string[]) => {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((value) => rightSet.has(value));
};
const metadataPreview = (course: Course) =>
  Array.from(new Set([...(course.tools ?? []), ...(course.concepts ?? []), ...(course.topic_tags ?? [])].map((item) => item.trim()).filter(Boolean))).slice(0, 3);

const getDetailPreview = (course: Course, keyword: string) => {
  const text = [
    course.semantic_summary,
    course.course_objective,
    course.course_content,
    course.course_field,
    course.textbooks,
    course.note,
    course.instructor,
    course.eligibility_summary,
    ...(course.tools ?? []),
    ...(course.concepts ?? []),
    ...(course.topic_tags ?? []),
    ...(course.domain_tags ?? []),
    ...(course.languages ?? []),
    ...(course.simplified_concepts ?? []),
    ...(course.core_questions ?? []),
  ].filter(Boolean).join(' ');
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
  const [isMobileNavigatorOpen, setIsMobileNavigatorOpen] = useState(true);
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
  const [searchMode, setSearchMode] = useState<SearchMode>('semantic');
  const [draftSearchQuery, setDraftSearchQuery] = useState('');
  const [draftSelectedTypes, setDraftSelectedTypes] = useState<string[]>([]);
  const [draftSelectedCredits, setDraftSelectedCredits] = useState<string[]>([]);
  const [draftSelectedSemesters, setDraftSelectedSemesters] = useState<string[]>([]);
  const [draftSearchMode, setDraftSearchMode] = useState<SearchMode>('semantic');
  const [expandedDepartments, setExpandedDepartments] = useState<string[]>([]);
  const [semanticCourses, setSemanticCourses] = useState<Course[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [semanticMode, setSemanticMode] = useState<SemanticSearchMode>('idle');
  const [semanticMessage, setSemanticMessage] = useState('');
  const [compareCourses, setCompareCourses] = useState<Course[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareNotice, setCompareNotice] = useState('');

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
  const hasDraftSearchQuery = Boolean(draftSearchQuery.trim());
  const hasDraftChanges =
    draftSearchMode !== searchMode ||
    draftSearchQuery !== searchQuery ||
    !sameStringArray(draftSelectedTypes, selectedTypes) ||
    !sameStringArray(draftSelectedCredits, selectedCredits) ||
    !sameStringArray(draftSelectedSemesters, selectedSemesters);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!query || searchMode !== 'semantic') {
      setSemanticCourses([]);
      setSemanticLoading(false);
      setSemanticMode('idle');
      setSemanticMessage('');
      return;
    }

    let cancelled = false;
    setSemanticLoading(true);

    const runSearch = async () => {
      try {
        const response = await courseAPI.semanticSearch({
          query,
          selected_types: selectedTypes,
          selected_credits: selectedCredits,
          selected_semesters: selectedSemesters,
          limit: 50,
        });
        if (cancelled) return;

        if (response.mode === 'semantic') {
          setSemanticCourses(response.results);
          setSemanticMode('semantic');
          setSemanticMessage(response.message ?? '');
          return;
        }

        setSemanticCourses([]);
        setSemanticMode('fallback');
        setSemanticMessage(response.message || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。');
      } catch (error) {
        if (cancelled) return;
        console.warn('Semantic course search failed, using keyword fallback:', error);
        setSemanticCourses([]);
        setSemanticMode('fallback');
        setSemanticMessage('關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。');
      } finally {
        if (!cancelled) setSemanticLoading(false);
      }
    };

    void runSearch();

    return () => {
      cancelled = true;
    };
  }, [searchMode, searchQuery, selectedTypes, selectedCredits, selectedSemesters]);

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
          course.semantic_summary,
          course.eligibility_summary,
          ...(course.tools ?? []),
          ...(course.concepts ?? []),
          ...(course.topic_tags ?? []),
          ...(course.domain_tags ?? []),
          ...(course.languages ?? []),
          ...(course.simplified_concepts ?? []),
          ...(course.core_questions ?? []),
        ];

  const matchesStructuredFilters = (course: Course) => {
    const matchesType = selectedTypes.length === 0 || selectedTypes.includes(normalize(course.required_elective));
    const matchesCredits = selectedCredits.length === 0 || selectedCredits.includes(String(course.credits));
    const matchesSemester = selectedSemesters.length === 0 || selectedSemesters.includes(normalize(course.semester_display));
    return matchesType && matchesCredits && matchesSemester;
  };

  const matchesKeywordFilters = (course: Course) => {
    const query = searchQuery.trim().toLowerCase();
    const matchesQuery = !query || searchableFields(course).filter(Boolean).some((value) => value!.toLowerCase().includes(query));
    return matchesStructuredFilters(course) && matchesQuery;
  };

  const currentCourses = useMemo(
    () => departmentCourses.filter(matchesKeywordFilters),
    [departmentCourses, searchQuery, selectedTypes, selectedCredits, selectedSemesters, resultTab]
  );

  const filteredCourses = useMemo(
    () => {
      if (hasSearchQuery && searchMode === 'semantic') {
        if (semanticMode === 'semantic') return semanticCourses.filter(matchesStructuredFilters);
        if (semanticMode === 'fallback') return courses.filter(matchesKeywordFilters);
        return [];
      }
      return courses.filter(matchesKeywordFilters);
    },
    [courses, hasSearchQuery, searchMode, searchQuery, selectedTypes, selectedCredits, selectedSemesters, resultTab, semanticCourses, semanticMode]
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
    const selectedCourseInFilteredResults =
      hasActiveFilters &&
      selectedCourse &&
      filteredCourses.some((course) => courseKey(course) === courseKey(selectedCourse));

    if (!departments.length) {
      setSelectedDepartment(null);
      return;
    }
    if (selectedDepartment && departments.includes(selectedDepartment)) return;
    setSelectedDepartment(null);
    if (!selectedCourseInFilteredResults) {
      setSelectedCourse(null);
    }
  }, [filteredCourses, groupedCourses, hasActiveFilters, selectedCollege, selectedCourse, selectedDepartment]);

  useEffect(() => {
    const source = hasActiveFilters ? filteredCourses : currentCourses;
    if (!selectedCourse) return;
    if (selectedCourse && source.some((course) => courseKey(course) === courseKey(selectedCourse))) return;
    setSelectedCourse(null);
  }, [currentCourses, filteredCourses, hasActiveFilters, selectedCourse]);

  const toggleValue = (value: string, setter: Dispatch<SetStateAction<string[]>>) =>
    setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]));

  const isCourseCompared = (course: Course) => compareCourses.some((item) => courseKey(item) === courseKey(course));

  const toggleCompareCourse = (course: Course) => {
    if (isCourseCompared(course)) {
      setCompareCourses((current) => current.filter((item) => courseKey(item) !== courseKey(course)));
      setCompareNotice('');
      return;
    }

    if (compareCourses.length >= COMPARE_LIMIT) {
      setCompareNotice(`最多只能同時對比 ${COMPARE_LIMIT} 門課。`);
      return;
    }

    setCompareCourses((current) => [...current, course]);
    setCompareNotice('');
  };

  const removeCompareCourse = (course: Course) => {
    setCompareCourses((current) => current.filter((item) => courseKey(item) !== courseKey(course)));
    setCompareNotice('');
  };

  const clearCompareCourses = () => {
    setCompareCourses([]);
    setCompareOpen(false);
    setCompareNotice('');
  };

  const openSearchPanel = () => {
    setDraftSearchMode(searchMode);
    setDraftSearchQuery(searchQuery);
    setDraftSelectedTypes(selectedTypes);
    setDraftSelectedCredits(selectedCredits);
    setDraftSelectedSemesters(selectedSemesters);
    setShowSearchPanel(true);
  };

  const clearDraftFilters = () => {
    setDraftSearchQuery('');
    setDraftSelectedTypes([]);
    setDraftSelectedCredits([]);
    setDraftSelectedSemesters([]);
  };

  const applySearchFilters = () => {
    setSearchMode(draftSearchMode);
    setSearchQuery(draftSearchQuery);
    setSelectedTypes(draftSelectedTypes);
    setSelectedCredits(draftSelectedCredits);
    setSelectedSemesters(draftSelectedSemesters);
    setShowSearchPanel(false);
  };

  const toggleExpandedDepartment = (key: string) => {
    setExpandedDepartments((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const activeTags = [
    ...(searchQuery.trim() ? [{ key: `search-${searchQuery}`, label: `${searchMode === 'semantic' ? '關鍵字向量搜尋' : '一般文字搜尋'}：${searchQuery.trim()}`, onRemove: () => setSearchQuery('') }] : []),
    ...selectedTypes.map((value) => ({ key: `type-${value}`, label: value, onRemove: () => setSelectedTypes((current) => current.filter((item) => item !== value)) })),
    ...selectedCredits.map((value) => ({ key: `credit-${value}`, label: `${value} 學分`, onRemove: () => setSelectedCredits((current) => current.filter((item) => item !== value)) })),
    ...selectedSemesters.map((value) => ({ key: `semester-${value}`, label: value, onRemove: () => setSelectedSemesters((current) => current.filter((item) => item !== value)) })),
  ];

  const navigationTitle = navigationLevel === 'colleges' ? '選擇學院' : navigationLevel === 'departments' ? selectedCollege || '選擇系所' : selectedDepartment || '選擇課程';
  const navigationHint = navigationLevel === 'colleges' ? '從學院開始瀏覽' : navigationLevel === 'departments' ? '查看各系所課程' : '選擇一門課程查看詳情';
  const closeMobileNavigator = () => setIsMobileNavigatorOpen(false);
  const openMobileNavigator = () => setIsMobileNavigatorOpen(true);

  const handleSelectSearchResult = (college: string, department: string, course: Course) => {
    setSelectedCollege(college);
    setSelectedDepartment(department);
    setSelectedCourse(course);
    setNavigationLevel('courses');
    closeMobileNavigator();
  };

  const handleSelectFlatSearchResult = (course: Course) => {
    handleSelectSearchResult(normalize(course.college) || FALLBACK_COLLEGE, normalize(course.department) || FALLBACK_DEPARTMENT, course);
  };

  const handleSelectCollege = (college: string) => {
    setSelectedCollege(college);
    setSelectedDepartment(null);
    setSelectedCourse(null);
    setNavigationLevel('departments');
    openMobileNavigator();
  };

  const handleSelectDepartment = (department: string) => {
    setSelectedDepartment(department);
    setSelectedCourse(null);
    setNavigationLevel('courses');
    openMobileNavigator();
  };

  const handleSelectCourse = (course: Course) => {
    setSelectedCourse(course);
    closeMobileNavigator();
  };

  const renderCompareButton = (course: Course) => {
    const compared = isCourseCompared(course);
    return (
      <button
        type="button"
        onClick={() => toggleCompareCourse(course)}
        className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition ${
          compared
            ? 'border-primary-300 bg-primary-50 text-primary-700 hover:bg-primary-100'
            : 'border-slate-200 bg-white text-slate-500 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700'
        }`}
        aria-label={`${compared ? '移除對比' : '加入對比'}：${course.course_name_zh}`}
        title={compared ? '移除對比' : '加入對比'}
      >
        {compared ? <HiX className="h-4 w-4" /> : <HiPlus className="h-4 w-4" />}
      </button>
    );
  };

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
            <aside className={`relative z-10 min-h-0 w-full flex-col overflow-hidden border-r border-slate-200 bg-white ${isMobileNavigatorOpen ? 'flex flex-1' : 'hidden'} md:flex md:w-[24rem] md:min-w-[24rem] md:max-w-[24rem] md:flex-none`}>
              <div className="sticky top-0 z-10 border-b border-slate-200 bg-white">
                <div className="flex items-center justify-between gap-3 px-4 py-3">
                  <h2 className="text-sm font-bold tracking-wide text-slate-900">課程導航</h2>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={openSearchPanel} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50" aria-label="開啟課程搜尋">
                      <HiSearch className="h-5 w-5" />
                    </button>
                    <button type="button" onClick={closeMobileNavigator} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 md:hidden" aria-label="收起課程導航">
                      <HiChevronLeft className="h-5 w-5" />
                    </button>
                  </div>
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

                    {hasSearchQuery && searchMode === 'semantic' ? (
                      <div className={`rounded-lg px-3 py-2 text-xs ${semanticMode === 'fallback' ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
                        {semanticLoading
                          ? '正在使用 Qdrant 關鍵字向量搜尋...'
                          : semanticMode === 'semantic'
                            ? `Qdrant 關鍵字向量搜尋結果：${filteredCourses.length} 門`
                            : semanticMessage || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。'}
                      </div>
                    ) : null}

                    {hasSearchQuery && searchMode === 'keyword' ? (
                      <div className="flex w-full overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
                        <button type="button" onClick={() => setResultTab('course_name')} className={`min-w-0 flex-1 px-4 py-2 text-sm font-medium leading-none transition ${resultTab === 'course_name' ? 'bg-slate-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
                          課名
                        </button>
                        <button type="button" onClick={() => setResultTab('detail_info')} className={`min-w-0 flex-1 border-l border-slate-200 px-4 py-2 text-sm font-medium leading-none transition ${resultTab === 'detail_info' ? 'border-l-slate-600 bg-slate-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
                          詳細內容
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="border-t border-slate-200 bg-gradient-to-r from-primary-50 to-primary-100 px-4 py-3">
                    <div className="flex items-center gap-2">
                      {navigationLevel !== 'colleges' ? (
                        <button
                          type="button"
                          onClick={() => {
                            if (navigationLevel === 'courses') {
                              setSelectedCourse(null);
                              setNavigationLevel('departments');
                              return;
                            }
                            setSelectedDepartment(null);
                            setSelectedCourse(null);
                            setNavigationLevel('colleges');
                          }}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm"
                          aria-label="返回上一層"
                        >
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
                    {hasSearchQuery && searchMode === 'semantic' ? (
                      semanticLoading ? (
                        <div className="p-8 text-center text-sm text-slate-500">正在搜尋相關課程...</div>
                      ) : filteredCourses.length > 0 ? (
                        <div className="divide-y divide-slate-200">
                          {filteredCourses.map((course) => {
                            const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                            const isRequired = normalize(course.required_elective) === '必修';
                            const scoreLabel = formatScore(course.relevance_score);
                            const preview = getDetailPreview(course, searchQuery);
                            const tags = metadataPreview(course);
                            return (
                              <div key={courseKey(course)} className={`flex gap-2 px-4 py-3 transition hover:bg-primary-50 ${isSelected ? 'border-l-4 border-primary-600 bg-primary-50' : ''}`}>
                                <button type="button" onClick={() => handleSelectFlatSearchResult(course)} className="min-w-0 flex-1 text-left">
                                  <div className="text-sm font-semibold leading-snug text-slate-900">
                                    <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                  </div>
                                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                    {scoreLabel ? <span className="rounded-full bg-blue-50 px-2 py-0.5 font-medium text-blue-700">相關度 {scoreLabel}</span> : null}
                                    {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                    <span>{course.credits} 學分</span>
                                    {course.semester_display ? <span>{course.semester_display}</span> : null}
                                    {course.department ? <span>{course.department}</span> : null}
                                    {course.instructor ? <span>{course.instructor}</span> : null}
                                  </div>
                                  {preview ? (
                                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                                      <HighlightText text={preview} keyword={searchQuery} />
                                    </p>
                                  ) : null}
                                  {tags.length > 0 ? (
                                    <div className="mt-2 flex flex-wrap gap-1.5">
                                      {tags.map((tag) => (
                                        <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                          <HighlightText text={tag} keyword={searchQuery} />
                                        </span>
                                      ))}
                                    </div>
                                  ) : null}
                                </button>
                                {renderCompareButton(course)}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="p-8 text-center text-sm text-slate-500">找不到符合條件的課程。</div>
                      )
                    ) : groupedSearchResults.length > 0 ? (
                      groupedSearchResults.map((group) => (
                        <div key={group.college} className="border-b border-slate-200">
                          <div className="bg-slate-50 px-4 py-2 text-sm text-slate-500">{group.college}．{group.count} 門</div>
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
                                      const tags = metadataPreview(course);
                                      return (
                                        <div key={courseKey(course)} className={`flex gap-2 border-t border-slate-100 px-4 py-3 transition hover:bg-primary-50 ${isSelected ? 'border-l-4 border-primary-600 bg-primary-50' : ''}`}>
                                          <button type="button" onClick={() => handleSelectSearchResult(group.college, department.name, course)} className="min-w-0 flex-1 text-left">
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
                                                {tags.length > 0 ? (
                                                  <div className="flex flex-wrap gap-1.5">
                                                    {tags.map((tag) => (
                                                      <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                                        <HighlightText text={tag} keyword={searchQuery} />
                                                      </span>
                                                    ))}
                                                  </div>
                                                ) : null}
                                              </div>
                                            )}
                                          </button>
                                          {renderCompareButton(course)}
                                        </div>
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
                      <div className="p-8 text-center text-sm text-slate-500">找不到符合條件的課程。</div>
                    )}
                  </div>
                ) : navigationLevel === 'colleges' ? (
                  <div className="bg-white">
                    {sortedColleges.map((college) => {
                      const config = COLLEGE_CONFIG[college] || COLLEGE_CONFIG[FALLBACK_COLLEGE];
                      const Icon = config.icon;
                      return (
                        <button key={college} type="button" onClick={() => handleSelectCollege(college)} className="flex w-full items-center gap-3 border-b border-slate-200 px-4 py-3 text-left transition hover:bg-slate-50">
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
                          <button key={department} type="button" onClick={() => handleSelectDepartment(department)} className="flex w-full items-center justify-between border-b border-slate-200 px-4 py-3 text-left transition hover:bg-primary-50">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-slate-900">{department}</div>
                              <div className="text-xs text-slate-500">{departmentCount} 門課</div>
                            </div>
                            <HiChevronRight className="h-5 w-5 shrink-0 text-slate-400" />
                          </button>
                        );
                      })
                    ) : (
                      <div className="px-4 py-6 text-sm text-slate-500">這個學院目前沒有可顯示的系所。</div>
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
                            <div key={courseKey(course)} className={`flex gap-2 px-4 py-3 transition hover:bg-primary-50 ${isSelected ? 'border-l-4 border-primary-600 bg-primary-50' : ''}`}>
                              <button type="button" onClick={() => handleSelectCourse(course)} className="min-w-0 flex-1 text-left">
                                <div className="mb-1 text-sm font-semibold leading-snug text-slate-900">
                                  <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                </div>
                                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                  {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                  <span>{course.credits} 學分</span>
                                  {course.instructor ? <span>{course.instructor}</span> : null}
                                </div>
                              </button>
                              {renderCompareButton(course)}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-8 text-center text-slate-500">
                        <HiSearch className="mx-auto mb-3 h-10 w-10 text-slate-400" />
                        <p className="text-sm font-medium">目前找不到符合條件的課程。</p>
                        <p className="mt-1 text-sm text-slate-400">試著返回上一層，或調整搜尋與篩選條件。</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </aside>

            <div className={`relative z-0 min-h-0 min-w-0 flex-1 overflow-y-auto bg-gray-50 p-4 ${isMobileNavigatorOpen ? 'hidden md:block' : 'block'}`}>
              {!isMobileNavigatorOpen ? (
                <button
                  type="button"
                  onClick={openMobileNavigator}
                  className="fixed right-4 top-24 z-30 inline-flex h-11 items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-lg transition hover:bg-slate-50 md:hidden"
                >
                  <HiChevronRight className="h-4 w-4" />
                  課程導航
                </button>
              ) : null}

              <div className="mb-3 flex items-center justify-between md:hidden">
                <button type="button" onClick={openMobileNavigator} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
                  <HiChevronRight className="h-4 w-4" />
                  課程導航
                </button>
                {selectedCourse ? <span className="truncate pl-3 text-xs text-slate-500">{selectedCourse.course_name_zh}</span> : null}
              </div>
              <CourseDetailPanel
                course={selectedCourse}
                searchKeyword={searchQuery}
                isCompared={selectedCourse ? isCourseCompared(selectedCourse) : false}
                onToggleCompare={toggleCompareCourse}
              />
            </div>
          </div>
        )}
      </div>

      {compareCourses.length > 0 ? (
        <div className="fixed bottom-4 right-4 z-40 w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-950">課程對比</div>
              <div className="mt-0.5 text-xs text-slate-500">已選 {compareCourses.length} / {COMPARE_LIMIT} 門</div>
            </div>
            <button type="button" onClick={clearCompareCourses} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition hover:bg-red-50 hover:text-red-600" aria-label="清空課程對比">
              <HiTrash className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {compareCourses.map((course) => (
              <button key={courseKey(course)} type="button" onClick={() => removeCompareCourse(course)} className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary-100 bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-800 transition hover:bg-primary-100">
                <span className="truncate">{course.course_name_zh}</span>
                <HiX className="h-3.5 w-3.5 shrink-0" />
              </button>
            ))}
          </div>
          {compareNotice ? <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{compareNotice}</div> : null}
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => setCompareOpen(true)} disabled={compareCourses.length < 2} className="flex-1 rounded-xl bg-primary-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-primary-800 disabled:cursor-not-allowed disabled:bg-slate-300">
              開始對比
            </button>
            <button type="button" onClick={clearCompareCourses} className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
              清空
            </button>
          </div>
          {compareCourses.length < 2 ? <div className="mt-2 text-xs text-slate-500">至少選 2 門課才能開始對比。</div> : null}
        </div>
      ) : null}

      {showSearchPanel ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" onClick={() => setShowSearchPanel(false)}>
          <div className="w-full max-w-2xl rounded-[2rem] bg-white p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">搜尋與篩選課程</h3>
                <p className="mt-1 text-sm text-slate-500">選擇搜尋模式，並搭配學分、修別與學期條件快速找到課程。</p>
              </div>
              <button type="button" onClick={() => setShowSearchPanel(false)} className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200" aria-label="關閉搜尋面板">
                <HiX className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-5">
              <label className="mb-2 block text-sm font-medium text-slate-700">搜尋模式</label>
              <div className="flex w-full overflow-hidden rounded-xl border border-slate-300 bg-white shadow-sm">
                <button
                  type="button"
                  onClick={() => setDraftSearchMode('semantic')}
                  className={`min-w-0 flex-1 px-4 py-2.5 text-sm font-medium transition ${draftSearchMode === 'semantic' ? 'bg-primary-900 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  關鍵字向量搜尋
                </button>
                <button
                  type="button"
                  onClick={() => setDraftSearchMode('keyword')}
                  className={`min-w-0 flex-1 border-l border-slate-200 px-4 py-2.5 text-sm font-medium transition ${draftSearchMode === 'keyword' ? 'border-l-primary-900 bg-primary-900 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  一般文字搜尋
                </button>
              </div>
            </div>
            <div className="mt-5">
              <label className="mb-2 block text-sm font-medium text-slate-700">{draftSearchMode === 'semantic' ? '搜尋關鍵字' : '搜尋文字'}</label>
              <div className="relative">
                <HiSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={draftSearchQuery}
                  onChange={(event) => setDraftSearchQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      applySearchFilters();
                    }
                  }}
                  placeholder={draftSearchMode === 'semantic' ? '例如：程式、Python、資料分析' : '例如：機器學習'}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
                />
              </div>
              {hasDraftSearchQuery ? (
                <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${!hasDraftChanges && draftSearchMode === 'semantic' && semanticMode === 'fallback' ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
                  {hasDraftChanges
                    ? '條件尚未套用；按下「套用條件」後才會搜尋。'
                    : draftSearchMode === 'semantic'
                      ? semanticLoading
                        ? '正在使用 ncu_courses_ug / ncu_courses_grad 進行 Qdrant 關鍵字向量搜尋...'
                        : semanticMode === 'semantic'
                          ? `目前使用 Qdrant 關鍵字向量搜尋，找到 ${filteredCourses.length} 門課。`
                          : semanticMessage || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。'
                      : `目前使用一般文字搜尋，找到 ${filteredCourses.length} 門課。`}
                </div>
              ) : null}
            </div>

            <div className="mt-5 space-y-5">
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">修別</label>
                <div className="flex flex-wrap gap-2">
                  {typeOptions.map((option) => (
                    <FilterPill key={option} label={option} active={draftSelectedTypes.includes(option)} onClick={() => toggleValue(option, setDraftSelectedTypes)} />
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">學分</label>
                <div className="flex flex-wrap gap-2">
                  {creditOptions.map((option) => (
                    <FilterPill key={option} label={`${option} 學分`} active={draftSelectedCredits.includes(option)} onClick={() => toggleValue(option, setDraftSelectedCredits)} />
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">學期</label>
                <div className="flex flex-wrap gap-2">
                  {semesterOptions.map((option) => (
                    <FilterPill key={option} label={option} active={draftSelectedSemesters.includes(option)} onClick={() => toggleValue(option, setDraftSelectedSemesters)} />
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button type="button" onClick={clearDraftFilters} className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
                清除篩選
              </button>
              <button type="button" onClick={applySearchFilters} className="flex-1 rounded-xl bg-primary-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-primary-800">
                套用條件
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {compareOpen && compareCourses.length > 0 ? (
        <CourseCompareModal courses={compareCourses} onClose={() => setCompareOpen(false)} onRemove={removeCompareCourse} onClear={clearCompareCourses} />
      ) : null}
    </>
  );
}
