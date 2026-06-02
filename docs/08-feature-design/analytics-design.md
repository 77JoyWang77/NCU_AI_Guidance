# 個人學習傾向分析頁面設計說明

> 路由：`/profile`　需登入（Firebase JWT）

---

## 資料來源

分析資料從使用者的**對話歷史**中萃取，不依賴個人資料表單。
所有數字會隨新對話自動更新（15 分鐘快取）。

| 資料表 | 欄位 | 用途 |
|--------|------|------|
| `chat_turns.course_pool` | JSONB 陣列 | 系所分佈、通識分類、唯一課程數、課程領域 |
| `chat_turns.course_cards` | JSONB 陣列 | domain_tags 興趣標籤 |
| `chat_turns.tools_used` | JSONB 陣列 | 探索型態診斷依據 |
| `chat_sessions` | `user_id` | session 計數 |
| `user_analytics` | `data`, `computed_at` | 15 分鐘快取（避免每次全量掃描） |

**額外查詢（lru_cache，只載入一次）：**
- `course_index.json` → `course_domains`（課程領域，analytics 時按 code 查）
- `nlp_topic_tags.json` → `top_topic_tags`（通識主題標籤）

---

## 後端 API

`GET /api/chat/analytics`（需 Bearer token）

```jsonc
{
  "overview": {
    "total_sessions": 12,
    "total_turns": 47,
    "total_courses_explored": 183,
    "fav_college": "資訊電機學院"
  },
  "dept_distribution": [           // Top 8 系所（僅 college_map 中有對應者）
    { "name": "資訊工程學系", "count": 42, "pct": 23.1 }
  ],
  "college_distribution": [        // Top 5 學院（雷達圖用）
    { "name": "資訊電機學院", "count": 89, "pct": 48.6 }
  ],
  "tool_usage": [
    { "tool": "search_courses", "label": "課程語意搜尋", "count": 31 }
  ],
  "top_domain_tags": [             // Top 15（來自 course_cards.domain_tags）
    { "tag": "機器學習", "count": 18 }
  ],
  "top_course_domains": [          // Top 20（來自 course_index.course_domains，切開 "、"）
    { "domain": "基礎學科", "count": 12 }
  ],
  "general_edu": {
    "total": 23,
    "categories": [
      { "name": "通識", "count": 10 },
      { "name": "外語", "count": 8 },
      { "name": "體育", "count": 5 }
    ],
    "top_topic_tags": [
      { "tag": "歷史", "count": 4 }
    ]
  }
}
```

---

## 快取機制

```
GET /api/chat/analytics
  → 查 user_analytics WHERE computed_at > now() - 15min
  → 命中 → 直接回傳（O(1)）
  → 未命中 → 全量計算 → 寫回 user_analytics → 回傳
```

- `save()` / `delete()` 完全不觸碰快取（零寫入放大）
- 15 分鐘後自然過期，下次請求重算
- 強制重算：`UPDATE user_analytics SET computed_at = to_timestamp(0)`

---

## 頁面佈局

```
概覽卡片（對話次數 / 提問輪次 / 探索課程數 / 最常探索學院）

Row 1：學術探索領域（六角雷達）｜ 探索型態診斷
Row 2：課程探索領域 WordCloud  ｜ 課程領域分佈 WordCloud
Row 3：探索系所分佈（Pie）     ｜ 通識與一般選修（圓形環）
```

---

## 各區塊設計說明

### 概覽卡片（4 格）

| 卡片 | 來源 | 說明 |
|------|------|------|
| 對話次數 | `chat_sessions` count | 歷史對話總數 |
| 提問輪次 | `chat_turns` count | 每輪 = 一次 Q&A |
| 探索課程 | `course_pool` 去重 | 以 `code` 優先，無 code 用 `name` |
| 最常探索學院 | `college_distribution[0]` | 排除「中心、處室」 |

---

### 學術探索領域分佈（六角雷達圖）

`college_distribution` 對應到 6 個學術領域軸：

| 軸 | 涵蓋學院 | 顏色 |
|----|---------|------|
| 理工 | 理學院、工學院、永續與綠能科技研究學院 | `#6366f1` |
| 資訊 | 資訊電機學院 | `#0ea5e9` |
| 地科 | 地球科學學院 | `#a16207` |
| 生醫 | 生醫理工學院 | `#10b981` |
| 人文 | 文學院、客家學院 | `#f59e0b` |
| 商管 | 管理學院 | `#ef4444` |

「中心、處室」不計入雷達圖。

**數值計算：**
```
相對分數(0-100) = domain_count / max_domain_count × 100   ← 雷達圖軸高度
實際佔比(%)    = domain_count / 所有非通識 count × 100    ← 圖例顯示
```

雷達圖軸標籤顯示「相對分數」（最大域永遠為 100，差異明顯），下方圖例顯示「實際佔比 %」。

---

### 探索型態診斷

依序判斷，取第一個符合的型態：

| 型態 | 判斷條件 |
|------|---------|
| 規劃導向型 | `tools_used` 前 6 名含畢業規定 / 學程工具 |
| 跨域探索型 | ≥ 3 個領域實際佔比 ≥ 15% |
| 專注深挖型 | 最集中系所佔比 > 50% |
| 廣泛探索型 | 探索系所 ≥ 5 個，且最集中系所 < 35% |
| 均衡探索型 | 預設 |

**規劃工具清單：**
`get_graduation_requirements`, `get_graduation_rules`, `get_program_info`,
`get_program_courses`, `get_requirements_notes`

---

### 課程探索領域 WordCloud

- 來源：`top_domain_tags`（`course_cards.domain_tags`，NLP 生成的學術領域標籤）
- 過濾：`score ≥ 0.5`（`"標籤::score"` 格式），純文字直接計入
- 歷史補救：若為空，從 `top_courses` 向 Qdrant 查 `domain_tags_rich` 回填

---

### 課程領域分佈 WordCloud

- 來源：`top_course_domains`（`course_index.course_domains`，課程官方分類）
- 資料流：`undergrad.json` / `grad.json` → `build_course_index.py` → `course_index.json`
  - 原始欄位：`課程綱要.課程領域`，以「、」切開後去重複
- analytics 時透過 `_load_course_domains()` lru_cache 查詢，O(1) 不需 Qdrant

---

### 探索系所分佈（ECharts Pie）

- 來源：`dept_distribution`（Top 8）
- 只保留 `college_map` 中有對應的真實系所，排除學院名稱（如「工學院」）作為開課單位的院級課程
- 圖例：名稱左對齊 + 百分比右對齊（`rich` text）
- 無延伸 label，hover 顯示 tooltip

---

### 通識與一般選修

**系所分類對照：**

| 類別 | 涵蓋系所 |
|------|---------|
| 通識 | 通識教育中心、核心通識課程、總教學中心、台灣聯大AI學程、環境科技學程、遙測學程 |
| 外語 | 語言中心 |
| 體育 | 體育室、軍訓室 |
| 服務學習 | 學務處-服務學習發展中心、學務處-職涯發展中心 |

顯示內容：
1. 各類別門數標籤（有資料才顯示）
2. `top_topic_tags` Top 6 圓形進度環（弧長 = 相對比例，不顯示絕對數值）

**主題標籤來源：** `nlp_topic_tags.json`，格式 `["歷史", "社會學", "宗教"]`

此卡片僅在 `general_edu.categories.length > 0` 或 `top_topic_tags.length > 0` 時顯示。

---

## 資料品質保證

### domain_tags（`nlp_domain_tags.json`）

1. **繁簡轉換**：opencc `s2twp` 全量轉換
2. **詞彙表合規**：每個 tag 必須來自 `dept_professor_map.json` 的 `specialty_vocab`
   - 字元集完全重疊 → 替換為詞彙表版本
   - 無合適對應 → 刪除
3. **Qdrant 同步**：`scripts/rag/update_domain_tags_payload.py` 更新 `domain_tags_rich`

### course_domains（`course_index.json`）

- `build_course_index.py` 從 `課程綱要.課程領域` 提取，以「、」切開
- analytics 直接查 course_index.json（lru_cache），不經 Qdrant
- Qdrant 無需更新（analytics 不走 Qdrant 讀取）

### ncu_graph_nodes 清理

`scripts/rag/remove_orphaned_field_nodes.py`：刪除 nlp_domain_tags 修正後的孤立 Field 節點，無需重新 embedding。
