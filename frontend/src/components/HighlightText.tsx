import React from 'react';

interface HighlightTextProps {
  text: string;
  keyword: string;
  className?: string;
}

/**
 * 关键词高亮组件
 * 在文本中高亮显示匹配的关键词
 */
const HighlightText: React.FC<HighlightTextProps> = ({ text, keyword, className = '' }) => {
  if (!keyword || !text) {
    return <span className={className}>{text}</span>;
  }

  // 转义正则表达式特殊字符
  const escapeRegExp = (string: string) => {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  };

  // 创建正则表达式，不区分大小写
  const regex = new RegExp(`(${escapeRegExp(keyword)})`, 'gi');
  const parts = text.split(regex);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        regex.test(part) ? (
          <mark
            key={index}
            className="bg-yellow-200 text-gray-900 font-medium px-0.5 rounded"
          >
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        )
      )}
    </span>
  );
};

export default HighlightText;
