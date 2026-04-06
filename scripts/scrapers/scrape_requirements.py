"""
爬取中央大學各系應修科目表 PDF
來源: https://pdc.adm.ncu.edu.tw/p/426-1019-7.php?Lang=zh-tw
輸出到: 應修科目表_114/
"""

import os
import time
import requests

BASE_URL = "https://pdc.adm.ncu.edu.tw"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "raw", "應修科目表")

# 完整科系列表 (學院 -> [(檔名, PDF路徑)])
DEPARTMENTS = {
    "文學院": [
        ("中國文學系", "/static/file/19/1019/img/310/331849229.pdf"),
        ("英美語文學系", "/static/file/19/1019/img/310/702478353.pdf"),
        ("法國語文學系", "/static/file/19/1019/img/310/146418916.pdf"),
        ("文學院學士班", "/static/file/19/1019/img/310/217284896.pdf"),
    ],
    "理學院": [
        ("數學系_數學科學組", "/static/file/19/1019/img/310/849923274.pdf"),
        ("數學系_計算與資料科學組", "/static/file/19/1019/img/310/191828402.pdf"),
        ("化學學系", "/static/file/19/1019/img/310/510742566.pdf"),
        ("物理學系", "/static/file/19/1019/img/310/451696396.pdf"),
        ("光電科學與工程學系", "/static/file/19/1019/img/310/499611076.pdf"),
        ("理學院學士班", "/static/file/19/1019/img/310/174926303.pdf"),
        ("理學院學士班_數學領域專長", "/static/file/19/1019/img/310/110846977.pdf"),
        ("理學院學士班_物理領域專長", "/static/file/19/1019/img/310/692542576.pdf"),
        ("理學院學士班_化學領域專長", "/static/file/19/1019/img/310/437330708.pdf"),
        ("理學院學士班_光電科學與工程領域專長", "/static/file/19/1019/img/310/499611076.pdf"),
        ("理學院學士班_生命科學領域專長", "/static/file/19/1019/img/310/732487798.pdf"),
        ("理學院學士班_生醫領域專長", "/static/file/19/1019/img/310/805107672.pdf"),
    ],
    "工學院": [
        ("土木工程學系", "/static/file/19/1019/img/310/479964354.pdf"),
        ("機械工程學系_光機電工程組", "/static/file/19/1019/img/310/126417600.pdf"),
        ("機械工程學系_先進材料與精密製造組", "/static/file/19/1019/img/310/588620051.pdf"),
        ("機械工程學系_設計與分析組", "/static/file/19/1019/img/310/444964625.pdf"),
        ("化學工程與材料工程學系", "/static/file/19/1019/img/310/916986166.pdf"),
        ("工學院學士班", "/static/file/19/1019/img/310/299345601.pdf"),
        ("工學院學士班_智慧機械專長", "/static/file/19/1019/img/310/692619762.pdf"),
        ("工學院學士班_能源材料專長", "/static/file/19/1019/img/310/164713556.pdf"),
        ("工學院學士班_永續防災專長", "/static/file/19/1019/img/310/463142222.pdf"),
        ("工學院學士班_綠色科技專長", "/static/file/19/1019/img/310/718632014.pdf"),
    ],
    "管理學院": [
        ("企業管理學系", "/static/file/19/1019/img/310/472406402.pdf"),
        ("資訊管理學系", "/static/file/19/1019/img/310/840445846.pdf"),
        ("財務金融學系", "/static/file/19/1019/img/237/133265376.pdf"),
        ("經濟學系", "/static/file/19/1019/img/310/469514125.pdf"),
    ],
    "資訊電機學院": [
        ("電機工程學系", "/static/file/19/1019/img/310/597140605.pdf"),
        ("資訊工程學系", "/static/file/19/1019/img/310/242199939.pdf"),
        ("通訊工程學系", "/static/file/19/1019/img/310/330918976.pdf"),
        ("資訊電機學院學士班", "/static/file/19/1019/img/310/344867666.pdf"),
        ("資訊電機學院學士班_資訊工程專長", "/static/file/19/1019/img/310/782181762.pdf"),
        ("資訊電機學院學士班_網路工程專長", "/static/file/19/1019/img/310/791962031.pdf"),
        ("資電學院各系等同課程對照表", "/static/file/19/1019/img/310/523781034.pdf"),
    ],
    "地球科學學院": [
        ("大氣科學學系", "/static/file/19/1019/img/310/121491227.pdf"),
        ("地球科學學系", "/static/file/19/1019/img/310/820231450.pdf"),
        ("太空科學與工程學系", "/static/file/19/1019/img/310/396780656.pdf"),
        ("地科院學士班", "/static/file/19/1019/img/310/764795648.pdf"),
    ],
    "客家學院": [
        ("客家語文暨社會科學學系_社政組", "/static/file/19/1019/img/310/828071693.pdf"),
        ("客家語文暨社會科學學系_語文組", "/static/file/19/1019/img/310/781155435.pdf"),
    ],
    "生醫理工學院": [
        ("生命科學系", "/static/file/19/1019/img/310/434352278.pdf"),
        ("生醫科學與工程學系", "/static/file/19/1019/img/310/576287305.pdf"),
    ],
}


def download_pdf(name, path, college_dir, session):
    url = BASE_URL + path
    filename = f"{name}_114.pdf"
    filepath = os.path.join(college_dir, filename)

    # 跳過重複 (相同 URL 但不同名稱，例如光電領域專長與光電學系同一 PDF)
    if os.path.exists(filepath):
        print(f"  已存在，跳過: {filename}")
        return True

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
        print(f"  ✓ {filename} ({len(resp.content)//1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ {filename}: {e}")
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"輸出目錄: {OUTPUT_DIR}\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://pdc.adm.ncu.edu.tw/p/426-1019-7.php?Lang=zh-tw",
    })

    total, success = 0, 0
    for college, depts in DEPARTMENTS.items():
        college_dir = os.path.join(OUTPUT_DIR, college)
        os.makedirs(college_dir, exist_ok=True)
        print(f"【{college}】")

        for name, path in depts:
            total += 1
            ok = download_pdf(name, path, college_dir, session)
            if ok:
                success += 1
            time.sleep(0.5)  # 禮貌性延遲

    print(f"\n完成: {success}/{total} 個 PDF 下載成功")
    print(f"儲存於: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
