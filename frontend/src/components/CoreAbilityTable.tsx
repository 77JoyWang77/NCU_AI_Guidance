import React from 'react';
import type { CoreAbility } from '../types';

interface CoreAbilityTableProps {
  abilities: CoreAbility[];
}

/**
 * 核心能力表格組件
 * 展示課程的核心能力、強度指數和評量方式
 */
const CoreAbilityTable: React.FC<CoreAbilityTableProps> = ({ abilities }) => {
  if (!abilities || abilities.length === 0) {
    return null;
  }

  // 解析強度指數，提取數值用於進度條
  const parseIntensity = (intensity: string): number => {
    const match = intensity.match(/\((\d+)\)/);
    return match ? parseInt(match[1]) : 0;
  };

  // 獲取強度等級的顏色
  const getIntensityColor = (value: number): string => {
    if (value >= 5) return 'bg-red-500';
    if (value >= 4) return 'bg-orange-500';
    if (value >= 3) return 'bg-yellow-500';
    if (value >= 2) return 'bg-blue-500';
    return 'bg-gray-400';
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full table-fixed bg-white border border-gray-200 rounded-lg">
        <colgroup>
          <col className="w-2/5" />
          <col className="w-1/5" />
          <col className="w-2/5" />
        </colgroup>
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 border-b">
              核心能力
            </th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 border-b">
              強度指數
            </th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 border-b">
              評量方式
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {abilities.map((ability, index) => {
            const intensityValue = parseIntensity(ability.intensity);
            const colorClass = getIntensityColor(intensityValue);

            return (
              <tr key={index} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 text-sm text-gray-900 break-words">
                  {ability.ability_name}
                </td>
                <td className="px-4 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-24 shrink-0 bg-gray-200 rounded-full h-2.5 overflow-hidden">
                      <div
                        className={`h-full ${colorClass} transition-all duration-300`}
                        style={{ width: `${intensityValue * 20}%` }}
                      ></div>
                    </div>
                    <span className="text-xs text-gray-600 whitespace-nowrap">
                      {ability.intensity}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  {ability.evaluation || '無'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default CoreAbilityTable;
