"""
產生 schedule_review.html：人工審核 schedule_draft 的課程年級/學期介面。

讀取 data/processed/schedule_draft/學院/系所.json
左欄：學院 → 系所 二層導覽
主區：課程表格，下拉選 when，勾選 verified，填備注
Export：下載修改後的 JSON（格式與 schedule_draft 相同）
"""

import json
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent.parent.parent
DRAFT_DIR = BASE_DIR / "data" / "processed" / "schedule_draft"
OUT_HTML  = BASE_DIR / "schedule_review.html"

WHEN_OPTIONS = [
    "",
    # ── 每年固定學期 ─────────────────────────
    "僅上學期", "僅下學期",
    # ── 單學期 ──────────────────────────────
    "大一上", "大一下",
    "大二上", "大二下",
    "大三上", "大三下",
    "大四上", "大四下",
    # ── 同年跨學期 ──────────────────────────
    "大一上~大一下",
    "大二上~大二下",
    "大三上~大三下",
    "大四上~大四下",
    # ── 跨年（相鄰） ────────────────────────
    "大一下~大二上",
    "大二下~大三上",
    "大三下~大四上",
    # ── 跨年（兩年期） ──────────────────────
    "大一上~大二上",
    "大一上~大二下",
    "大一下~大二下",
    "大二上~大三上",
    "大二上~大三下",
    "大二下~大三下",
    "大三上~大四上",
    "大三上~大四下",
    "大三下~大四下",
    # ── 跨年（三年期） ──────────────────────
    "大一上~大三上",
    "大一上~大三下",
    "大一下~大三下",
    "大二上~大四上",
    "大二上~大四下",
    # ── 跨年（四年期） ──────────────────────
    "大一上~大四上",
    "大一上~大四下",
    "大一下~大四下",
]

# ── 讀取所有 schedule_draft 資料 ─────────────────────────────
# 結構：{ "學院名": { "系所名": { ...dept_json... } } }
all_data: dict = {}
stats_data: dict = {}   # 快速統計用

for college_dir in sorted(DRAFT_DIR.iterdir()):
    if not college_dir.is_dir():
        continue
    col_name = college_dir.name
    all_data[col_name] = {}
    stats_data[col_name] = {}

    for dept_file in sorted(college_dir.glob("*.json")):
        dept_name = dept_file.stem
        dept_data = json.loads(dept_file.read_text(encoding="utf-8"))
        all_data[col_name][dept_name] = dept_data

# ── 遞迴收集所有課程（供統計） ────────────────────────────────
def collect_courses(node):
    cs = []
    if isinstance(node, dict):
        if "code" in node and "verified" in node:
            cs.append(node)
        for v in node.values():
            if isinstance(v, (dict, list)):
                cs.extend(collect_courses(v))
    elif isinstance(node, list):
        for item in node:
            cs.extend(collect_courses(item))
    return cs

for col_name, depts in all_data.items():
    for dept_name, dept_data in depts.items():
        courses = collect_courses(dept_data)
        total    = len(courses)
        filled   = sum(1 for c in courses if c.get("when"))
        verified = sum(1 for c in courses if c.get("verified"))
        stats_data[col_name][dept_name] = {
            "total": total, "filled": filled, "verified": verified
        }

data_json  = json.dumps(all_data,   ensure_ascii=False)
stats_json = json.dumps(stats_data, ensure_ascii=False)

options_html = "\n".join(
    f'<option value="{v}">{v if v else "（待填）"}</option>'
    for v in WHEN_OPTIONS
)

HTML = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>應修課程年級審核</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Noto Sans TC', sans-serif; font-size: 13px;
       display: flex; height: 100vh; overflow: hidden; background: #f5f5f5; }}

/* ── sidebar ── */
#sidebar {{ width: 200px; background: #1e272e; color: #dfe6e9; overflow-y: auto;
            flex-shrink: 0; }}
#sidebar h3 {{ color: #74b9ff; padding: 10px 12px 6px; font-size: 11px;
               text-transform: uppercase; letter-spacing: 1px; }}
.col-group {{ border-bottom: 1px solid #2d3436; }}
.col-header {{ width: 100%; background: none; border: none; color: #a0adb4;
               text-align: left; padding: 6px 12px; cursor: pointer;
               font-size: 12px; font-weight: bold; display: flex;
               justify-content: space-between; align-items: center; }}
.col-header:hover {{ background: #2d3436; color: white; }}
.col-header.open {{ color: #74b9ff; }}
.col-header .arrow {{ font-size: 10px; transition: transform .2s; }}
.col-header.open .arrow {{ transform: rotate(90deg); }}
.dept-list {{ display: none; }}
.dept-list.open {{ display: block; }}
.dept-btn {{ display: block; width: 100%; background: none; border: none;
             color: #b2bec3; text-align: left; padding: 5px 12px 5px 22px;
             cursor: pointer; font-size: 11px; border-left: 3px solid transparent; }}
.dept-btn:hover {{ background: #2d3436; }}
.dept-btn.active {{ border-left-color: #74b9ff; color: white; background: #2d3436; }}
.dept-btn small {{ display: block; color: #636e72; font-size: 10px; margin-top: 1px; }}

/* ── main ── */
#main {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
#toolbar {{ background: #2d3436; color: white; padding: 7px 14px;
            display: flex; gap: 10px; align-items: center; flex-shrink: 0; }}
#toolbar button {{ padding: 4px 12px; border: none; border-radius: 3px;
                   cursor: pointer; font-size: 12px; }}
#btn-filter {{ background: #0984e3; color: white; }}
#btn-filter.on {{ background: #e17055; }}
#btn-export {{ background: #00b894; color: white; }}
#page-title {{ font-weight: bold; font-size: 13px; flex: 1; }}
#stats-bar {{ font-size: 11px; color: #a0adb4; }}

#content {{ flex: 1; overflow-y: auto; padding: 14px; }}

/* ── section blocks ── */
.section-block {{ background: white; border-radius: 6px; margin-bottom: 14px;
                  box-shadow: 0 1px 3px rgba(0,0,0,.1); overflow: hidden; }}
.section-hdr {{ background: #dfe6e9; padding: 7px 14px; font-size: 12px;
                color: #2d3436; font-weight: bold; border-bottom: 1px solid #ccc;
                cursor: pointer; display: flex; justify-content: space-between; }}
.section-hdr:hover {{ background: #d0d8dd; }}
.section-hdr.slot-hdr {{ background: #e8f4fd; border-left: 4px solid #0984e3; }}
.section-hdr.slot-hdr::before {{ content: '⬡ '; color: #0984e3; }}
.dual-major-badge {{ display: inline-block; margin-left: 8px; padding: 1px 7px; background: #6c5ce7; color: #fff; border-radius: 10px; font-size: 0.75em; font-weight: 700; vertical-align: middle; letter-spacing: 0.03em; }}
.section-body {{ overflow-x: auto; }}

/* ── table ── */
table {{ width: 100%; border-collapse: collapse; min-width: 620px; }}
th {{ background: #f8f9fa; padding: 6px 10px; text-align: left; font-size: 11px;
      color: #636e72; border-bottom: 2px solid #dee2e6; white-space: nowrap; }}
tr.crow {{ border-bottom: 1px solid #f1f3f5; transition: background .1s; }}
tr.crow:hover {{ background: #f8f9fa; }}
tr.crow.pending  {{ background: #fff8f2; }}
tr.crow.done     {{ background: #f0fff4; }}
tr.crow.filtered {{ display: none; }}
td {{ padding: 5px 10px; vertical-align: middle; font-size: 12px; }}
td.tc {{ font-family: monospace; color: #0984e3; white-space: nowrap; min-width: 80px; }}
td.tn {{ color: #2d3436; max-width: 200px; }}
td.tcr {{ text-align: center; color: #636e72; white-space: nowrap; }}
td.tw {{ white-space: nowrap; }}

select.wsel {{ border: 1px solid #ddd; border-radius: 3px; padding: 3px 6px;
               font-size: 12px; min-width: 108px; background: white; cursor: pointer; }}
select.wsel.filled {{ border-color: #00b894; background: #f0fff9; }}
select.wsel.empty  {{ border-color: #e17055; background: #fff5f2; }}

input.ni {{ border: 1px solid #e0e0e0; border-radius: 3px; padding: 3px 6px;
            font-size: 11px; width: 110px; color: #636e72; }}
input.ni:focus {{ outline: none; border-color: #74b9ff; }}

.chkv {{ transform: scale(1.3); cursor: pointer; accent-color: #6c5ce7; }}
.atag {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; white-space: nowrap; }}
.atag.a {{ background: #55efc4; color: #2d3436; }}
.atag.m {{ background: #fab1a0; color: #2d3436; }}
</style>
</head>
<body>

<div id="sidebar">
  <h3>系所</h3>
  <div id="col-list"></div>
</div>

<div id="main">
  <div id="toolbar">
    <span id="page-title">← 選擇系所</span>
    <span id="stats-bar"></span>
    <button id="btn-filter">只看待確認</button>
    <button id="btn-export">⬇ 匯出 JSON</button>
  </div>
  <div id="content">
    <p style="color:#999;padding:24px;">← 從左側選擇學院和系所開始審核</p>
  </div>
</div>

<script>
const ALL   = {data_json};
const STATS = {stats_json};
const WHEN_OPTIONS = {json.dumps(WHEN_OPTIONS, ensure_ascii=False)};

let data = JSON.parse(JSON.stringify(ALL));
let curCollege = null, curDept = null;
let filterOn = false;

// ── sidebar 建立 ──────────────────────────────────────────────
const colList = document.getElementById('col-list');
Object.entries(data).forEach(([col, depts]) => {{
  const grp  = document.createElement('div'); grp.className = 'col-group';
  const hdr  = document.createElement('button'); hdr.className = 'col-header';
  hdr.innerHTML = col + '<span class="arrow">▶</span>';
  hdr.onclick = () => {{
    hdr.classList.toggle('open');
    dlist.classList.toggle('open');
  }};
  const dlist = document.createElement('div'); dlist.className = 'dept-list';

  Object.entries(STATS[col] || {{}}).forEach(([dept, s]) => {{
    const btn = document.createElement('button');
    btn.className = 'dept-btn';
    btn.dataset.col = col; btn.dataset.dept = dept;
    btn.innerHTML = dept + '<small>' + s.filled + '/' + s.total
      + ' 填寫・' + s.verified + ' 確認</small>';
    btn.onclick = () => loadDept(col, dept);
    dlist.appendChild(btn);
  }});

  grp.appendChild(hdr); grp.appendChild(dlist);
  colList.appendChild(grp);
}});

// ── load dept ────────────────────────────────────────────────
function loadDept(col, dept) {{
  curCollege = col; curDept = dept;
  document.querySelectorAll('.dept-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.col===col && b.dataset.dept===dept));
  document.getElementById('page-title').textContent = col + ' ／ ' + dept;
  renderContent();
  updateStatsBar();
}}

function renderContent() {{
  const el = document.getElementById('content');
  el.innerHTML = '';
  if (!curCollege || !curDept) return;
  const deptData = data[curCollege][curDept];
  buildSections(deptData, el, curCollege, curDept, []);
  applyFilter();
}}

// ── 遞迴建立 sections ─────────────────────────────────────────
const SECTION_LABELS = {{
  required_courses: '必修課程',
  elective_groups: '選修課程',
  groups: '課程群組',
  tracks: '學程/組別',
  core_elective_groups: '核心選修',
  required_electives: '必選修',
  college_required_courses: '學院必修',
  common_required_courses: '共同必修',
  foundation_courses: '基礎課程',
  application_courses: '應用課程',
  specialization_tracks: '專長學程',
  earth_system_courses: '地球系統課程',
  cross_domain_required: '跨域必修',
  dept_required_courses: '系訂必修',
  science_ability_groups: '科學能力必修課群',
  college_required_elective_groups: '院必修選修',
  other_elective_groups: '其他選修',
}};

const SKIP_KEYS = new Set(['id','name','program_type','min_credits','required_credits',
  'elective_credits','total_structured_credits','graduation_rules','certifications',
  'common_required_credits','college_required_credits','foundation_credits',
  'professional_credits','application_credits','min_credits_note',
  'college_required_elective_courses_note']);

function buildSections(node, container, col, dept, path) {{
  if (!node || typeof node !== 'object') return;

  Object.entries(node).forEach(([key, val]) => {{
    if (SKIP_KEYS.has(key)) return;
    if (!Array.isArray(val) && typeof val !== 'object') return;

    const label = SECTION_LABELS[key] || key;

    if (Array.isArray(val)) {{
      // 直接課程陣列
      if (val.length && val[0]?.code !== undefined && val[0]?.verified !== undefined) {{
        addCourseTable(container, label, val, col, dept, path.concat(key));
      }}
      // 群組陣列（有 name/courses）
      else if (val.length && (val[0]?.courses || val[0]?.required_courses || val[0]?.name)) {{
        val.forEach((grp, gi) => {{
          const dualBadge = grp.dual_major_only ? '<span class="dual-major-badge">雙主修</span>' : '';
          const grpLabel = label + (grp.name ? '：' + grp.name : ' ' + (gi+1)) + dualBadge;
          const newPath  = path.concat(key, gi);
          // 群組內直接課程
          if (grp.courses) addCourseTable(container, grpLabel, grp.courses, col, dept, newPath.concat('courses'));
          if (grp.required_courses) addCourseTable(container, grpLabel + '（必修）', grp.required_courses, col, dept, newPath.concat('required_courses'));
          if (grp.elective_courses) addCourseTable(container, grpLabel + '（選修）', grp.elective_courses, col, dept, newPath.concat('elective_courses'));
          // option_a / option_b / option_c（三選N 結構）
          const OPT_LABELS = {{option_a:'選項A', option_b:'選項B', option_c:'選項C'}};
          Object.entries(OPT_LABELS).forEach(([optKey, optLabel]) => {{
            if (grp[optKey]) addCourseTable(container,
              grpLabel + '／' + optLabel,
              grp[optKey], col, dept, newPath.concat(optKey));
          }});
          // slots（擇一課程群）
          if (grp.slots) grp.slots.forEach((slot, si) => {{
            if (slot.courses && slot.courses.length) {{
              addCourseTable(container,
                grpLabel + '／' + (slot.slot_name || ('擇一' + (si+1))),
                slot.courses, col, dept,
                newPath.concat('slots', si, 'courses'), true);
            }}
          }});
          // 群組內再一層 elective_groups（含巢狀 option_a/b/c 與 slots）
          if (grp.elective_groups) grp.elective_groups.forEach((eg, egi) => {{
            const egLabel = grpLabel + '／' + (eg.name || '選修' + egi);
            const egPath  = newPath.concat('elective_groups', egi);
            if (eg.courses) addCourseTable(container, egLabel, eg.courses, col, dept, egPath.concat('courses'));
            const OPT2 = {{option_a:'選項A', option_b:'選項B', option_c:'選項C'}};
            Object.entries(OPT2).forEach(([optKey, optLabel]) => {{
              if (eg[optKey]) addCourseTable(container,
                egLabel + '／' + optLabel, eg[optKey], col, dept, egPath.concat(optKey));
            }});
            if (eg.slots) eg.slots.forEach((slot, si) => {{
              if (slot.courses && slot.courses.length) addCourseTable(container,
                egLabel + '／' + (slot.slot_name || '擇一' + (si+1)),
                slot.courses, col, dept, egPath.concat('slots', si, 'courses'), true);
            }});
          }});
        }});
      }}
    }} else if (typeof val === 'object' && val !== null) {{
      buildSections(val, container, col, dept, path.concat(key));
    }}
  }});
}}

function addCourseTable(container, label, courses, col, dept, path, isSlot=false) {{
  if (!courses?.length) return;
  const block = document.createElement('div'); block.className = 'section-block';
  const hdr   = document.createElement('div'); hdr.className = 'section-hdr';
  if (isSlot) hdr.classList.add('slot-hdr');
  const count = courses.length;
  const filled = courses.filter(c => c.when).length;
  hdr.innerHTML = label + '<span>' + filled + '/' + count + ' 填寫</span>';
  hdr.onclick = () => body.style.display = body.style.display === 'none' ? '' : 'none';
  const body = document.createElement('div'); body.className = 'section-body';
  body.appendChild(buildTable(courses, col, dept, path));
  block.appendChild(hdr); block.appendChild(body);
  container.appendChild(block);
}}

// ── 建立課程表格 ───────────────────────────────────────────────
function buildTable(courses, col, dept, path) {{
  const tbl = document.createElement('table');
  const tr0 = tbl.createTHead().insertRow();
  ['課號','課程名稱','學分','年級/學期','偵測','已確認','備注'].forEach(h => {{
    const th = document.createElement('th'); th.textContent = h; tr0.appendChild(th);
  }});
  const tbody = tbl.createTBody();
  courses.forEach((course, ci) => {{
    const tr = tbody.insertRow();
    tr.className = 'crow ' + rowClass(course);

    // 課號
    const tdC = tr.insertCell(); tdC.className = 'tc';
    tdC.textContent = course.code || '—';

    // 課名
    const tdN = tr.insertCell(); tdN.className = 'tn';
    tdN.textContent = course.name || '';

    // 學分
    const tdCr = tr.insertCell(); tdCr.className = 'tcr';
    tdCr.textContent = course.credits || '';

    // when select
    const tdW = tr.insertCell(); tdW.className = 'tw';
    const sel = buildWhenSelect(course, () => {{
      setField(col, dept, path, ci, 'when', sel.value);
      sel.className = 'wsel ' + (sel.value ? 'filled' : 'empty');
      tr.className = 'crow ' + rowClass(getCourse(col, dept, path, ci));
      updateStatsBar(); refreshDeptBtn(col, dept);
    }});
    tdW.appendChild(sel);

    // auto tag
    const tdA = tr.insertCell();
    const tag = document.createElement('span');
    tag.className = 'atag ' + (course.when_auto ? 'a' : 'm');
    tag.textContent = course.when_auto ? '自動' : '手動';
    tdA.appendChild(tag);

    // verified
    const tdV = tr.insertCell(); tdV.style.textAlign = 'center';
    const chk = document.createElement('input');
    chk.type = 'checkbox'; chk.className = 'chkv'; chk.checked = !!course.verified;
    chk.onchange = () => {{
      setField(col, dept, path, ci, 'verified', chk.checked);
      tr.className = 'crow ' + rowClass(getCourse(col, dept, path, ci));
      updateStatsBar(); refreshDeptBtn(col, dept);
    }};
    tdV.appendChild(chk);

    // note
    const tdNo = tr.insertCell();
    const ni = document.createElement('input');
    ni.type = 'text'; ni.className = 'ni'; ni.placeholder = '備注';
    ni.value = course.note || '';
    ni.oninput = () => setField(col, dept, path, ci, 'note', ni.value);
    tdNo.appendChild(ni);
  }});
  return tbl;
}}

function buildWhenSelect(course, onchange) {{
  const sel = document.createElement('select');
  sel.className = 'wsel ' + (course.when ? 'filled' : 'empty');
  WHEN_OPTIONS.forEach(opt => {{
    const o = document.createElement('option');
    o.value = opt; o.textContent = opt || '（待填）';
    if (opt === (course.when || '')) o.selected = true;
    sel.appendChild(o);
  }});
  sel.onchange = onchange;
  return sel;
}}

function rowClass(c) {{
  if (c?.verified)  return 'done';
  if (!c?.when_auto || !c?.when) return 'pending';
  return '';
}}

// ── 資料存取 ──────────────────────────────────────────────────
function getCourse(col, dept, path, ci) {{
  let node = data[col][dept];
  for (const k of path) node = node[k];
  return node[ci];
}}

function setField(col, dept, path, ci, field, value) {{
  getCourse(col, dept, path, ci)[field] = value;
}}

// ── 篩選 ──────────────────────────────────────────────────────
document.getElementById('btn-filter').onclick = () => {{
  filterOn = !filterOn;
  const btn = document.getElementById('btn-filter');
  btn.classList.toggle('on', filterOn);
  btn.textContent = filterOn ? '顯示全部' : '只看待確認';
  applyFilter();
}};

function applyFilter() {{
  document.querySelectorAll('.crow').forEach(tr => {{
    if (filterOn) {{
      tr.classList.toggle('filtered',
        tr.classList.contains('done') || (!tr.classList.contains('pending')));
    }} else {{
      tr.classList.remove('filtered');
    }}
  }});
}}

// ── 統計 ──────────────────────────────────────────────────────
function updateStatsBar() {{
  if (!curCollege || !curDept) return;
  const courses = collectCourses(data[curCollege][curDept]);
  const total    = courses.length;
  const filled   = courses.filter(c => c.when).length;
  const verified = courses.filter(c => c.verified).length;
  document.getElementById('stats-bar').textContent =
    `填寫 ${{filled}}/${{total}} · 確認 ${{verified}}/${{total}}`;
}}

function refreshDeptBtn(col, dept) {{
  const courses  = collectCourses(data[col][dept]);
  const total    = courses.length;
  const filled   = courses.filter(c => c.when).length;
  const verified = courses.filter(c => c.verified).length;
  const btn = document.querySelector(`.dept-btn[data-col="${{col}}"][data-dept="${{dept}}"]`);
  if (btn) btn.querySelector('small').textContent =
    filled + '/' + total + ' 填寫・' + verified + ' 確認';
}}

function collectCourses(node) {{
  const cs = [];
  function walk(n) {{
    if (!n) return;
    if (Array.isArray(n)) n.forEach(walk);
    else if (typeof n === 'object') {{
      if (n.code !== undefined && n.verified !== undefined) cs.push(n);
      else Object.values(n).forEach(v => {{ if (typeof v === 'object') walk(v); }});
    }}
  }}
  walk(node);
  return cs;
}}

// ── 匯出 ──────────────────────────────────────────────────────
document.getElementById('btn-export').onclick = () => {{
  if (!curCollege || !curDept) return alert('請先選擇系所');
  const out = data[curCollege][curDept];
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = curDept + '.json';
  a.click();
}};
</script>
</body>
</html>
"""

OUT_HTML.write_text(HTML, encoding="utf-8")

# 統計
total = auto = 0
for col_depts in all_data.values():
    for dept_data in col_depts.values():
        for c in (lambda node, cs=[]: (
            [cs.append(item) for item in (
                [i for sublist in [collect_courses(v) for v in (node.values() if isinstance(node, dict) else [])] for i in sublist]
                if isinstance(node, dict) else []
            )] or cs
        ))(dept_data):
            pass

# 簡化統計
for col_depts in stats_data.values():
    for s in col_depts.values():
        total += s["total"]
        auto  += s["filled"]  # 這裡 filled = 有 when 的

print(f"✅ 已輸出：{OUT_HTML}")
print(f"   {sum(len(v) for v in all_data.values())} 個系所，審核介面已更新")
