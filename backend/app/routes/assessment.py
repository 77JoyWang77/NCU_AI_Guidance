from fastapi import APIRouter, Query
from typing import List
import json
import os
import csv
from app.models.schemas import (
    AssessmentMode,
    Question,
    SubmitAnswersRequest,
    AssessmentResult,
    DepartmentScore,
    TagScore,
    AdmissionCriteria,
    SubjectSelectionRequest
)

router = APIRouter()

# 載入量表題目
def load_questions():
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'processed', 'assessment_questions.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 載入學測篩選標準
def load_admission_criteria():
    csv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'raw', 'admission', 'ncu_caac.csv')
    criteria_list = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            criteria_list.append(AdmissionCriteria(
                dept_code=row['系所代碼'],
                dept_name=row['系所名稱'],
                quota=int(row['招收人數']),
                chinese_required=int(row['國_採計']),
                english_required=int(row['英_採計']),
                math_a_required=int(row['數A_採計']),
                math_b_required=int(row['數B_採計']),
                social_required=int(row['社_採計']),
                science_required=int(row['自_採計']),
                chinese_standard=row.get('國_檢定'),
                english_standard=row.get('英_檢定'),
                math_a_standard=row.get('數A_檢定'),
                math_b_standard=row.get('數B_檢定'),
                social_standard=row.get('社_檢定'),
                science_standard=row.get('自_檢定'),
                english_listening=row.get('英聽'),
                sum_criteria=row.get('相加項')
            ))

    return criteria_list

@router.get("/questions", response_model=List[Question])
async def get_questions(mode: AssessmentMode = Query(..., description="Assessment mode: grade1, grade2, or grade3")):
    """
    取得科系興趣量表題目
    - grade1: 高一模式（文組 vs 理組，30題）
    - grade2: 高二模式（細分科系，各科系5題）
    - grade3: 高三模式（結合學測，各科系5題）
    """
    all_questions = load_questions()

    # 依模式篩選題目
    if mode == AssessmentMode.GRADE1:
        # 高一：回傳文組和理組的題目
        return [q for q in all_questions if q['mode'] == 'grade1']
    elif mode == AssessmentMode.GRADE2:
        # 高二：回傳所有科系的題目
        return [q for q in all_questions if q['mode'] == 'grade2']
    else:  # grade3
        # 高三：回傳所有科系的題目（後續可加入學測篩選）
        return [q for q in all_questions if q['mode'] == 'grade3']

@router.post("/submit", response_model=AssessmentResult)
async def submit_answers(request: SubmitAnswersRequest):
    """
    提交答案並取得推薦結果
    """
    all_questions = load_questions()
    question_dict = {q['id']: q for q in all_questions}

    # 統計各科系得分
    department_scores = {}
    tag_scores = {}

    for answer in request.answers:
        question = question_dict.get(answer.questionId)
        if not question:
            continue

        department = question['department']
        score = answer.score

        # 累加科系得分
        if department not in department_scores:
            department_scores[department] = {
                'total': 0,
                'count': 0,
                'tags': set()
            }
        department_scores[department]['total'] += score
        department_scores[department]['count'] += 1
        department_scores[department]['tags'].update(question['tags'])

        # 累加標籤得分
        for tag in question['tags']:
            if tag not in tag_scores:
                tag_scores[tag] = 0
            tag_scores[tag] += score

    # 計算平均分並排序
    department_results = []
    for dept, data in department_scores.items():
        avg_score = data['total'] / data['count'] if data['count'] > 0 else 0

        # 取得學院資訊（簡化處理）
        college = get_college_for_department(dept)

        department_results.append(DepartmentScore(
            name=dept,
            college=college,
            score=round(avg_score, 2),
            matchedTags=list(data['tags'])
        ))

    # 依得分降序排序
    department_results.sort(key=lambda x: x.score, reverse=True)

    # 整理標籤得分
    tag_results = [
        TagScore(tag=tag, score=round(score, 2))
        for tag, score in tag_scores.items()
    ]
    tag_results.sort(key=lambda x: x.score, reverse=True)

    return AssessmentResult(
        departments=department_results[:15],  # 回傳前15個推薦
        tagScores=tag_results[:20]  # 回傳前20個標籤
    )

def get_college_for_department(department: str) -> str:
    """根據科系名稱回傳學院名稱"""
    college_mapping = {
        # 文學院
        "中國文學系": "文學院",
        "英美語文學系": "文學院",
        "法國語文學系": "文學院",
        "文學院學士班": "文學院",

        # 理學院
        "化學學系": "理學院",
        "物理學系": "理學院",
        "數學系": "理學院",
        "光電科學與工程學系": "理學院",
        "理學院學士班": "理學院",

        # 管理學院
        "經濟學系": "管理學院",
        "企業管理學系": "管理學院",
        "財務金融學系": "管理學院",
        "資訊管理學系": "管理學院",

        # 地球科學學院
        "地球科學學系": "地球科學學院",
        "太空科學與工程學系": "地球科學學院",
        "大氣科學學系": "地球科學學院",
        "地球科學學士班": "地球科學學院",

        # 客家學院
        "客家語文暨社會科學學系": "客家學院",

        # 資訊電機學院
        "電機工程學系": "資訊電機學院",
        "資訊工程學系": "資訊電機學院",
        "通訊工程學系": "資訊電機學院",
        "資訊電機學院學士班": "資訊電機學院",

        # 生醫理工學院
        "生命科學系": "生醫理工學院",
        "生醫科學與工程學系": "生醫理工學院",

        # 工學院
        "土木工程學系": "工學院",
        "化學工程與材料工程學系": "工學院",
        "機械工程學系": "工學院",
        "工學院學士班": "工學院",
    }

    return college_mapping.get(department, "其他")

@router.get("/admission-criteria", response_model=List[AdmissionCriteria])
async def get_admission_criteria():
    """
    取得所有學測篩選標準
    """
    return load_admission_criteria()

@router.post("/filter-by-subjects")
async def filter_departments_by_subjects(request: SubjectSelectionRequest):
    """
    根據選擇的學測科目篩選科系
    """
    all_criteria = load_admission_criteria()

    # 建立科目對應表
    subject_map = {
        'chinese': 'chinese_required',
        'english': 'english_required',
        'math_a': 'math_a_required',
        'math_b': 'math_b_required',
        'social': 'social_required',
        'science': 'science_required'
    }

    # 篩選符合條件的科系：只要科系採計的科目在使用者選擇的科目中即可
    matching_depts = []
    for criteria in all_criteria:
        required_subjects = []

        if criteria.chinese_required == 1:
            required_subjects.append('chinese')
        if criteria.english_required == 1:
            required_subjects.append('english')
        if criteria.math_a_required == 1:
            required_subjects.append('math_a')
        if criteria.math_b_required == 1:
            required_subjects.append('math_b')
        if criteria.social_required == 1:
            required_subjects.append('social')
        if criteria.science_required == 1:
            required_subjects.append('science')

        # 檢查科系要求的科目是否都在使用者選擇的科目中
        if all(subj in request.subjects for subj in required_subjects):
            matching_depts.append(criteria.dept_name)

    return {"departments": matching_depts}
