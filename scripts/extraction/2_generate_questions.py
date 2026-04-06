import json
import random
import os

# 讀取 projects metadata
with open('app/mock_data/projects_metadata.json', 'r', encoding='utf-8') as f:
    projects = json.load(f)

# 科系映射（用於匹配）
dept_mapping = {
    '文學院學士班': '文學院學士班',
    '中國文學系': '中國文學系',
    '英美語文學系': '英美語文學系',
    '法國語文學系': '法國語文學系',
    '企業管理學系': '企業管理學系',
    '經濟學系': '經濟學系',
    '財務金融學系': '財務金融學系',
    '資訊管理學系': '資訊管理學系',
    '客家語文暨社會科學學系': '客家語文暨社會科學學系',
    '地球科學學系': '地球科學學系',
    '大氣科學學系': '大氣科學學系',
    '太空科學與工程學系': '太空科學與工程學系',
    '數學系': '數學系',
    '物理學系': '物理學系',
    '化學學系': '化學學系',
    '光電科學與工程學系': '光電科學與工程學系',
    '理學院學士班': '理學院學士班',
    '資訊工程學系': '資訊工程學系',
    '電機工程學系': '電機工程學系',
    '通訊工程學系': '通訊工程學系',
    '資訊電機學院學士班': '資訊電機學院學士班',
    '機械工程學系': '機械工程學系',
    '土木工程學系': '土木工程學系',
    '化學工程與材料工程學系': '化學工程與材料工程學系',
    '工學院學士班': '工學院學士班',
    '生命科學系': '生命科學系',
    '生醫科學與工程學系': '生醫科學與工程學系',
}

# 標籤庫（保留原有的標籤）
all_tags = {
    '人工智慧': ['資訊工程學系', '電機工程學系', '資訊管理學系'],
    '機器學習': ['資訊工程學系', '資訊管理學系', '數學系'],
    '程式設計': ['資訊工程學系', '電機工程學系', '資訊管理學系'],
    '數據分析': ['資訊管理學系', '經濟學系', '數學系'],
    '文學創作': ['中國文學系', '英美語文學系', '法國語文學系'],
    '語言研究': ['中國文學系', '英美語文學系', '法國語文學系', '客家語文暨社會科學學系'],
    '商業管理': ['企業管理學系', '資訊管理學系', '財務金融學系'],
    '金融分析': ['財務金融學系', '經濟學系'],
    '地質研究': ['地球科學學系'],
    '氣象分析': ['大氣科學學系'],
    '天文物理': ['物理學系', '太空科學與工程學系'],
    '化學實驗': ['化學學系', '化學工程與材料工程學系'],
    '材料科學': ['化學工程與材料工程學系', '機械工程學系'],
    '光電技術': ['光電科學與工程學系', '電機工程學系'],
    '電路設計': ['電機工程學系', '通訊工程學系'],
    '結構力學': ['土木工程學系', '機械工程學系'],
    '生物醫學': ['生命科學系', '生醫科學與工程學系'],
    '客家文化': ['客家語文暨社會科學學系'],
}

# 按科系組織 projects
projects_by_dept = {}
for project in projects:
    dept = project['department']
    if dept not in projects_by_dept:
        projects_by_dept[dept] = []
    projects_by_dept[dept].append(project)

# 生成題目
questions = []
question_id = 1

for dept, dept_projects in projects_by_dept.items():
    # 每個科系選擇1-3個project（如果有的話）
    selected_projects = random.sample(dept_projects, min(3, len(dept_projects)))

    for project in selected_projects:
        # 找出相關的標籤
        dept_tags = []
        for tag, related_depts in all_tags.items():
            if dept in related_depts:
                dept_tags.append(tag)

        # 如果沒有標籤，給一個通用標籤
        if not dept_tags:
            dept_tags = ['研究', '探索']

        # 隨機選擇2-3個標籤
        selected_tags = random.sample(dept_tags, min(3, len(dept_tags)))

        # 生成題目
        question = {
            'id': f'q{question_id:03d}',
            'mode': 'grade2',  # 預設都是 grade2
            'department': dept,
            'title': project['title'],
            'motivation': f'這個研究題目探討 {dept} 領域中的重要議題，具有實際應用價值和學術意義。',
            'method': '透過文獻回顧、實驗設計、數據分析等方法進行研究。',
            'result': '研究成果可以應用於實際場景，並對學術界有所貢獻。',
            'tags': selected_tags
        }

        questions.append(question)
        question_id += 1

# 為每個科系至少保證有一個題目（如果之前沒有）
for dept in dept_mapping.values():
    has_question = any(q['department'] == dept for q in questions)
    if not has_question:
        dept_tags = []
        for tag, related_depts in all_tags.items():
            if dept in related_depts:
                dept_tags.append(tag)

        if not dept_tags:
            dept_tags = ['研究', '探索']

        selected_tags = random.sample(dept_tags, min(2, len(dept_tags)))

        question = {
            'id': f'q{question_id:03d}',
            'mode': 'grade2',
            'department': dept,
            'title': f'{dept}研究計畫：探索新領域',
            'motivation': f'探索 {dept} 的研究方向和發展趨勢。',
            'method': '透過系統性的研究方法進行深入探討。',
            'result': '為學術界和實務界提供有價值的見解。',
            'tags': selected_tags
        }

        questions.append(question)
        question_id += 1

# 為 grade1 和 grade3 複製一些題目
grade1_questions = []
grade3_questions = []

for q in questions[:40]:  # 選擇前40個題目用於 grade1
    q_copy = q.copy()
    q_copy['mode'] = 'grade1'
    grade1_questions.append(q_copy)

for q in questions[:50]:  # 選擇前50個題目用於 grade3
    q_copy = q.copy()
    q_copy['mode'] = 'grade3'
    grade3_questions.append(q_copy)

# 合併所有題目
all_questions = grade1_questions + questions + grade3_questions

# 重新分配 ID
for i, q in enumerate(all_questions):
    q['id'] = f'q{i+1:03d}'

print(f'生成了 {len(all_questions)} 個題目')
print(f'- Grade 1: {len(grade1_questions)} 個')
print(f'- Grade 2: {len(questions)} 個')
print(f'- Grade 3: {len(grade3_questions)} 個')

# 統計每個科系的題目數量
dept_counts = {}
for q in all_questions:
    dept = q['department']
    dept_counts[dept] = dept_counts.get(dept, 0) + 1

print('\n各科系題目數量：')
for dept, count in sorted(dept_counts.items()):
    print(f'  {dept}: {count}')

# 儲存到文件
with open('app/mock_data/assessment_questions.json', 'w', encoding='utf-8') as f:
    json.dump(all_questions, f, ensure_ascii=False, indent=2)

print('\n✓ 已儲存到 app/mock_data/assessment_questions.json')
