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

  const parseIntensity = (intensity: string): number => {
    const match = intensity.match(/\((\d+)\)/);
    return match ? parseInt(match[1]) : 0;
  };

  const getIntensityColor = (value: number): string => {
    if (value >= 5) return 'bg-red-500';
    if (value >= 4) return 'bg-orange-500';
    if (value >= 3) return 'bg-yellow-500';
    if (value >= 2) return 'bg-blue-500';
    return 'bg-gray-400';
  };

  return (
    <>
      <div className="space-y-3 md:hidden">
        {abilities.map((ability, index) => {
          const intensityValue = parseIntensity(ability.intensity);
          const colorClass = getIntensityColor(intensityValue);

          return (
            <div key={`${ability.ability_name}-${index}`} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="space-y-1">
                <div className="text-xs font-medium tracking-wide text-gray-500">核心能力</div>
                <div className="text-sm font-semibold leading-6 text-gray-900 break-words">{ability.ability_name}</div>
              </div>

              <div className="mt-4 space-y-2">
                <div className="text-xs font-medium tracking-wide text-gray-500">強度指數</div>
                <div className="flex items-center gap-3">
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-gray-200">
                    <div
                      className={`h-full ${colorClass} transition-all duration-300`}
                      style={{ width: `${intensityValue * 20}%` }}
                    ></div>
                  </div>
                  <span className="shrink-0 text-xs font-medium text-gray-600 whitespace-nowrap">{ability.intensity}</span>
                </div>
              </div>

              <div className="mt-4 space-y-1">
                <div className="text-xs font-medium tracking-wide text-gray-500">評量方式</div>
                <div className="text-sm leading-7 text-gray-700 break-words">{ability.evaluation || '無'}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full table-fixed rounded-lg border border-gray-200 bg-white" style={{ minWidth: '28rem' }}>
          <colgroup>
            <col className="w-[40%]" />
            <col className="w-[22%]" />
            <col className="w-[38%]" />
          </colgroup>
          <thead className="bg-gray-50">
            <tr>
              <th className="border-b px-4 py-3 text-left text-sm font-semibold text-gray-700">核心能力</th>
              <th className="border-b px-4 py-3 text-left text-sm font-semibold text-gray-700">強度指數</th>
              <th className="border-b px-4 py-3 text-left text-sm font-semibold text-gray-700">評量方式</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {abilities.map((ability, index) => {
              const intensityValue = parseIntensity(ability.intensity);
              const colorClass = getIntensityColor(intensityValue);

              return (
                <tr key={index} className="transition-colors hover:bg-gray-50">
                  <td className="break-words px-4 py-3 text-sm text-gray-900">{ability.ability_name}</td>
                  <td className="px-4 py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <div className="h-2 min-w-[2.5rem] flex-1 overflow-hidden rounded-full bg-gray-200">
                        <div
                          className={`h-full ${colorClass} transition-all duration-300`}
                          style={{ width: `${intensityValue * 20}%` }}
                        ></div>
                      </div>
                      <span className="whitespace-nowrap text-xs text-gray-600">{ability.intensity}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{ability.evaluation || '無'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
};

export default CoreAbilityTable;
