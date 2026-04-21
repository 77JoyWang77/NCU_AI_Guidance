import os
import json
import re

def extract_pdf_metadata(pdf_dir):
    """掃描PDF檔案並提取元資料"""
    projects = []
    project_id = 1

    # 遍歷所有科系資料夾
    for department in os.listdir(pdf_dir):
        department_path = os.path.join(pdf_dir, department)

        if not os.path.isdir(department_path):
            continue

        # 遍歷該科系的所有PDF檔案
        for filename in os.listdir(department_path):
            if not filename.endswith('.pdf'):
                continue

            # 解析檔案名稱
            # 格式：學年度-計畫類型-類別_學生姓名_題目.pdf
            try:
                # 移除.pdf後綴
                name_without_ext = filename[:-4]

                # 分割基本部分
                parts = name_without_ext.split('_')
                if len(parts) < 3:
                    continue

                # 提取學年度和類別
                prefix = parts[0]  # 例如：104-2815-C-008-007-E
                prefix_parts = prefix.split('-')
                year = prefix_parts[0]  # 學年度
                type_code = prefix_parts[-1]  # E/H/M/B

                # 提取學生姓名和題目
                student_name = parts[1]
                title = '_'.join(parts[2:])  # 題目可能包含底線

                # 建立專案物件
                project = {
                    'id': f'proj{project_id:03d}',
                    'year': year,
                    'type': type_code,
                    'department': department,
                    'studentName': student_name,
                    'title': title,
                    'pdfPath': os.path.join(department, filename)
                }

                projects.append(project)
                project_id += 1

            except Exception as e:
                print(f'解析失敗: {filename} - {e}')
                continue

    return projects

if __name__ == '__main__':
    # PDF資料夾路徑
    pdf_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw', 'projects', '104-114')

    # 提取元資料
    print('開始掃描PDF檔案...')
    projects = extract_pdf_metadata(pdf_dir)
    print(f'共找到 {len(projects)} 個專案')

    # 儲存為JSON
    output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'processed', 'projects.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)

    print(f'已儲存至: {output_path}')

    # 顯示一些範例
    print('\n前5個專案範例：')
    for p in projects[:5]:
        print(f'  [{p["year"]}] {p["studentName"]} - {p["title"][:50]}...')
