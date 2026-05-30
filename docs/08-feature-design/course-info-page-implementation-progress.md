# Course Info Page Implementation Progress

## Phase 0 - 專案盤點與 Qdrant 資料檢查

狀態：已完成

完成事項：
- 已讀取 `C:\Users\user\Desktop\AI_project\course_info_page_codex_final_prompt.md`。
- 已檢查專案根目錄 `C:\Users\user\Desktop\AI_project\ncu_ai_guidance`。
- 已確認 `data/processed/qdrant_data` 存在，不需要解壓縮 `qdrant_data.zip`。
- 已確認以下必要路徑存在：
  - `data/processed/qdrant_data/meta.json`
  - `data/processed/qdrant_data/collection/ncu_courses_ug`
  - `data/processed/qdrant_data/collection/ncu_courses_grad`
- 已確認 `meta.json` 內 `ncu_courses_ug` 與 `ncu_courses_grad` 均為 Cosine 向量 collection，向量維度為 3072。
- 已盤點課程資訊頁主要修改範圍：
  - `frontend/src/pages/CoursesPage.tsx`
  - `frontend/src/components/CourseDetailPanel.tsx`
  - `frontend/src/api/services.ts`
  - `frontend/src/types/index.ts`
  - `backend/app/routes/courses.py`
  - `backend/app/models/schemas.py`

限制與風險紀錄：
- `C:\Users\user\Desktop\AI_project\course_info_page_codex_final_prompt_with_qdrant.md` 目前不存在；後續每個 Phase 仍會重新嘗試讀取並記錄狀態。
- 不會修改 `data/processed/qdrant_data` 原始資料。
- 後續會保留快速搜尋 keyword fallback，避免 Qdrant、embedding 或 OpenAI API key 問題導致課程搜尋不可用。

## Phase 1 - 快速搜尋改成 Qdrant 向量搜尋

狀態：已完成

完成事項：
- 新增 `backend/app/services/course_info_service.py`，提供課程資訊頁專用的 Qdrant semantic search helper。
- 新增 `POST /api/courses/semantic-search`，使用 `OPENAI_API_KEY` 建立 embedding，並優先查詢：
  - `ncu_courses_ug`
  - `ncu_courses_grad`
- 語意搜尋結果會合併兩個 collection、依 Qdrant score 由高到低排序，並轉成既有 `Course` 格式。
- 快速搜尋保留修別、學分、學期篩選。
- Qdrant、embedding 或 OpenAI key 失敗時，後端回傳 `mode: fallback`，前端自動回到原本 keyword search。
- 前端快速搜尋面板已改為自然語言輸入提示，並顯示目前使用 Qdrant 語意搜尋或 keyword fallback。
- 搜尋結果會在有 Qdrant score 時顯示相關度百分比。

驗證：
- 已執行 `python -m compileall backend/app`，後端語法檢查通過。

限制與風險紀錄：
- `course_info_page_codex_final_prompt_with_qdrant.md` 在進入 Phase 1 前重新讀取仍不存在。
- 若環境未設定 `OPENAI_API_KEY`，語意搜尋會按要求 fallback 到 keyword search。

## Phase 2 - 整合 course_eligibility.json 到課程 context

狀態：已完成

完成事項：
- `backend/app/services/course_info_service.py` 已讀取 `data/processed/course_eligibility.json`。
- 已建立課程資格對應策略：
  - 優先使用 `course_code` / `course_id` 正規化後對應。
  - 找不到課號時，使用 `course_name + dept + semester` 與 `course_name + dept` 補充對應。
- 課程列表與 Qdrant 搜尋結果都會附加：
  - `eligibility_summary`
  - `eligibility_status`
  - `eligibility_warning`
- 摘要內容整合 `is_unrestricted`、`is_grad_only`、`is_undergrad_open`、`is_open_to_all_undergrad`、`access_rules` 與 `course_relations`。
- 摘要已包含常見條件：學制、年級、系所、學院、輔系、雙主修、學分學程、第二專長、校際選課、先修、並修與不得重複修習。
- 單門課程 AI context 已納入修課資格摘要、原始條件與解析警示。
- 課程詳情頁新增「修課資格摘要」區塊；若資料缺失或有特殊條件，會以警示樣式顯示。

驗證：
- 已執行 `python -m compileall backend/app`，後端語法檢查通過。

限制與風險紀錄：
- `course_info_page_codex_final_prompt_with_qdrant.md` 在進入 Phase 2 前重新讀取仍不存在。
- `course_eligibility.json` 若沒有可對應資料，頁面會顯示缺失摘要，不會中斷課程頁。

## Phase 3 - 整合 tool / concept / topic metadata

狀態：已完成

完成事項：
- 課程列表與 Qdrant 搜尋結果會帶入既有 NLP metadata：
  - `tools`
  - `concepts`
  - `topic_tags`
  - `domain_tags`
  - `languages`
  - `simplified_concepts`
  - `core_questions`
- 快速搜尋的「詳細內容」模式已納入上述 metadata 與修課資格摘要作為 keyword fallback 搜尋欄位。
- 搜尋結果預覽已顯示最多 3 個工具 / 概念 / 主題 metadata chip。
- 課程詳情頁新增「課程知識標籤」區塊，分組顯示工具、核心概念、主題、領域標籤、語言、簡化概念與核心問題。
- 單門課程 AI context 已納入語言、工具、概念、簡化概念、主題、領域與核心問題。

驗證：
- 已執行 `python -m compileall backend/app`，後端語法檢查通過。
- 已執行 `npm.cmd run build`，前端 production build 通過。

限制與風險紀錄：
- `course_info_page_codex_final_prompt_with_qdrant.md` 在進入 Phase 3 前重新讀取仍不存在。

## Phase 4 - 新增單門課程 OpenAI 問答小窗

狀態：已完成

完成事項：
- 新增 `POST /api/courses/{course_id}/ask`，提供單門課程一次性 OpenAI 問答。
- API 使用 `OPENAI_API_KEY`，可用 `OPENAI_MODEL` 覆寫預設模型；未設定 key 時回傳清楚錯誤訊息。
- 問答 context 只使用課程資料、修課資格與 metadata，不使用既有獨立 Chat 頁面。
- 後端不建立 session、不寫入資料庫、不儲存聊天紀錄。
- 課程詳情頁新增「詢問這門課」按鈕與 modal 小窗。
- 小窗只保留目前這次問題與回答；關閉或切換課程會清空狀態。
- AI 回答區會顯示 context 缺失或資格解析警示。

驗證：
- 已執行 `python -m compileall backend/app`，後端語法檢查通過。
- 已執行 `npm.cmd run build`，前端 production build 通過。

限制與風險紀錄：
- `course_info_page_codex_final_prompt_with_qdrant.md` 在進入 Phase 4 前重新讀取仍不存在。
- 未實際呼叫 OpenAI API；若本機 `.env` 未設定有效 `OPENAI_API_KEY`，小窗會顯示後端提供的缺 key 錯誤。

後續修正：
- 已將課程資訊頁的 embedding 與單門課程問答改為支援 Azure OpenAI。
- 若 `.env` 設定 `AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_CHAT_DEPLOYMENT`、`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`，會優先使用 Azure OpenAI。
- 若未設定 Azure OpenAI，才會退回使用 `OPENAI_API_KEY`。

## 驗證紀錄

狀態：已完成初步驗證

- `python -m compileall backend/app`：通過。
- `npm.cmd run build`：通過。
- Vite build 仍有既有的大 chunk warning，但不影響 build 成功。
