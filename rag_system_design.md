# 高中生課程諮詢RAG系統 - 完整設計

## 一、高中生需求分析

### 1.1 核心需求場景

#### 升學規劃類
- **科系探索**: "資工系都要上什麼課？"、"會計系課程難不難？"
- **興趣匹配**: "我喜歡寫程式，適合哪些科系？"、"對語言有興趣可以選什麼系？"
- **課程負擔**: "哪個系必修學分最多？"、"XX系課業壓力大嗎？"
- **未來發展**: "企管系畢業後可以做什麼？"

#### 課程理解類
- **課程內容**: "微積分都在教什麼？"、"普通化學和有機化學差在哪？"
- **先修要求**: "要先修什麼課才能上XX課？"
- **難度評估**: "哪些課比較容易過？"、"大一必修有哪些？"
- **教師風格**: "XX老師教得好嗎？"、"哪個老師比較涼？"

#### 選課規劃類
- **時間安排**: "星期五有哪些課？"、"早八的課有哪些？"
- **學分規劃**: "通識課程有哪些選擇？"、"如何湊滿畢業學分？"
- **衝堂檢查**: "這兩門課時間會衝突嗎？"
- **跨系選課**: "外系生可以選哪些課？"

#### 校園生活類
- **教室位置**: "C2-114在哪裡？"、"哪棟樓的教室比較新？"
- **課外活動**: "有沒有服務學習課程？"、"實習課程有哪些？"
- **證照考試**: "哪些課可以幫助考證照？"

### 1.2 典型問題集 (50+個)

#### 探索性問題 (Exploratory)
1. "中央大學有哪些學院？各學院特色是什麼？"
2. "理學院和工學院的差別在哪？"
3. "資工系和資管系課程有什麼不同？"
4. "文學院有哪些系所？都在學什麼？"
5. "商學院的核心課程有哪些？"
6. "雙主修需要多修幾學分？有哪些課要上？"
7. "通識課程分成哪幾類？每類要修多少學分？"
8. "全英文授課的課程多嗎？有哪些？"
9. "實驗課和講課有什麼差別？"
10. "哪些系有實習課程？"

#### 比較性問題 (Comparative)
11. "微積分(一)和微積分(二)內容差在哪？"
12. "普通物理和普通化學哪個比較難？"
13. "經濟學和會計學的差別？"
14. "必修和選修的比例大概多少？"
15. "大一和大二的課程難度差很多嗎？"
16. "半學年和全學年課程的差別？"
17. "不同老師教的同一門課內容會差很多嗎？"
18. "理論課和實作課的比例？"
19. "線上課程和實體課程有什麼不同？"
20. "日間部和進修部的課程一樣嗎？"

#### 決策支援問題 (Decision Support)
21. "我對AI有興趣，應該選資工系還是電機系？"
22. "想當數據分析師，要修哪些課？"
23. "對商業和科技都有興趣，有什麼科系適合？"
24. "英文不好的話，哪些系會比較吃力？"
25. "數學不好可以讀什麼系？"
26. "想出國留學，應該選什麼系和課程？"
27. "想創業的話，商學院哪個系比較適合？"
28. "對設計有興趣但也想學科技，有什麼選擇？"
29. "體育生適合哪些科系？"
30. "想當老師，要選什麼系？"

#### 實用規劃問題 (Practical Planning)
31. "大一新生必修課程有哪些？"
32. "一學期最多可以修幾學分？"
33. "如何查詢課程時間表？"
34. "選課優先順序是怎麼決定的？"
35. "什麼時候可以選課？"
36. "如何知道課程還有沒有名額？"
37. "加退選期間可以做什麼？"
38. "外系生選課有什麼限制？"
39. "暑期課程有哪些？"
40. "如何申請抵免學分？"

#### 深度諮詢問題 (In-depth Consultation)
41. "資工系四年課程規劃建議？"
42. "如何在大學培養就業競爭力？"
43. "想進入半導體產業，要修哪些課？"
44. "金融科技領域需要什麼背景？"
45. "數據科學相關課程有哪些？"
46. "人工智慧相關的課程推薦？"
47. "如何規劃雙主修？會很難嗎？"
48. "輔系和雙主修的差別？"
49. "研究所和大學課程銜接建議？"
50. "如何平衡課業和社團活動？"

#### 特殊需求問題 (Special Needs)
51. "線上課程有哪些選擇？"
52. "晚上的課程有哪些？"
53. "短期密集課程有嗎？"
54. "可以跨校選課嗎？"
55. "交換學生課程如何抵免？"

---

## 二、RAG系統架構設計

### 2.1 整體架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│  (Web App / LINE Bot / Discord Bot / Voice Assistant)       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Orchestrator Agent                         │
│  - Intent Classification                                     │
│  - Query Routing                                            │
│  - Session Management                                        │
└────────┬───────────────┬───────────────┬────────────────────┘
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ Course  │    │ Career  │    │Planning │
    │ Expert  │    │ Advisor │    │ Helper  │
    │ Agent   │    │ Agent   │    │ Agent   │
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
         └───────┬───────┴───────┬───────┘
                 │               │
        ┌────────▼────────┐ ┌───▼────────┐
        │  Tool Layer     │ │Knowledge   │
        │                 │ │Graph       │
        └─────────────────┘ └────────────┘
                 │
        ┌────────▼────────┐
        │  Vector Store   │
        │  (Embeddings)   │
        └─────────────────┘
                 │
        ┌────────▼────────┐
        │ Course Database │
        │  (3316 courses) │
        └─────────────────┘
```

### 2.2 Multi-Agent 系統設計

#### Agent 1: Orchestrator (總協調者)
**職責**:
- 理解使用者意圖
- 將查詢路由到適當的專家Agent
- 整合多個Agent的回應
- 維護對話上下文

**使用的LLM**: GPT-4 / Claude 3.5 Sonnet

**流程**:
```python
def orchestrate(user_query, session_context):
    # 1. Intent Classification
    intent = classify_intent(user_query)
    # intents: course_query, career_advice, planning, comparison, general_qa

    # 2. Extract entities
    entities = extract_entities(user_query)
    # entities: department, course_name, semester, instructor, etc.

    # 3. Route to appropriate agent(s)
    if intent == "course_query":
        result = course_expert_agent.query(user_query, entities)
    elif intent == "career_advice":
        result = career_advisor_agent.consult(user_query, entities)
    elif intent == "planning":
        result = planning_helper_agent.plan(user_query, session_context)
    elif intent == "comparison":
        # Multi-agent collaboration
        course_data = course_expert_agent.get_courses(entities)
        analysis = career_advisor_agent.analyze_fit(course_data)
        result = synthesize(course_data, analysis)

    # 4. Generate response
    return generate_response(result, session_context)
```

#### Agent 2: Course Expert (課程專家)
**職責**:
- 回答課程內容、時間、學分等具體問題
- 檢索課程資訊
- 提供課程比較

**Tools**:
- `search_courses(filters)`: 根據條件搜尋課程
- `get_course_details(course_id)`: 獲取詳細課程資訊
- `compare_courses(course_ids)`: 比較多門課程
- `find_similar_courses(course_id)`: 找相似課程
- `check_schedule_conflict(course_ids)`: 檢查時間衝突
- `get_prerequisites(course_id)`: 查詢先修課程

**RAG Strategy**:
- Hybrid Search (向量 + 關鍵字)
- Re-ranking with course metadata

#### Agent 3: Career Advisor (生涯顧問)
**職責**:
- 根據興趣推薦科系
- 分析課程與職涯的關聯
- 提供學習路徑建議

**Tools**:
- `match_interests_to_departments(interests)`: 興趣配對科系
- `analyze_career_path(career_goal)`: 分析職涯路徑
- `recommend_skill_courses(skills)`: 推薦技能課程
- `get_department_overview(department)`: 科系概覽

**Knowledge Sources**:
- 課程資料庫
- 職涯資料庫 (外部整合)
- 產業趨勢資料

#### Agent 4: Planning Helper (規劃助手)
**職責**:
- 學期選課規劃
- 畢業學分規劃
- 時間表最佳化

**Tools**:
- `generate_semester_plan(constraints)`: 生成學期計畫
- `calculate_credits(course_ids)`: 計算學分
- `optimize_schedule(preferences)`: 最佳化時間表
- `validate_graduation_requirements(transcript)`: 驗證畢業要求

**Algorithms**:
- Constraint Satisfaction Problem (CSP) solver
- Genetic Algorithm for schedule optimization

---

## 三、技術實作細節

### 3.1 資料處理流程

#### Step 1: 資料預處理
```python
# 1. 清理和標準化
- 移除HTML標籤
- 統一日期格式
- 標準化系所名稱
- 解析上課時間

# 2. 資料擴增
- 從course_content提取關鍵概念
- 從notes提取重要資訊
- 生成課程摘要
- 提取技能關鍵字 (從教學目標、內容)

# 3. 建立關聯
- 課程-科系關聯
- 課程-技能關聯
- 課程-職涯關聯
- 先修課程鏈
```

#### Step 2: Embedding 策略

**多層次Embedding**:
```python
# Layer 1: 課程標題 (快速檢索)
title_embedding = embed(f"{course_name_zh} {course_name_en}")

# Layer 2: 課程描述 (語意搜尋)
description_embedding = embed(f"""
課程名稱: {course_name_zh}
開課系所: {department}
課程目標: {course_objective}
課程內容: {course_content}
""")

# Layer 3: 詳細內容 (深度理解)
detailed_embedding = embed(f"""
{all_course_fields}
相關技能: {extracted_skills}
適合對象: {target_students}
""")

# Layer 4: 跨語言 (中英文)
bilingual_embedding = embed(f"{course_name_zh} {course_name_en} {course_content}")
```

**Embedding模型選擇**:
- 主要: `text-embedding-3-large` (OpenAI) 或 `bge-large-zh-v1.5` (中文優化)
- 備用: `multilingual-e5-large` (多語言)
- 輕量: `gte-base-zh` (快速檢索)

### 3.2 檢索策略 (Retrieval)

#### 混合檢索架構
```python
class HybridRetriever:
    def retrieve(self, query, top_k=20):
        # 1. 向量檢索 (Semantic Search)
        vector_results = self.vector_search(query, top_k=15)

        # 2. 關鍵字檢索 (BM25)
        keyword_results = self.bm25_search(query, top_k=15)

        # 3. 結構化查詢 (Metadata Filter)
        if has_structured_intent(query):
            filter_results = self.structured_search(query)
        else:
            filter_results = []

        # 4. 融合排序 (Reciprocal Rank Fusion)
        combined = self.rrf_fusion(
            [vector_results, keyword_results, filter_results],
            weights=[0.5, 0.3, 0.2]
        )

        # 5. Re-ranking
        reranked = self.rerank(query, combined, top_k=10)

        return reranked

    def rerank(self, query, candidates, top_k):
        # 使用 Cross-Encoder 重新排序
        scores = self.cross_encoder.predict([
            (query, doc.content) for doc in candidates
        ])
        return sorted(zip(candidates, scores),
                     key=lambda x: x[1],
                     reverse=True)[:top_k]
```

#### 查詢增強 (Query Enhancement)
```python
class QueryEnhancer:
    def enhance(self, query, context):
        # 1. Query Expansion (查詢擴展)
        expanded = self.expand_with_synonyms(query)
        # "AI課程" -> "人工智慧課程, 機器學習, 深度學習"

        # 2. Query Decomposition (查詢分解)
        if is_complex_query(query):
            sub_queries = self.decompose(query)
            # "資工系大一必修有哪些,哪些比較難?"
            # -> ["資工系大一必修課程", "課程難度評估"]

        # 3. Contextualization (上下文化)
        contextualized = self.add_context(query, context)
        # User: "那這門課呢?"
        # -> "這門課" + previous_course_context

        # 4. Spell Correction (拼寫修正)
        corrected = self.correct_spelling(query)
        # "程是設計" -> "程式設計"

        return {
            'original': query,
            'expanded': expanded,
            'sub_queries': sub_queries,
            'contextualized': contextualized,
            'corrected': corrected
        }
```

### 3.3 Tools 設計

#### Tool 1: 課程搜尋引擎
```python
class CourseSearchTool:
    """
    Advanced course search with multiple filters
    """
    def search(self,
               keywords: str = None,
               department: str = None,
               credits: int = None,
               required_elective: str = None,
               semester: str = None,
               instructor: str = None,
               day_of_week: str = None,
               time_range: tuple = None,
               course_level: str = None,
               has_office_hours: bool = None):

        # Build complex query
        filters = []
        if department:
            filters.append(f"department == '{department}'")
        if credits:
            filters.append(f"credits == {credits}")
        if required_elective:
            filters.append(f"required_elective == '{required_elective}'")

        # Execute search with vector + filter
        results = self.vector_store.search(
            query=keywords,
            filter=combine_filters(filters),
            top_k=20
        )

        return results
```

#### Tool 2: 時間表分析器
```python
class ScheduleAnalyzer:
    """
    Parse and analyze course schedules
    """
    def parse_schedule(self, schedule_str):
        # "Wed8A, Fri3,4" -> structured format
        return {
            'Wednesday': ['8A'],
            'Friday': ['3', '4']
        }

    def check_conflicts(self, course_ids):
        schedules = [self.get_schedule(cid) for cid in course_ids]
        conflicts = []
        for i, s1 in enumerate(schedules):
            for j, s2 in enumerate(schedules[i+1:]):
                if self.has_overlap(s1, s2):
                    conflicts.append((course_ids[i], course_ids[j]))
        return conflicts

    def find_free_slots(self, selected_courses):
        # Find available time slots
        all_slots = self.generate_all_slots()
        occupied = self.get_occupied_slots(selected_courses)
        return [slot for slot in all_slots if slot not in occupied]
```

#### Tool 3: 課程關係圖建構器
```python
class CourseGraphBuilder:
    """
    Build knowledge graph of course relationships
    """
    def build_graph(self, courses):
        G = nx.DiGraph()

        # Add nodes (courses)
        for course in courses:
            G.add_node(course['id'], **course)

        # Add edges (relationships)
        for course in courses:
            # Prerequisite relationships
            prereqs = self.extract_prerequisites(course)
            for prereq in prereqs:
                G.add_edge(prereq, course['id'],
                          relation='prerequisite')

            # Same department
            same_dept = self.find_same_department(course)
            for related in same_dept:
                G.add_edge(course['id'], related,
                          relation='same_department')

            # Similar content (from embeddings)
            similar = self.find_similar_courses(course, threshold=0.8)
            for sim_course, score in similar:
                G.add_edge(course['id'], sim_course,
                          relation='similar',
                          weight=score)

        return G

    def find_learning_path(self, start_course, end_course):
        # Find optimal learning path
        return nx.shortest_path(self.graph, start_course, end_course)
```

#### Tool 4: 統計分析器
```python
class StatisticsAnalyzer:
    """
    Analyze course statistics and trends
    """
    def get_department_stats(self, department):
        courses = self.filter_by_department(department)
        return {
            'total_courses': len(courses),
            'avg_credits': np.mean([c['credits'] for c in courses]),
            'required_ratio': self.calc_required_ratio(courses),
            'popular_instructors': self.get_top_instructors(courses),
            'course_distribution': self.get_distribution(courses),
            'difficulty_estimate': self.estimate_difficulty(courses)
        }

    def compare_departments(self, dept_list):
        stats = [self.get_department_stats(d) for d in dept_list]
        return self.create_comparison_table(stats)

    def trending_courses(self, time_window='1_year'):
        # Analyze course trends (if historical data available)
        pass
```

#### Tool 5: 自然語言SQL生成器
```python
class NL2SQLTool:
    """
    Convert natural language to SQL for structured queries
    """
    def generate_sql(self, nl_query):
        prompt = f"""
        Given the course database schema:
        - courses(id, course_name_zh, department, credits,
                  required_elective, instructor, schedule, ...)

        Convert this natural language query to SQL:
        "{nl_query}"

        Return only the SQL query.
        """

        sql = self.llm.generate(prompt)
        validated_sql = self.validate_and_sanitize(sql)
        return validated_sql

    def execute(self, nl_query):
        sql = self.generate_sql(nl_query)
        results = self.db.execute(sql)
        return results
```

#### Tool 6: 職涯配對引擎
```python
class CareerMatchingTool:
    """
    Match courses to career paths
    """
    def __init__(self):
        # Load career database
        self.career_skills = self.load_career_skills()
        # e.g., "Software Engineer": ["Python", "Data Structures", ...]

    def match_career(self, interests, strengths):
        # Match student profile to careers
        careers = self.recommend_careers(interests, strengths)

        # For each career, find relevant courses
        recommendations = []
        for career in careers:
            required_skills = self.career_skills[career]
            courses = self.find_courses_by_skills(required_skills)
            recommendations.append({
                'career': career,
                'match_score': self.calculate_match(interests, career),
                'recommended_courses': courses,
                'learning_path': self.generate_path(courses)
            })

        return sorted(recommendations,
                     key=lambda x: x['match_score'],
                     reverse=True)
```

### 3.4 提示詞工程 (Prompt Engineering)

#### System Prompt for Orchestrator
```python
ORCHESTRATOR_PROMPT = """
你是一位專業的大學課程諮詢顧問助手,專門協助高中生了解大學課程資訊。

你的職責:
1. 理解學生的問題和需求
2. 協調不同的專家Agent來回答問題
3. 提供清晰、有用、友善的回應
4. 追蹤對話歷史,提供連貫的建議

可用的Agent:
- CourseExpert: 回答具體課程問題(內容、時間、學分等)
- CareerAdvisor: 提供生涯規劃和科系選擇建議
- PlanningHelper: 協助選課和學期規劃

回應風格:
- 使用高中生能理解的語言
- 避免過多專業術語
- 提供具體例子和數據支持
- 主動追問以更好理解需求
- 保持友善和鼓勵的態度

當前對話紀錄:
{chat_history}

學生問題: {user_query}

請分析問題並決定:
1. 問題類型 (intent)
2. 需要呼叫哪些Agent
3. 需要哪些額外資訊
"""
```

#### Prompt for Course Expert
```python
COURSE_EXPERT_PROMPT = """
你是課程專家,精通所有課程的詳細資訊。

檢索到的相關課程:
{retrieved_courses}

學生問題: {query}

請根據檢索到的課程資訊回答問題。注意:
1. 只使用檢索到的資訊,不要編造
2. 如果資訊不足,說明需要更多資訊
3. 提供具體的課程代碼、名稱、開課資訊
4. 如果有多個選項,列出並比較
5. 用表格呈現比較資訊(如果適合)

回應格式:
- 直接回答問題
- 提供supporting details
- 列出相關課程連結(如果有)
"""
```

#### Prompt for Career Advisor
```python
CAREER_ADVISOR_PROMPT = """
你是生涯顧問,協助學生探索興趣和規劃未來。

學生輸入: {user_input}
相關課程資料: {course_data}
職涯資料: {career_data}

請提供:
1. 興趣分析: 根據學生的描述分析其興趣傾向
2. 科系建議: 推薦3-5個適合的科系,說明理由
3. 課程路徑: 為每個科系規劃學習路徑
4. 職涯展望: 說明未來可能的職業方向
5. 注意事項: 提醒需要特別注意的事項

保持:
- 鼓勵性: 幫助學生建立信心
- 實際性: 提供可行的建議
- 全面性: 考慮多個面向
"""
```

### 3.5 評估與優化

#### Evaluation Metrics
```python
class RAGEvaluator:
    """
    Evaluate RAG system performance
    """
    def evaluate(self, test_set):
        metrics = {
            # Retrieval metrics
            'retrieval_precision': self.calc_precision(),
            'retrieval_recall': self.calc_recall(),
            'mrr': self.calc_mrr(),  # Mean Reciprocal Rank
            'ndcg': self.calc_ndcg(),  # Normalized DCG

            # Generation metrics
            'answer_relevance': self.calc_relevance(),
            'answer_faithfulness': self.calc_faithfulness(),
            'answer_completeness': self.calc_completeness(),

            # User satisfaction
            'user_rating': self.collect_ratings(),
            'task_success_rate': self.calc_success_rate(),

            # System metrics
            'latency': self.measure_latency(),
            'cost': self.calculate_cost()
        }
        return metrics
```

#### A/B Testing Framework
```python
class ABTester:
    """
    Test different RAG configurations
    """
    def test_variants(self, variants, test_queries):
        results = {}
        for variant_name, config in variants.items():
            rag = RAGSystem(config)
            metrics = self.run_tests(rag, test_queries)
            results[variant_name] = metrics

        return self.compare_results(results)

# Example variants
variants = {
    'baseline': {
        'retriever': 'vector_only',
        'top_k': 5,
        'llm': 'gpt-3.5-turbo'
    },
    'hybrid': {
        'retriever': 'hybrid',
        'top_k': 10,
        'reranker': 'cross-encoder',
        'llm': 'gpt-4'
    },
    'agent-based': {
        'retriever': 'hybrid',
        'multi_agent': True,
        'tools_enabled': True,
        'llm': 'claude-3-sonnet'
    }
}
```

---

## 四、實作技術棧

### 4.1 核心框架
```python
# LLM Framework
- LangChain / LlamaIndex (RAG orchestration)
- LangGraph (Multi-agent workflows)
- AutoGen (Agent collaboration)

# Vector Database
- Qdrant (推薦 - 混合搜尋支援)
- Weaviate (知識圖譜整合)
- Milvus (大規模部署)
- ChromaDB (輕量開發)

# Embedding Models
- OpenAI text-embedding-3-large
- bge-large-zh-v1.5 (本地部署)
- multilingual-e5-large

# LLM Models
- GPT-4 Turbo / GPT-4o (主要)
- Claude 3.5 Sonnet (對話)
- Gemini Pro (多模態)
- Llama 3 70B (本地備選)

# Search & Retrieval
- Elasticsearch (關鍵字搜尋)
- Sentence Transformers (嵌入)
- rank-BM25 (傳統檢索)
- Cross-Encoders (重排序)
```

### 4.2 資料處理
```python
# Data Processing
- Pandas (資料處理)
- NumPy (數值計算)
- NetworkX (知識圖譜)

# NLP
- jieba (中文分詞)
- spaCy (NER, POS tagging)
- OpenCC (繁簡轉換)
```

### 4.3 部署架構
```python
# Backend
- FastAPI (API server)
- Celery (非同步任務)
- Redis (快取 & 訊息佇列)
- PostgreSQL (結構化資料)

# Frontend
- React / Next.js (Web)
- Streamlit (快速原型)

# Monitoring
- LangSmith (LLM追蹤)
- Prometheus + Grafana (系統監控)
- Sentry (錯誤追蹤)
```

---

## 五、進階功能設計

### 5.1 個人化推薦

```python
class PersonalizationEngine:
    """
    Track user preferences and personalize recommendations
    """
    def build_user_profile(self, user_id, interactions):
        profile = {
            'interests': self.extract_interests(interactions),
            'preferred_difficulty': self.infer_difficulty_preference(),
            'time_preferences': self.analyze_time_patterns(),
            'learning_style': self.identify_learning_style(),
            'career_goals': self.extract_career_mentions()
        }
        return profile

    def personalized_search(self, query, user_profile):
        # Adjust search based on profile
        results = self.base_search(query)
        reranked = self.rerank_with_profile(results, user_profile)
        return reranked
```

### 5.2 互動式對話流程

```python
# Multi-turn conversation example
class ConversationFlow:
    def handle_course_exploration(self, user_query):
        # Turn 1: Broad question
        if is_broad_query(user_query):
            response = self.ask_clarification()
            # "你對哪個領域比較有興趣?理工、商管、還是人文?"

        # Turn 2: Narrow down
        elif has_preference(user_query):
            response = self.show_options()
            # "理工學院有資工、電機、化工...你想了解哪個?"

        # Turn 3: Deep dive
        elif has_specific_target(user_query):
            response = self.provide_detailed_info()
            # Show course list, requirements, etc.

        # Turn 4: Follow-up
        response += self.suggest_next_steps()
        # "還想了解課程內容、師資、還是未來出路?"

        return response
```

### 5.3 視覺化呈現

```python
class Visualizer:
    """
    Generate visual representations
    """
    def create_curriculum_map(self, department):
        # Create interactive curriculum visualization
        # showing course relationships, prerequisites
        pass

    def generate_schedule_view(self, selected_courses):
        # Create weekly schedule visualization
        pass

    def plot_department_comparison(self, departments):
        # Radar chart comparing different aspects
        pass
```

### 5.4 語音互動

```python
class VoiceInterface:
    """
    Voice-based interaction
    """
    def process_voice_query(self, audio):
        # Speech to text
        text = self.stt(audio)

        # Process query
        response_text = self.rag_system.query(text)

        # Text to speech
        audio_response = self.tts(response_text)

        return {
            'text': response_text,
            'audio': audio_response
        }
```

---

## 六、實作路徑建議

### Phase 1: MVP (2-3週)
1. 資料預處理與Embedding
2. 基礎向量檢索
3. 簡單的Q&A介面
4. 5-10個測試問題驗證

### Phase 2: 核心功能 (3-4週)
1. 實作混合檢索
2. 加入Course Expert Agent
3. 實作基礎Tools
4. Web界面開發

### Phase 3: Multi-Agent (3-4週)
1. 實作Orchestrator
2. 加入Career Advisor和Planning Helper
3. Agent協作邏輯
4. 對話管理

### Phase 4: 優化與擴展 (2-3週)
1. 效能優化
2. 個人化功能
3. 視覺化
4. 使用者測試與迭代

### Phase 5: 部署與維護 (持續)
1. 生產環境部署
2. 監控與日誌
3. 持續優化
4. 資料更新機制

---

## 七、成本估算

### 開發成本
- LLM API costs: ~$200-500/month (視使用量)
- Vector Database: $0-100/month (開發階段可用免費版)
- 伺服器: $50-200/month
- 其他服務: $50/month

### 優化成本建議
1. 使用快取減少重複查詢
2. 對簡單問題使用小模型(GPT-3.5)
3. 批次處理降低API呼叫
4. 本地部署Embedding模型

---

## 八、成功指標

### 技術指標
- 檢索準確率 > 85%
- 回應時間 < 3秒
- 系統可用性 > 99%

### 使用者指標
- 使用者滿意度 > 4.0/5.0
- 問題解決率 > 80%
- 回訪率 > 50%

### 業務指標
- 每日活躍用戶
- 問題覆蓋率
- 轉換率(諮詢->申請)

---

## 九、風險與挑戰

### 技術風險
1. **資料品質**: 課程資訊可能不完整或過時
   - 解決: 建立資料更新機制,人工審核

2. **檢索準確性**: 可能檢索到不相關的課程
   - 解決: 多層檢索+重排序,持續優化

3. **回應一致性**: 多次詢問可能得到不同答案
   - 解決: 快取機制,回應模板

### 使用者體驗風險
1. **期望管理**: 使用者可能期望系統無所不知
   - 解決: 明確說明系統能力範圍

2. **資訊過載**: 回應過於詳細
   - 解決: 分層呈現,互動式探索

---

## 十、未來擴展方向

1. **多模態**: 整合圖片、影片(課程介紹影片)
2. **社群功能**: 學長姐經驗分享
3. **即時更新**: 選課人數、評價即時更新
4. **跨校比較**: 整合其他大學資料
5. **行動應用**: LINE Bot, Mobile App
6. **AR/VR**: 虛擬校園導覽
7. **預測分析**: 選課趨勢、熱門課程預測

---

## 結語

這個RAG系統的設計著重於:
- **以使用者為中心**: 滿足高中生的實際需求
- **模組化架構**: 易於擴展和維護
- **多Agent協作**: 處理複雜查詢
- **工具整合**: 提供多樣化功能
- **持續優化**: 基於數據不斷改進

建議從MVP開始,逐步迭代,根據實際使用情況調整優先級。
