import React from 'react';
import type { Course } from '../types';
import CoreAbilityTable from './CoreAbilityTable';
import HighlightText from './HighlightText';
import {
  HiBookOpen,
  HiUser,
  HiCalendar,
  HiLocationMarker,
  HiFlag,
  HiDocumentText,
  HiTag,
  HiUserGroup,
  HiClock,
  HiExternalLink,
} from 'react-icons/hi';

interface CourseDetailPanelProps {
  course: Course | null;
  searchKeyword?: string;
}

/**
 * 课程详情面板组件
 * 在右侧显示课程的完整信息
 */
const CourseDetailPanel: React.FC<CourseDetailPanelProps> = ({ course, searchKeyword = '' }) => {
  if (!course) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
        <div className="text-center text-gray-500">
          <HiBookOpen className="mx-auto h-16 w-16 mb-4 text-gray-400" />
          <p className="text-lg font-medium">請選擇一門課程查看詳情</p>
          <p className="text-sm mt-2">從左側列表中選擇課程</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* 課程基本資訊 - 頂部卡片 */}
      <div className="bg-gradient-to-br from-primary-50 via-primary-100 to-primary-200 p-5 border-b border-primary-200">
        <h2 className="text-xl font-bold mb-1.5 text-gray-900 leading-snug">
          <HighlightText text={course.course_name_zh} keyword={searchKeyword} />
        </h2>
        <p className="text-gray-600 text-sm mb-3">
          <HighlightText text={course.course_name_en} keyword={searchKeyword} />
        </p>
        <div className="flex flex-wrap gap-2 mt-4">
          <span className="bg-white/80 px-3 py-1 rounded-full text-sm text-gray-700 font-medium border border-primary-200">
            {course.course_system || '學士班'}
          </span>
          <span className="bg-white/80 px-3 py-1 rounded-full text-sm text-gray-700 font-medium border border-primary-200">
            {course.credits} 學分
          </span>
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              course.required_elective === '必修'
                ? 'bg-red-100 text-red-800 border border-red-200'
                : 'bg-green-100 text-green-800 border border-green-200'
            }`}
          >
            {course.required_elective}
          </span>
          <span className="bg-white/80 px-3 py-1 rounded-full text-sm text-gray-700 font-medium border border-primary-200">
            {course.semester_display}
          </span>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* 課程目標 */}
        {course.course_objective && (
          <Section icon={<HiFlag className="h-5 w-5" />} title="課程目標">
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
              <HighlightText text={course.course_objective} keyword={searchKeyword} />
            </p>
          </Section>
        )}

        {/* 授課內容 */}
        {course.course_content && (
          <Section icon={<HiDocumentText className="h-5 w-5" />} title="授課內容">
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
              <HighlightText text={course.course_content} keyword={searchKeyword} />
            </p>
          </Section>
        )}

        {/* 課程領域 */}
        {course.course_field && (
          <Section icon={<HiTag className="h-5 w-5" />} title="課程領域">
            <div className="flex flex-wrap gap-2">
              {course.course_field.split('、').map((field, index) => (
                <span
                  key={index}
                  className="bg-primary-50 text-primary-700 px-3 py-1 rounded-full text-sm font-medium border border-primary-200"
                >
                  <HighlightText text={field.trim()} keyword={searchKeyword} />
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* 核心能力 */}
        {course.core_abilities && course.core_abilities.length > 0 && (
          <Section icon={<HiUserGroup className="h-5 w-5" />} title="核心能力培養">
            <CoreAbilityTable abilities={course.core_abilities} />
          </Section>
        )}

        {/* 分發條件 */}
        {course.distribution_conditions && course.distribution_conditions.length > 0 && (
          <Section icon={<HiUserGroup className="h-5 w-5" />} title="選課條件">
            <div className="space-y-2">
              {course.distribution_conditions.map((condition, index) => (
                <div key={index} className="flex gap-3 p-3 bg-primary-50 rounded-lg border border-primary-100">
                  <span className="flex-shrink-0 w-8 h-8 bg-primary-500 text-white rounded-full flex items-center justify-center text-sm font-medium shadow-sm">
                    {condition.priority}
                  </span>
                  <p className="text-sm text-gray-700 leading-relaxed">
                    <HighlightText text={condition.condition} keyword={searchKeyword} />
                  </p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* 其他資訊 - 小標籤形式 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-3 border-t">
          <InfoItem icon={<HiUser className="h-5 w-5" />} label="授課教師">
            <HighlightText text={course.instructor} keyword={searchKeyword} />
          </InfoItem>
          {course.class_time && (
            <InfoItem icon={<HiClock className="h-5 w-5" />} label="上課時間">
              {course.class_time}
            </InfoItem>
          )}
          {course.classroom && (
            <InfoItem icon={<HiLocationMarker className="h-5 w-5" />} label="教室">
              {course.classroom}
            </InfoItem>
          )}
          {course.weeks && (
            <InfoItem icon={<HiCalendar className="h-5 w-5" />} label="授課週數">
              {course.weeks} 週
            </InfoItem>
          )}
          {course.teaching_method && (
            <InfoItem icon={<HiDocumentText className="h-5 w-5" />} label="授課方式">
              {course.teaching_method}
            </InfoItem>
          )}
          {course.office_hours && (
            <InfoItem icon={<HiClock className="h-5 w-5" />} label="辦公時間">
              {course.office_hours}
            </InfoItem>
          )}
        </div>

        {/* 教科書與評分 */}
        {course.textbooks && (
          <Section icon={<HiBookOpen className="h-5 w-5" />} title="教科書/參考書">
            <p className="text-sm text-gray-700 leading-relaxed">
              <HighlightText text={course.textbooks} keyword={searchKeyword} />
            </p>
          </Section>
        )}

        {course.grading && (
          <Section icon={<HiDocumentText className="h-5 w-5" />} title="評量配分">
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
              {course.grading}
            </p>
          </Section>
        )}

        {/* 備註 */}
        {course.note && (
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm text-gray-700">
              <span className="font-medium">備註：</span>
              <HighlightText text={course.note} keyword={searchKeyword} />
            </p>
          </div>
        )}

        {/* 連結區 */}
        <div className="flex flex-wrap gap-2 pt-3 border-t">
          {course.distribution_link && (
            <a
              href={course.distribution_link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors shadow-sm"
            >
              <HiExternalLink className="h-5 w-5" />
              <span>分發條件詳情</span>
            </a>
          )}
          {course.outline_link && (
            <a
              href={course.outline_link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors shadow-sm"
            >
              <HiExternalLink className="h-5 w-5" />
              <span>課程綱要詳情</span>
            </a>
          )}
        </div>
      </div>
    </div>
  );
};

// 章節組件
const Section: React.FC<{
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}> = ({ icon, title, children }) => (
  <div className="space-y-2">
    <div className="flex items-center gap-2 text-gray-800">
      <div className="text-primary-600 shrink-0">{icon}</div>
      <h3 className="text-base font-semibold">{title}</h3>
    </div>
    <div>{children}</div>
  </div>
);

// 小資訊項目組件
const InfoItem: React.FC<{
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}> = ({ icon, label, children }) => (
  <div className="flex items-start gap-2 text-sm">
    <div className="text-gray-400 mt-0.5">{icon}</div>
    <div>
      <span className="text-gray-500">{label}：</span>
      <span className="text-gray-900">{children}</span>
    </div>
  </div>
);

export default CourseDetailPanel;
