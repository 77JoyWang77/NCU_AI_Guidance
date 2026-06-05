/** 學院正典順序（所有頁面共用） */
export const COLLEGE_ORDER = [
  '文學院',
  '理學院',
  '工學院',
  '管理學院',
  '資訊電機學院',
  '地球科學學院',
  '客家學院',
  '生醫理工學院',
] as const;

export type CollegeName = (typeof COLLEGE_ORDER)[number];

/** 系所 → 學院 對照表 */
export const DEPT_TO_COLLEGE: Record<string, string> = {
  // 文學院
  '文學院學士班':           '文學院',
  '中國文學系':             '文學院',
  '英美語文學系':           '文學院',
  '法國語文學系':           '文學院',
  // 理學院
  '理學院學士班':           '理學院',
  '化學學系':               '理學院',
  '物理學系':               '理學院',
  '數學系':                 '理學院',
  '光電科學與工程學系':     '理學院',
  '光電科學研究中心':       '理學院',
  '天文研究所':             '理學院',
  '統計研究所':             '理學院',
  // 工學院
  '工學院學士班':           '工學院',
  '土木工程學系':           '工學院',
  '機械工程學系':           '工學院',
  '化學工程與材料工程學系': '工學院',
  '材料科學與工程研究所':   '工學院',
  '營建管理研究所':         '工學院',
  '環境工程研究所':         '工學院',
  '能源工程研究所':         '工學院',
  // 管理學院
  '經濟學系':               '管理學院',
  '企業管理學系':           '管理學院',
  '財務金融學系':           '管理學院',
  '資訊管理學系':           '管理學院',
  // 資訊電機學院
  '資訊電機學院學士班':     '資訊電機學院',
  '電機工程學系':           '資訊電機學院',
  '資訊工程學系':           '資訊電機學院',
  '通訊工程學系':           '資訊電機學院',
  '網路學習科技研究所':     '資訊電機學院',
  // 地球科學學院
  '地球科學學院學士班':     '地球科學學院',
  '地球科學學系':           '地球科學學院',
  '大氣科學學系':           '地球科學學院',
  '太空科學與工程學系':     '地球科學學院',
  '太空及遙測研究中心':     '地球科學學院',
  '太空科學與工程研究所':   '地球科學學院',
  '太空科學與科技研究中心': '地球科學學院',
  '應用地質研究所':         '地球科學學院',
  '水文與海洋科學研究所':   '地球科學學院',
  // 客家學院
  '客家語文暨社會科學學系': '客家學院',
  // 生醫理工學院
  '生命科學系':             '生醫理工學院',
  '生醫科學與工程學系':     '生醫理工學院',
  '系統生物與生物資訊研究所': '生醫理工學院',
  '認知神經科學研究所':     '生醫理工學院',
};

export function getDeptCollege(dept: string): string {
  return DEPT_TO_COLLEGE[dept] ?? '未分類單位';
}

/**
 * 系所排序優先級：
 *   0 學系   — 名稱含「學系」，或末字為「系」且無「研究」
 *   1 學士班 — 名稱含「學士班」
 *   2 學院   — 名稱含「學院」但不含「系」「班」（學院附設課程等）
 *   3 研究所 — 名稱含「研究所」（ProjectsPage 才有）
 *   4 其他   — 中心、處室、師資培育中心 等
 */
export function deptSortKey(name: string): number {
  if (name.includes('學系') || (name.endsWith('系') && !name.includes('研究'))) return 0;
  if (name.includes('學士班')) return 1;
  if (name.includes('學院') && !name.includes('系') && !name.includes('班')) return 2;
  if (name.includes('研究所')) return 3;
  return 4;
}

/** 單一學院內的系所排序：學系 → 學士班 → 研究所，同類內按 zh-Hant */
export function sortDeptsInCollege(depts: string[]): string[] {
  return [...depts].sort((a, b) => {
    const ka = deptSortKey(a), kb = deptSortKey(b);
    if (ka !== kb) return ka - kb;
    return a.localeCompare(b, 'zh-Hant');
  });
}

/** 跨學院排序：依正典學院順序 → 學系/學士班/研究所 → zh-Hant */
export function sortDeptsByCollegeOrder(depts: string[]): string[] {
  return [...depts].sort((a, b) => {
    const ca = getDeptCollege(a), cb = getDeptCollege(b);
    const ia = COLLEGE_ORDER.indexOf(ca as CollegeName);
    const ib = COLLEGE_ORDER.indexOf(cb as CollegeName);
    const ra = ia === -1 ? COLLEGE_ORDER.length : ia;
    const rb = ib === -1 ? COLLEGE_ORDER.length : ib;
    if (ra !== rb) return ra - rb;
    const ka = deptSortKey(a), kb = deptSortKey(b);
    if (ka !== kb) return ka - kb;
    return a.localeCompare(b, 'zh-Hant');
  });
}
