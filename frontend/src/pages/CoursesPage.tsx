import { useState, useEffect, useMemo } from 'react';
import { courseAPI } from '../api/services';
import type { Course } from '../types';
import CourseDetailPanel from '../components/CourseDetailPanel';
import HighlightText from '../components/HighlightText';
import {
  HiMenu,
  HiSearch,
  HiChevronRight,
  HiChevronLeft,
  HiBookOpen,
  HiBeaker,
  HiCog,
  HiBriefcase,
  HiChip,
  HiGlobeAlt,
  HiLibrary,
  HiHeart,
  HiOfficeBuilding,
  HiFilter,
  HiX,
} from 'react-icons/hi';

// 學院排序（按重要性）
const COLLEGE_ORDER = [
  '文學院',
  '理學院',
  '工學院',
  '管理學院',
  '資訊電機學院',
  '地球科學學院',
  '客家學院',
  '生醫理工學院',
  '永續與綠能科技研究學院',
  '中心、處室',
];

// 學院圖示和顏色配置
const COLLEGE_CONFIG: Record<string, { icon: any; gradient: string; color: string }> = {
  '文學院': { icon: HiBookOpen, gradient: 'from-blue-400 to-purple-500', color: 'text-blue-600' },
  '理學院': { icon: HiBeaker, gradient: 'from-cyan-400 to-blue-500', color: 'text-cyan-600' },
  '工學院': { icon: HiCog, gradient: 'from-orange-400 to-red-500', color: 'text-orange-600' },
  '管理學院': { icon: HiBriefcase, gradient: 'from-green-400 to-emerald-500', color: 'text-green-600' },
  '資訊電機學院': { icon: HiChip, gradient: 'from-indigo-400 to-purple-600', color: 'text-indigo-600' },
  '地球科學學院': { icon: HiGlobeAlt, gradient: 'from-teal-400 to-cyan-500', color: 'text-teal-600' },
  '客家學院': { icon: HiLibrary, gradient: 'from-red-400 to-pink-500', color: 'text-red-600' },
  '生醫理工學院': { icon: HiHeart, gradient: 'from-pink-400 to-rose-500', color: 'text-pink-600' },
  '永續與綠能科技研究學院': { icon: HiGlobeAlt, gradient: 'from-green-400 to-teal-500', color: 'text-green-600' },
  '中心、處室': { icon: HiOfficeBuilding, gradient: 'from-gray-400 to-gray-500', color: 'text-gray-600' },
};

interface GroupedCourses {
  [college: string]: {
    [department: string]: Course[];
  };
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('');
  const [selectedCredits, setSelectedCredits] = useState<string>('');
  const [selectedSemester, setSelectedSemester] = useState<string>('');
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null);

  // 導航狀態
  const [showNavigation, setShowNavigation] = useState(true); // 顯示導航還是課程列表
  const [selectedCollege, setSelectedCollege] = useState<string | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);

  // 搜尋/篩選面板狀態
  const [showSearchPanel, setShowSearchPanel] = useState(false);
  const [searchMode, setSearchMode] = useState<'name' | 'detail'>('name');
  const [searchExpandedDepts, setSearchExpandedDepts] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadCourses();
  }, []);

  const loadCourses = async () => {
    try {
      setLoading(true);
      const data = await courseAPI.getCourses();
      setCourses(data);
    } catch (error) {
      console.error('載入課程失敗:', error);
    } finally {
      setLoading(false);
    }
  };

  // 按學院和系所分組
  const groupedCourses = useMemo(() => {
    const grouped: GroupedCourses = {};
    courses.forEach((course) => {
      const college = course.college || '其他';
      const department = course.department || '未分類';
      if (!grouped[college]) grouped[college] = {};
      if (!grouped[college][department]) grouped[college][department] = [];
      grouped[college][department].push(course);
    });
    return grouped;
  }, [courses]);

  // 排序學院
  const sortedColleges = useMemo(() => {
    const colleges = Object.keys(groupedCourses);
    return colleges.sort((a, b) => {
      const indexA = COLLEGE_ORDER.indexOf(a);
      const indexB = COLLEGE_ORDER.indexOf(b);
      if (indexA === -1 && indexB === -1) return a.localeCompare(b);
      if (indexA === -1) return 1;
      if (indexB === -1) return -1;
      return indexA - indexB;
    });
  }, [groupedCourses]);

  // 當前學院的系所列表
  const currentDepartments = useMemo(() => {
    if (!selectedCollege || !groupedCourses[selectedCollege]) return [];
    return Object.keys(groupedCourses[selectedCollege]).sort();
  }, [selectedCollege, groupedCourses]);

  // 當前系所的課程列表（受搜尋和篩選影響）
  const currentCourses = useMemo(() => {
    if (!selectedCollege || !selectedDepartment) return [];
    const allDeptCourses = groupedCourses[selectedCollege]?.[selectedDepartment] || [];

    let result = [...allDeptCourses];

    // 必修/選修篩選
    if (selectedType) {
      result = result.filter((c) => c.required_elective === selectedType);
    }

    // 學分數篩選
    if (selectedCredits) {
      result = result.filter((c) => c.credits === parseInt(selectedCredits));
    }

    // 學期篩選
    if (selectedSemester) {
      result = result.filter((c) => c.semester_display === selectedSemester);
    }

    // 搜尋
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (course) =>
          course.course_name_zh?.toLowerCase().includes(query) ||
          course.course_name_en?.toLowerCase().includes(query) ||
          course.instructor?.toLowerCase().includes(query) ||
          course.course_objective?.toLowerCase().includes(query) ||
          course.course_content?.toLowerCase().includes(query) ||
          course.course_field?.toLowerCase().includes(query)
      );
    }

    return result;
  }, [selectedCollege, selectedDepartment, groupedCourses, selectedType, selectedCredits, selectedSemester, searchQuery]);

  const handleCollegeClick = (college: string) => {
    setSelectedCollege(college);
    setSelectedDepartment(null);
    setSelectedCourse(null);
  };

  const handleDepartmentClick = (department: string) => {
    setSelectedDepartment(department);
    setSelectedCourse(null);
    setShowNavigation(false); // 切換到課程列表視圖
  };

  const handleCourseClick = (course: Course) => {
    setSelectedCourse(course);
  };

  const handleBackToNavigation = () => {
    setShowNavigation(true);
    setSelectedCourse(null);
  };

  const handleNavigationBack = () => {
    if (selectedDepartment) {
      setSelectedDepartment(null);
      setSelectedCourse(null);
    } else if (selectedCollege) {
      setSelectedCollege(null);
    }
  };

  const toggleDeptExpansion = (key: string) => {
    setSearchExpandedDepts(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSearchCourseClick = (course: Course) => {
    setSelectedCourse(course);
  };

  // 全域搜尋結果（跨所有課程）
  const globalSearchResults = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const query = searchQuery.toLowerCase();
    const grouped: GroupedCourses = {};
    let total = 0;
    courses.forEach(course => {
      const match = searchMode === 'name'
        ? !!(course.course_name_zh?.toLowerCase().includes(query) || course.course_name_en?.toLowerCase().includes(query))
        : !!(course.course_name_zh?.toLowerCase().includes(query) ||
             course.course_name_en?.toLowerCase().includes(query) ||
             course.instructor?.toLowerCase().includes(query) ||
             course.course_objective?.toLowerCase().includes(query) ||
             course.course_content?.toLowerCase().includes(query) ||
             course.course_field?.toLowerCase().includes(query));
      if (match) {
        const college = course.college || '其他';
        const dept = course.department || '未分類';
        if (!grouped[college]) grouped[college] = {};
        if (!grouped[college][dept]) grouped[college][dept] = [];
        grouped[college][dept].push(course);
        total++;
      }
    });
    return { grouped, total };
  }, [courses, searchQuery, searchMode]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 主要內容區 */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4"></div>
            <p className="text-gray-600">載入中...</p>
          </div>
        </div>
      ) : (
        <div className="flex gap-0 h-[calc(100vh-64px)]">
          {/* 左側區域 (40%) - 導航或課程列表 */}
          <div className="w-96 shrink-0 border-r bg-white overflow-y-auto">
            {showNavigation ? (
              // ===== 導航視圖 =====
              <div className="h-full flex flex-col">
                {/* 導航 Header */}
                <div className="flex items-center gap-3 px-3 py-2.5 border-b bg-gray-50">
                  <h2 className="text-sm font-bold text-gray-800 shrink-0">課程導航</h2>
                  <div className="relative flex-1 ml-2">
                    <HiSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => { setSearchQuery(e.target.value); setSearchExpandedDepts(new Set()); }}
                      placeholder="搜尋課程..."
                      className="w-full pl-8 pr-7 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    />
                    {searchQuery && (
                      <button
                        onClick={() => { setSearchQuery(''); setSearchExpandedDepts(new Set()); }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      >
                        <HiX className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => setShowSearchPanel(!showSearchPanel)}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm transition-colors shrink-0 ${
                      showSearchPanel || selectedType || selectedCredits || selectedSemester
                        ? 'bg-primary-100 text-primary-700'
                        : 'hover:bg-gray-200 text-gray-600'
                    }`}
                  >
                    <HiFilter className="w-4 h-4" />
                    篩選
                  </button>
                  {(selectedCollege || selectedDepartment) && !searchQuery && (
                    <button
                      onClick={handleNavigationBack}
                      className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 shrink-0"
                    >
                      <HiChevronLeft className="w-4 h-4" />
                      返回
                    </button>
                  )}
                </div>

                {/* 篩選選項 - 可展開/收合 */}
                {showSearchPanel && (
                  <div className="px-3 py-2.5 border-b bg-gray-50 space-y-2">
                    <div className="grid grid-cols-3 gap-2">
                      <select
                        value={selectedType}
                        onChange={(e) => setSelectedType(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部類型</option>
                        <option value="必修">必修</option>
                        <option value="選修">選修</option>
                      </select>
                      <select
                        value={selectedCredits}
                        onChange={(e) => setSelectedCredits(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部學分</option>
                        <option value="0">0 學分</option>
                        <option value="1">1 學分</option>
                        <option value="2">2 學分</option>
                        <option value="3">3 學分</option>
                        <option value="4">4 學分</option>
                      </select>
                      <select
                        value={selectedSemester}
                        onChange={(e) => setSelectedSemester(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部學期</option>
                        <option value="上學期">上學期</option>
                        <option value="下學期">下學期</option>
                        <option value="全年">全年</option>
                      </select>
                    </div>
                    {(selectedType || selectedCredits || selectedSemester) && (
                      <button
                        onClick={() => { setSelectedType(''); setSelectedCredits(''); setSelectedSemester(''); }}
                        className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                      >
                        清除篩選
                      </button>
                    )}
                  </div>
                )}

                {/* 搜尋結果視圖 */}
                {searchQuery && (
                  <div className="flex-1 overflow-y-auto">
                    {/* 搜尋模式切換 + 總數 */}
                    <div className="flex items-center justify-between px-3 py-2 bg-gray-100 border-b">
                      <div className="flex text-sm border border-gray-300 rounded overflow-hidden">
                        <button
                          onClick={() => setSearchMode('name')}
                          className={`px-3 py-1 ${searchMode === 'name' ? 'bg-primary-600 text-white' : 'text-gray-600 hover:bg-gray-200'}`}
                        >課程名稱</button>
                        <button
                          onClick={() => setSearchMode('detail')}
                          className={`px-3 py-1 border-l border-gray-300 ${searchMode === 'detail' ? 'bg-primary-600 text-white' : 'text-gray-600 hover:bg-gray-200'}`}
                        >詳細資訊</button>
                      </div>
                      <span className="text-sm text-gray-500">
                        共 <span className="font-semibold text-primary-700">{globalSearchResults?.total ?? 0}</span> 門
                      </span>
                    </div>
                    {globalSearchResults && globalSearchResults.total === 0 ? (
                      <div className="p-6 text-center text-gray-400 text-sm">找不到符合的課程</div>
                    ) : globalSearchResults && sortedColleges
                        .filter(c => globalSearchResults.grouped[c])
                        .map(college => {
                          const depts = globalSearchResults.grouped[college];
                          const collegeTotalCnt = Object.values(depts).reduce((s, arr) => s + arr.length, 0);
                          return (
                            <div key={college}>
                              <div className="px-3 py-1.5 bg-gray-50 border-b text-xs font-semibold text-gray-500 uppercase tracking-wide">
                                {college} · {collegeTotalCnt} 門
                              </div>
                              {Object.keys(depts).sort().map(dept => {
                                const deptCourses = depts[dept];
                                const key = `${college}::${dept}`;
                                const isExpanded = searchExpandedDepts.has(key);
                                return (
                                  <div key={dept}>
                                    <button
                                      onClick={() => toggleDeptExpansion(key)}
                                      className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 border-b text-left"
                                    >
                                      <span className="text-sm text-gray-800">{dept}</span>
                                      <div className="flex items-center gap-2 shrink-0">
                                        <span className="text-sm text-gray-400">{deptCourses.length} 門</span>
                                        <HiChevronRight className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                      </div>
                                    </button>
                                    {isExpanded && (
                                      <div className="divide-y bg-white">
                                        {deptCourses.map(course => (
                                          <button
                                            key={`${course.serial_no}-${course.course_id}`}
                                            onClick={() => handleSearchCourseClick(course)}
                                            className={`w-full px-5 py-2.5 text-left hover:bg-primary-50 transition-colors ${selectedCourse === course ? 'bg-primary-50 border-l-2 border-primary-600' : ''}`}
                                          >
                                            <div className="text-sm font-medium text-gray-900 leading-snug">
                                              <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                            </div>
                                            <div className="flex items-center gap-2 mt-0.5">
                                              <span className={`text-xs ${course.required_elective === '必修' ? 'text-red-500' : 'text-green-600'}`}>{course.required_elective}</span>
                                              <span className="text-xs text-gray-400">{course.credits} 學分</span>
                                              {course.instructor && <span className="text-xs text-gray-400 truncate">{course.instructor}</span>}
                                            </div>
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          );
                        })
                    }
                  </div>
                )}

                {/* 學院列表 */}
                {!selectedCollege && !searchQuery && (
                  <div className="flex-1 overflow-y-auto">
                    {sortedColleges.map((college) => {
                      const config = COLLEGE_CONFIG[college] || COLLEGE_CONFIG['中心、處室'];
                      const Icon = config.icon;
                      const deptCount = Object.keys(groupedCourses[college] || {}).length;
                      const courseCount = Object.values(groupedCourses[college] || {}).reduce(
                        (sum, courses) => sum + courses.length,
                        0
                      );

                      return (
                        <button
                          key={college}
                          onClick={() => handleCollegeClick(college)}
                          className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors text-left border-b"
                        >
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${config.gradient} flex items-center justify-center shadow-md`}>
                              <Icon className="w-5 h-5 text-white" />
                            </div>
                            <div>
                              <div className="font-semibold text-gray-900 text-sm">{college}</div>
                              <div className="text-xs text-gray-500">
                                {deptCount} 系所 · {courseCount} 課程
                              </div>
                            </div>
                          </div>
                          <HiChevronRight className="w-5 h-5 text-gray-400" />
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* 系所列表 */}
                {selectedCollege && !searchQuery && (
                  <div className="flex-1 overflow-y-auto">
                    <div className="px-4 py-3 bg-gradient-to-r from-primary-50 to-primary-100 border-b">
                      <div className="flex items-center gap-3">
                        {(() => {
                          const config = COLLEGE_CONFIG[selectedCollege] || COLLEGE_CONFIG['中心、處室'];
                          const Icon = config.icon;
                          return (
                            <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${config.gradient} flex items-center justify-center shadow-md`}>
                              <Icon className="w-4 h-4 text-white" />
                            </div>
                          );
                        })()}
                        <span className="font-bold text-gray-900 text-sm">{selectedCollege}</span>
                      </div>
                    </div>
                    {currentDepartments.map((department) => {
                      const courseCount = groupedCourses[selectedCollege][department].length;
                      return (
                        <button
                          key={department}
                          onClick={() => handleDepartmentClick(department)}
                          className="w-full px-4 py-3 flex items-center justify-between hover:bg-primary-50 transition-colors text-left border-b"
                        >
                          <div>
                            <div className="text-sm font-medium text-gray-900">{department}</div>
                            <div className="text-xs text-gray-500">{courseCount} 門課程</div>
                          </div>
                          <HiChevronRight className="w-5 h-5 text-gray-400" />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              // ===== 課程列表視圖 =====
              <div className="h-full flex flex-col">
                {/* 課程列表 Header */}
                <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <h2 className="text-base font-bold text-gray-900 truncate">{selectedDepartment}</h2>
                    <span className="text-sm text-gray-400 shrink-0">{currentCourses.length} 門</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => setShowSearchPanel(!showSearchPanel)}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
                        showSearchPanel || selectedType || selectedCredits || selectedSemester
                          ? 'bg-primary-100 text-primary-700'
                          : 'hover:bg-gray-200 text-gray-600'
                      }`}
                    >
                      <HiFilter className="w-4 h-4" />
                      篩選
                    </button>
                    <button
                      onClick={handleBackToNavigation}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-primary-600 hover:bg-primary-50 rounded-md transition-colors"
                    >
                      <HiMenu className="w-4 h-4" />
                      導航
                    </button>
                  </div>
                </div>

                {/* 篩選面板（課程列表視圖） */}
                {showSearchPanel && (
                  <div className="px-3 py-2.5 border-b bg-gray-50 space-y-2">
                    <div className="grid grid-cols-3 gap-2">
                      <select
                        value={selectedType}
                        onChange={(e) => setSelectedType(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部類型</option>
                        <option value="必修">必修</option>
                        <option value="選修">選修</option>
                      </select>
                      <select
                        value={selectedCredits}
                        onChange={(e) => setSelectedCredits(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部學分</option>
                        <option value="0">0 學分</option>
                        <option value="1">1 學分</option>
                        <option value="2">2 學分</option>
                        <option value="3">3 學分</option>
                        <option value="4">4 學分</option>
                      </select>
                      <select
                        value={selectedSemester}
                        onChange={(e) => setSelectedSemester(e.target.value)}
                        className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="">全部學期</option>
                        <option value="上學期">上學期</option>
                        <option value="下學期">下學期</option>
                        <option value="全年">全年</option>
                      </select>
                    </div>
                    {(selectedType || selectedCredits || selectedSemester) && (
                      <button
                        onClick={() => { setSelectedType(''); setSelectedCredits(''); setSelectedSemester(''); }}
                        className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                      >
                        清除篩選
                      </button>
                    )}
                  </div>
                )}

                {/* 課程列表內容 */}
                {currentCourses.length === 0 ? (
                  <div className="p-8 text-center text-gray-500">
                    <HiSearch className="w-10 h-10 mx-auto mb-3 text-gray-400" />
                    <p className="text-sm font-medium">找不到符合條件的課程</p>
                    <p className="text-sm mt-1 text-gray-400">請調整篩選條件</p>
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto divide-y">
                    {currentCourses.map((course) => (
                      <button
                        key={`${course.serial_no}-${course.course_id}`}
                        onClick={() => handleCourseClick(course)}
                        className={`w-full px-4 py-3 text-left hover:bg-primary-50 transition-colors ${
                          selectedCourse === course ? 'bg-primary-50 border-l-4 border-primary-600' : ''
                        }`}
                      >
                        <div className="text-sm font-semibold text-gray-900 leading-snug mb-1">
                          <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                              course.required_elective === '必修'
                                ? 'bg-red-100 text-red-700'
                                : 'bg-green-100 text-green-700'
                            }`}
                          >
                            {course.required_elective}
                          </span>
                          <span className="text-xs text-gray-500">{course.credits} 學分</span>
                          <span className="text-xs text-gray-500">{course.instructor}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 右側：課程詳情 (60%) */}
          <div className="flex-1 overflow-y-auto bg-gray-50 p-4">
            <CourseDetailPanel course={selectedCourse} searchKeyword={searchQuery} />
          </div>
        </div>
      )}
    </div>
  );
}
