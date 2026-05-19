# Prompt 與工具使用時機改善計畫

> 撰寫日期：2026-05-16  
> 狀態：待決策（不改程式碼，先確認方案）

---

## 背景

目前系統有四個已知的工具設計問題，影響 LLM 的工具選用精準度與搜尋品質。本文件逐一分析問題根因、列出備選方案，供決策後實施。

---

## Issue 1：通識課 topic_tags 過濾支援

### 問題
使用者問「通識有沒有法律相關的課？」，目前 prompt 引導 LLM 用 `search_courses(query="法律", dept="通識教育中心")` 走語意搜尋。語意搜尋對此類查詢不穩定——「法律」這個詞可能命中生態法、法庭語言等邊緣課程，而非精確匹配有「法律」tag 的課程。

### 現況調查
- 通識課（CC/GS 前綴）的 `topic_tags` 有 **25 種固定值**（已由 NLP pipeline 標記）：
  > 工程、化學、心理學、文學、永續發展、生物、全球化、宗教、性別研究、法律、物理、社會學、政治、音樂、倫理學、哲學、族群文化、經濟、資訊科技、語言學、數學、歷史、環境科學、醫學、藝術
- 這 25 個 tag 已存於 Qdrant payload 的 `topic_tags` 欄位（list[str]）
- 目前 `search_courses` 的 Qdrant filter 構建完全不支援 `topic_tags` 過濾

### 方案比較

| 方案 | 做法 | 優點 | 缺點 |
|------|------|------|------|
| **A（推薦）** | 新增 `topic_tag: str` 參數到 `tool_search_courses` schema；工具層加 `{$contains: topic_tag}` filter | LLM 有明確參數，精確過濾 | 需改 tools.py + schema；LLM 需知道 25 個 tag |
| **B** | 工具內部自動判斷：若 query 精確等於某已知 tag，先走 tag filter；否則走語意 | 對 LLM 透明 | 邏輯複雜，且 LLM 無法明確指定 tag |
| **C** | 只改 prompt，把 25 個 tag 寫在 prompt 中，指引 LLM 辨識並包入 query | 零程式碼改動 | LLM 仍走語意搜尋，無法精確過濾 |

### 方案 A 具體做法
```python
# tools.py schema 新增
"topic_tag": {
    "type": "string",
    "description": "通識課主題標籤（僅適用於通識課）。"
    "可用值：工程、化學、心理學、文學、永續發展、生物、全球化、宗教、"
    "性別研究、法律、物理、社會學、政治、音樂、倫理學、哲學、族群文化、"
    "經濟、資訊科技、語言學、數學、歷史、環境科學、醫學、藝術"
}

# Qdrant filter 構建新增
if topic_tag:
    conditions.append(FieldCondition(
        key="topic_tags",
        match=MatchAny(any=[topic_tag])
    ))
```

---

## Issue 2：domain_profile 去除 top-5 截斷

### 問題
`get_dept_info` 回傳的 `domain_profile` 只有 top-5 領域，限制了 LLM 對系所全貌的理解。系所的課程領域通常不多（多數系所只有 5-15 種），top-5 截斷反而遺漏邊緣但重要的領域。

### 現況調查
`backend/app/services/graph_service.py`，`get_dept_domain_profile` 函式中：
```python
# 第 322 行（硬截 top-5）
return [{"domain": d, "count": c} for d, c in counter.most_common(5)]
```

### 方案
**直接改為回傳全部**：
```python
return [{"domain": d, "count": c} for d, c in counter.most_common()]
```
- 一行修改，無副作用
- 如果 LLM 接到 20 個 domain，token 增加約 200，可接受

---

## Issue 3：get_depts_by_tech 擴展 concept 語意搜尋能力

### 問題
`get_depts_by_tech` 的主路徑是字串精確比對圖中的 tech/concept/field 節點。這對技術名稱（Python、PyTorch）運作良好，但對概念查詢（「機率論」、「最佳化」）容易 miss——概念有大量同義詞，精確比對無法命中。

### 現況調查
`backend/app/services/graph_service.py` 的 `get_depts_by_tech` 執行流程：
1. 找技術節點（精確比對優先，Qdrant 向量為 fallback）
2. 反向遍歷 TEACHES/COVERS/COVERS_FIELD → 課程集合
3. 課程 → 系所（必修/選修分離）

向量 fallback 已存在，但：
- 閾值較高（score ≥ 0.7）
- 只取 top-5 個候選節點

### 方案比較

| 方案 | 做法 | 優點 | 缺點 |
|------|------|------|------|
| **A（推薦）** | 降低向量閾值（≥ 0.55）並擴展 top-k 候選節點 5→20 | 改動最小 | 可能引入雜訊 |
| **B** | 新增獨立 `get_depts_by_concept(concept)` 工具，走純語意路徑 | 職責分離清楚 | 新增一個工具，LLM 需判斷何時用 |
| **C** | 改 prompt，指引 LLM 搭配 search_courses + get_depts_by_tech 組合使用 | 零程式碼 | LLM 需多次工具呼叫 |

### 方案 A 具體做法
在 `_find_graph_nodes_by_query`（或類似函式）中：
- 向量搜尋閾值從 0.7 → 0.55
- 取候選節點數從 5 → 20
- 增加 node_type 過濾：優先 Concept/Field，不限 tech

---

## Issue 4：ppr_explore 使用場景重新定義（最重要）

### 問題
目前 `ppr_explore` 的使用範圍在 prompt 中定義太廣，許多場景用 `search_courses` 就夠，導致：
1. LLM 不知道何時用哪個
2. PPR 單種子時常常品質不如 search_courses
3. 開發者和使用者對 PPR 的期待與實際效果有落差

### 現況調查：PPR 實作
- **種子尋找**：雙軌並行——Qdrant 向量搜尋 `ncu_graph_nodes` + 字串精確/模糊比對，精確優先
- **演算法**：igraph Weighted PPR（damping=0.85, directed=False）；fallback Python power iteration
- **後處理**：`_ppr_gap_filter` 移除 score < mean - 0.5σ 的尾部噪音

### PPR vs search_courses 本質差異

| 維度 | search_courses | ppr_explore |
|------|--------------|-------------|
| 索引基礎 | Qdrant 向量（dense+BM25） | 知識圖譜邊（COVERS/TEACHES/REQUIRES/WORKS_FOR） |
| 擅長 | 語意精確、有條件過濾（學院、必修/選修等） | 多跳連結、發現間接關聯、跨類型節點 |
| 不擅長 | 圖路徑（teacher→concept→course）| 圖稀疏領域、單種子精確需求 |
| 適合場景 | 精確需求：「找機器學習課，我是文學院學生」 | 廣泛探索：「ML 和生物的交叉領域有什麼」 |

### 單種子 PPR 為什麼不如 search_courses？

PPR 從種子節點出發，沿圖邊擴散。單種子時，PPR 的能量主要集中在直接鄰居（1-hop），這幾乎等同於直接查 `COVERS/TEACHES` 邊——而 search_courses 的圖擴展（Signal C）已經做了這件事，且同時有向量搜尋的補充。

**PPR 只有在多種子時才有獨特價值**：兩個 seed 的 PPR 會在共同鄰居節點積累分數，這些節點正是「橋接兩個概念」的課程/教師，這是 search_courses 無法做到的。

### PPR 真正有價值的場景

1. **多概念交集**：使用者同時對 2+ 個概念感興趣
   - `ppr_explore(seed="機器學習, 生物資訊", focus="course")`
   - PPR 的共同鄰居 = 同時涵蓋兩個概念的課程

2. **教師網絡探索**：師生連結在圖中有 `WORKS_FOR / TEACHES` 邊
   - `ppr_explore(seed="自然語言處理", focus="instructor")`
   - 向量搜尋找不到「誰的研究方向是 NLP」（這是圖關係）

3. **系所層級概念覆蓋**：了解某概念在哪些系有課
   - `ppr_explore(seed="永續發展", focus="dept")`
   - `get_depts_by_tech` 偏向 tech/tool，概念類更適合 PPR

4. **跨類型探索**：使用者要看課程＋教師＋系所全貌
   - `ppr_explore(seed="人工智慧, 機器學習", focus="overview")`

### 目前 prompt 誤用 PPR 的範例（應改為其他工具）

| 現在 prompt 的範例 | 問題 | 建議替換 |
|---|---|---|
| 「高中學微積分，大學往哪延伸？」→ ppr_explore(seed="微積分") | 微積分課太多，單種子 PPR 稀釋 | `search_courses(query="數值分析 最佳化 微分方程")` |
| 「演算法在學什麼？有類似的課嗎？」→ ppr_explore | 直接名稱查詢 | `get_course_detail + find_similar_courses` |
| 「有哪些 AI 相關課程」→ ppr_explore（單種子） | 單明確需求 | `search_courses(query="人工智慧 機器學習")` |
| 「哪些教授在研究深度學習」→ ppr_explore+get_teacher_info | focus="instructor" 合理，但說明不清 | 保留但強調是「teacher network」，非課程查詢 |

### 建議的 prompt 修改方向

**修改前（現在）**：
```
廣泛探索（「AI 相關有哪些課」「機器學習連到哪些老師」「我對 XX 有興趣，有哪些選擇」）：
  → ppr_explore(seed="概念或課名", focus="course/instructor/dept/overview")
  → **多概念時強烈建議多種子**
```

**修改後（建議）**：
```
廣泛探索 / 多概念交集（「機器學習和生物的交叉有哪些課」「AI、統計、金融的關聯」）：
  → ppr_explore(seed="概念A, 概念B", focus="course")
  → ⚠️ 單一概念直接查課程請用 search_courses，PPR 在單種子時不如向量搜尋

教師網絡探索（「研究 XX 的教授有誰」「誰在做 XX 領域」）：
  → ppr_explore(seed="領域概念", focus="instructor")
  → 這是 PPR 比向量搜尋更有優勢的場景（圖有 WORKS_FOR/TEACHES 邊）

系所概念覆蓋（「哪些系所涉及永續發展」「XX 概念在哪些系有課」）：
  → ppr_explore(seed="概念", focus="dept")
  → 或 get_depts_by_tech（後者更精準於 tech，前者更廣泛於 concept）
```

### PPR 參數實驗建議

目前 PPR 品質問題可能有幾個來源，建議實驗：

| 參數 | 現值 | 實驗值 | 預期效果 |
|------|------|---------|---------|
| damping | 0.85 | 0.75 | 擴散更廣，單種子時結果更多樣 |
| _ppr_gap_filter σ 係數 | 0.5 | 0.3 | 過濾更多尾部噪音，提升結果精準度 |
| 種子向量閾值 | ? | ≥ 0.65 | 更嚴格的種子過濾，避免偏離的起跑點 |
| top-k 回傳 | 10-15 | 20 | 給 LLM 更多選擇空間 |

---

## 決策表

| Issue | 推薦方案 | 風險 | 優先級 |
|-------|---------|------|-------|
| 1. topic_tags 過濾 | 方案 A（新增參數） | 低 | 中 |
| 2. domain_profile 截斷 | 直接改一行 | 極低 | 高（立刻做） |
| 3. get_depts_by_tech 擴展 | 方案 A（降閾值+擴展 top-k） | 低-中 | 中 |
| 4. PPR 場景重定義 | 修改 prompt 說明 + 範例 | 低 | 高（影響 LLM 行為最大） |

---

## 需要進一步測試才能決策的項目

1. **PPR 實際 vs search_courses 對比測試**：設計 5-10 個查詢，分別用兩個工具，比較結果品質
2. **topic_tags 覆蓋率**：多少通識課有 topic_tags？如果覆蓋率低，方案 A 價值也低
3. **concept 語意搜尋的 miss 率**：get_depts_by_tech 實際上對 concept 查詢 miss 多少？需要測試案例

---

## 測試腳本建議

```bash
# PPR vs search_courses 對比
python scripts/test_filter_search.py --ppr-compare

# topic_tags 覆蓋率統計  
python -c "
import json
data = json.load(open('data/processed/nlp/nlp_topic_tags.json'))
tags = [v.get('topic_tags',[]) for v in data.values()]
covered = sum(1 for t in tags if t)
print(f'有 topic_tags: {covered}/{len(tags)} ({covered/len(tags)*100:.1f}%)')
"
```
