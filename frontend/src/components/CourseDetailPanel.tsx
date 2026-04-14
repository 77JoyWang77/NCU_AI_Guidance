import React from 'react';
import {
  HiBookOpen,
  HiCalendar,
  HiClock,
  HiDocumentText,
  HiExternalLink,
  HiFlag,
  HiLocationMarker,
  HiTag,
  HiUser,
  HiUserGroup,
} from 'react-icons/hi';
import type { Course } from '../types';
import CoreAbilityTable from './CoreAbilityTable';
import HighlightText from './HighlightText';

interface CourseDetailPanelProps {
  course: Course | null;
  searchKeyword?: string;
}

const splitFields = (value?: string | null) =>
  (value ?? '')
    .split(/[、,;；／/]/)
    .map((item) => item.trim())
    .filter(Boolean);

const CourseDetailPanel: React.FC<CourseDetailPanelProps> = ({ course, searchKeyword = '' }) => {
  if (!course) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50">
        <div className="text-center text-gray-500">
          <HiBookOpen className="mx-auto mb-4 h-16 w-16 text-gray-400" />
          <p className="text-lg font-medium">請選擇一門課程查看詳情</p>
          <p className="mt-2 text-sm">從左側列表中選擇課程</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-primary-200 bg-gradient-to-br from-primary-50 via-primary-100 to-primary-200 p-5">
        <h2 className="mb-1.5 text-xl font-bold leading-snug text-gray-900">
          <HighlightText text={course.course_name_zh} keyword={searchKeyword} />
        </h2>
        <p className="mb-3 text-sm text-gray-600">
          <HighlightText text={course.course_name_en} keyword={searchKeyword} />
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="rounded-full border border-primary-200 bg-white/80 px-3 py-1 text-sm font-medium text-gray-700">
            {course.course_system || '未提供學制資訊'}
          </span>
          <span className="rounded-full border border-primary-200 bg-white/80 px-3 py-1 text-sm font-medium text-gray-700">
            {course.credits} 學分
          </span>
          <span
            className={`rounded-full px-3 py-1 text-sm font-medium ${
              (course.required_elective || '').trim() === '必修'
                ? 'border border-red-200 bg-red-100 text-red-800'
                : 'border border-green-200 bg-green-100 text-green-800'
            }`}
          >
            {course.required_elective || '未提供類型'}
          </span>
          <span className="rounded-full border border-primary-200 bg-white/80 px-3 py-1 text-sm font-medium text-gray-700">
            {course.semester_display || '未提供學期'}
          </span>
        </div>
      </div>

      <div className="space-y-5 p-5">
        {course.course_objective ? (
          <Section icon={<HiFlag className="h-5 w-5" />} title="課程目標">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              <HighlightText text={course.course_objective} keyword={searchKeyword} />
            </p>
          </Section>
        ) : null}

        {course.course_content ? (
          <Section icon={<HiDocumentText className="h-5 w-5" />} title="課程內容">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              <HighlightText text={course.course_content} keyword={searchKeyword} />
            </p>
          </Section>
        ) : null}

        {course.course_field ? (
          <Section icon={<HiTag className="h-5 w-5" />} title="課程領域">
            <div className="flex flex-wrap gap-2">
              {splitFields(course.course_field).map((field) => (
                <span key={field} className="rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-sm font-medium text-primary-700">
                  <HighlightText text={field} keyword={searchKeyword} />
                </span>
              ))}
            </div>
          </Section>
        ) : null}

        {course.core_abilities && course.core_abilities.length > 0 ? (
          <Section icon={<HiUserGroup className="h-5 w-5" />} title="核心能力">
            <CoreAbilityTable abilities={course.core_abilities} />
          </Section>
        ) : null}

        {course.distribution_conditions && course.distribution_conditions.length > 0 ? (
          <Section icon={<HiUserGroup className="h-5 w-5" />} title="分發條件">
            <div className="space-y-2">
              {course.distribution_conditions.map((condition, index) => (
                <div key={index} className="flex gap-3 rounded-lg border border-primary-100 bg-primary-50 p-3">
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary-500 text-sm font-medium text-white shadow-sm">
                    {condition.priority}
                  </span>
                  <p className="text-sm leading-relaxed text-gray-700">
                    <HighlightText text={condition.condition} keyword={searchKeyword} />
                  </p>
                </div>
              ))}
            </div>
          </Section>
        ) : null}

        <div className="grid grid-cols-1 gap-2 border-t pt-3 md:grid-cols-2">
          <InfoItem icon={<HiUser className="h-5 w-5" />} label="授課教師">
            <HighlightText text={course.instructor || '未提供'} keyword={searchKeyword} />
          </InfoItem>
          {course.class_time ? (
            <InfoItem icon={<HiClock className="h-5 w-5" />} label="上課時間">
              {course.class_time}
            </InfoItem>
          ) : null}
          {course.classroom ? (
            <InfoItem icon={<HiLocationMarker className="h-5 w-5" />} label="上課地點">
              {course.classroom}
            </InfoItem>
          ) : null}
          {course.weeks ? (
            <InfoItem icon={<HiCalendar className="h-5 w-5" />} label="週數">
              {course.weeks} 週
            </InfoItem>
          ) : null}
          {course.teaching_method ? (
            <InfoItem icon={<HiDocumentText className="h-5 w-5" />} label="教學方式">
              {course.teaching_method}
            </InfoItem>
          ) : null}
          {course.office_hours ? (
            <InfoItem icon={<HiClock className="h-5 w-5" />} label="Office Hours">
              {course.office_hours}
            </InfoItem>
          ) : null}
        </div>

        {course.textbooks ? (
          <Section icon={<HiBookOpen className="h-5 w-5" />} title="教材與參考書">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              <HighlightText text={course.textbooks} keyword={searchKeyword} />
            </p>
          </Section>
        ) : null}

        {course.grading ? (
          <Section icon={<HiDocumentText className="h-5 w-5" />} title="評分方式">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">{course.grading}</p>
          </Section>
        ) : null}

        {course.note ? (
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
            <p className="text-sm text-gray-700">
              <span className="font-medium">備註：</span>
              <HighlightText text={course.note} keyword={searchKeyword} />
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 border-t pt-3">
          {course.distribution_link ? (
            <a
              href={course.distribution_link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg bg-primary-500 px-4 py-2 text-white transition-colors hover:bg-primary-600"
            >
              <HiExternalLink className="h-5 w-5" />
              <span>查看分發資訊</span>
            </a>
          ) : null}
          {course.outline_link ? (
            <a
              href={course.outline_link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg bg-primary-500 px-4 py-2 text-white transition-colors hover:bg-primary-600"
            >
              <HiExternalLink className="h-5 w-5" />
              <span>查看課程大綱</span>
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const Section: React.FC<{ icon: React.ReactNode; title: string; children: React.ReactNode }> = ({ icon, title, children }) => (
  <div className="space-y-2">
    <div className="flex items-center gap-2 text-gray-800">
      <div className="shrink-0 text-primary-600">{icon}</div>
      <h3 className="text-base font-semibold">{title}</h3>
    </div>
    <div>{children}</div>
  </div>
);

const InfoItem: React.FC<{ icon: React.ReactNode; label: string; children: React.ReactNode }> = ({ icon, label, children }) => (
  <div className="flex items-start gap-2 text-sm">
    <div className="mt-0.5 text-gray-400">{icon}</div>
    <div>
      <span className="text-gray-500">{label}：</span>
      <span className="text-gray-900">{children}</span>
    </div>
  </div>
);

export default CourseDetailPanel;
