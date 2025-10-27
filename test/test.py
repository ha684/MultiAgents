# {
#   "message": {
#     "role": "user",
#     "parts": [
#       {
#         "type": "text",
#         "text": "i want to know about the recent storm coming to viet nam"
#       }
#     ],
#     "metadata": {
#       "conversation_id": "068f1c40-5a4d-7b74-8000-8f6f76ec074b",
#       "kb_id": "068e7efb-fd5b-7523-8000-3e54cd74ff34",
#       "user_id": "ha",
#       "app_name": "ha"
#     }
#   },
#   "agentic": false,
#   "web_search": false
# }


# from langchain_community.document_loaders import UnstructuredExcelLoader
# loader = UnstructuredExcelLoader(r"C:\workspace\data\サンプル_QMSシステム開発_RD_エンティティ一覧.xlsx", mode="elements", include_header=True, find_subtable=True)
# docs = loader.load()
# for doc in docs:
#     print(doc.page_content)
#     print("-"*100)

# from src.rag.processor.strategy.spreadsheet import SpreadsheetStrategy
# from src.db.models.document import Document as DBDocument
# import os

# db_document = DBDocument(
#     file_path=r"C:\workspace\data\サンプル_QMSシステム開発_RD_エンティティ一覧.xlsx",
#     file_type="xlsx",
#     file_size=os.path.getsize(r"C:\workspace\data\サンプル_QMSシステム開発_RD_エンティティ一覧.xlsx"),
#     filename="サンプル_QMSシスム開発_RD_エンティティ一覧.xlsx",
# )
# loader = sheetStrategy({})
# docs = loader.chunk(r"C:\workspace\data\サンプル_QMSシステム開発_RD_エンティティ一覧.xlsx", db_document)

# for doc in docs:
#     print(doc.page_content)
#     print("-"*100)

# from langchain_pymupdf4llm import PyMuPDF4LLMLoader

# loader = PyMuPDF4LLMLoader(r"C:\workspace\data\2506.09250v1.pdf")
# docs = loader.load()
# for doc in docs:
#     print(doc.page_content)
#     print("-" * 100)
# -*- coding: utf-8 -*-
import fitz  # PyMuPDF
import os
import re
import json
import string
import hashlib

# ====== REGEX ======
ANSWER_RE = re.compile(r"^\s*(\d+)\s*[\.\)]")  # "1. ..." / "1) ..."
QUESTION_RE = re.compile(r"^\s*C[âa]u\s*(\d+)\s*[\.:]", re.IGNORECASE)

# ====== FLAGS / BIT ======
UNDERLINE_BIT = 1 << 1  # char_flags bit 1 = underline (giá trị 2)


# ====== HỖ TRỢ HÌNH ======
def extract_hlines(page, height_thresh=2.0, y_tol=2.0):
    """Lấy các đoạn kẻ ngang (x0, x1, y) từ vector graphics để fallback nhận underline."""
    hlines = []
    for path in page.get_drawings():
        for item in path.get("items", []):
            t = item[0]
            if t == "l":  # line
                p0, p1 = item[1], item[2]
                if abs(p0.y - p1.y) <= y_tol:
                    x0, x1 = sorted([p0.x, p1.x])
                    hlines.append((x0, x1, (p0.y + p1.y) / 2.0))
            elif t == "re":  # thin rectangle ~ underline
                r = item[1]
                try:
                    h = r.y1 - r.y0
                    if h <= height_thresh:
                        hlines.append((r.x0, r.x1, r.y1))  # mép dưới như đường kẻ
                except Exception:
                    pass
    return hlines


def spans_have_underline(spans):
    """Ưu tiên đọc underline từ char_flags của span (PyMuPDF >= 1.25.2)."""
    for sp in spans:
        cf = sp.get("char_flags", 0)
        if cf & UNDERLINE_BIT:
            return True
    return False


def rect_overlap_ratio(ax0, ax1, bx0, bx1):
    inter = max(0, min(ax1, bx1) - max(ax0, bx0))
    base = max(ax1 - ax0, 1e-6)
    return inter / base


def answer_has_vector_underline(line_rects, hlines, y_tol=2.0, x_cover=0.5):
    """Fallback: so khớp đường kẻ ngang với từng dòng của đáp án."""
    for x0, y0, x1, y1 in line_rects:
        for lx0, lx1, ly in hlines:
            if abs(ly - y1) <= y_tol:
                if rect_overlap_ratio(x0, x1, lx0, lx1) >= x_cover:
                    return True
    return False


# ====== TIỆN ÍCH KHÁC ======
LETTERS = list(string.ascii_uppercase)  # A, B, C, ...


def num_to_letter(num_str, fallback_index=None):
    """'1' -> 'A', '2' -> 'B'. Nếu không có số, dùng fallback_index (0-based)."""
    if num_str and num_str.isdigit():
        idx = max(0, int(num_str) - 1)
        return LETTERS[idx] if idx < len(LETTERS) else num_str
    if fallback_index is not None and 0 <= fallback_index < len(LETTERS):
        return LETTERS[fallback_index]
    return num_str or ""


def clean_answer_text(full_text):
    """Bỏ tiền tố '1.' / '1)' ở đầu, giữ lại nội dung."""
    t = re.sub(r"^\s*\d+\s*[\.\)]\s*", "", full_text).strip()
    t = re.sub(r"\s+", " ", t)
    return t


# ====== LỌC ẢNH & TRỘN TEXT/IMAGE THEO THỨ TỰ ĐỌC ======
def should_keep_image(
    rect,
    page_rect,
    px_w,
    px_h,
    min_area_ratio=0.003,  # 0.3% diện tích trang
    min_px_side=120,
):  # cạnh tối thiểu 120 px
    """Bỏ icon nhỏ, ảnh nền hoặc đường kẻ raster hóa."""
    page_area = max((page_rect.width * page_rect.height), 1.0)
    area_ok = (rect.width * rect.height) >= (min_area_ratio * page_area)
    px_ok = (px_w is None or px_h is None) or (
        px_w >= min_px_side and px_h >= min_px_side
    )
    aspect = rect.width / max(rect.height, 1e-6)
    not_line = 0.05 <= aspect <= 20.0
    return area_ok and px_ok and not_line


def build_ordered_elements(
    page, doc, page_hlines, min_area_ratio=0.003, min_px_side=120
):
    """
    Trộn line-text và image theo (y0, x0).
    - Text: page.get_text("dict") -> từng line
    - Image: page.get_images + page.get_image_rects(xref) -> vị trí hiển thị thực tế
    """
    elements = []
    page_rect = page.rect

    # --- TEXT LINES ---
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = " ".join(
                s.get("text", "").strip() for s in spans if s.get("text")
            ).strip()
            if not line_text:
                continue
            elements.append(
                {
                    "type": "text",
                    "text": line_text,
                    "spans": spans,
                    "bbox": tuple(line.get("bbox", (0, 0, 0, 0))),
                    "hlines": page_hlines,  # dùng fallback underline theo trang này
                }
            )

    # --- IMAGES ---
    xref_cache = {}
    for img_tup in page.get_images(full=True):
        xref = img_tup[0]
        if xref in xref_cache:
            base_img = xref_cache[xref]
        else:
            try:
                base_img = doc.extract_image(
                    xref
                )  # {'image','ext','width','height',...}
            except Exception:
                base_img = {}
            xref_cache[xref] = base_img

        px_w = base_img.get("width")
        px_h = base_img.get("height")
        ext = (base_img.get("ext") or "png").lower()
        img_bytes = base_img.get("image")

        try:
            rects = page.get_image_rects(xref)  # list of fitz.Rect nơi ảnh được vẽ
        except Exception:
            rects = []

        for r in rects:
            if not should_keep_image(
                r,
                page_rect,
                px_w,
                px_h,
                min_area_ratio=min_area_ratio,
                min_px_side=min_px_side,
            ):
                continue

            elements.append(
                {
                    "type": "image",
                    "xref": xref,
                    "bbox": (r.x0, r.y0, r.x1, r.y1),
                    "ext": ext,
                    "img_bytes": img_bytes,  # có thể None nếu extract lỗi, sẽ fallback khi lưu
                    "px_w": px_w,
                    "px_h": px_h,
                }
            )

    # Sắp xếp theo thứ tự đọc (từ trên xuống, trái qua phải)
    elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))
    return elements


# ====== TRÍCH TOÀN BỘ PDF & LƯU JSON ======
def extract_questions_answers_images(
    pdf_path,
    out_img_dir,
    out_json_path,
    save_all_images=True,
    min_area_ratio=0.003,
    min_px_side=120,
    store_relative_paths=True,
):
    """
    - Gán ảnh cho câu hỏi theo đúng thứ tự đọc (ảnh xuất hiện sau "Câu N" -> thuộc câu N).
    - Lọc icon/ảnh nền bé; khử trùng lặp ảnh theo hash nội dung.
    - Nhận diện đáp án đúng bằng underline (char_flags) + fallback vector line.
    - JSON:
        * answer           : 'C' (tương thích cũ)
        * answer_text      : 'nội dung đáp án đúng'
        * answer_full      : 'C. nội dung đáp án đúng'
        * every_choices    : ['A. ...', 'B. ...', ...]
        * image_path       : ảnh đầu tiên (relative hoặc absolute tuỳ store_relative_paths)
        * image_paths      : toàn bộ ảnh của câu (cùng kiểu path như trên)
        * image_dir        : thư mục ảnh (absolute) để bạn ghép nếu cần
    """
    # Chuẩn hoá & đảm bảo thư mục ảnh
    out_img_dir = os.path.abspath(out_img_dir)
    os.makedirs(out_img_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    all_results = []  # đưa ra JSON
    current_question = None
    current_answer = None

    def to_json_path(abs_path):
        """Trả về đường dẫn JSON theo cấu hình store_relative_paths."""
        if not abs_path:
            return ""
        abs_path_norm = os.path.normpath(abs_path)
        if store_relative_paths:
            # chỉ lưu tên file để tránh lệch đường dẫn máy khác
            return os.path.basename(abs_path_norm)
        return abs_path_norm

    def flush_answer():
        """Kết thúc 1 đáp án, tính gạch chân & gom text."""
        nonlocal current_answer, current_question
        if current_answer is None or current_question is None:
            return

        # A) underline từ char_flags
        has_ul = any(
            spans_have_underline(sp_group) for sp_group in current_answer["line_spans"]
        )

        # B) fallback vector underline (theo từng dòng, theo hlines cùng trang)
        if not has_ul:
            for rects, hls in zip(
                current_answer["line_bboxes"], current_answer["line_hlines"]
            ):
                if answer_has_vector_underline([rects], hls):
                    has_ul = True
                    break

        joined_text = " ".join(current_answer["lines"]).strip()
        joined_text = re.sub(r"\s+", " ", joined_text)
        clean_text = clean_answer_text(joined_text)

        # Gán letter + lưu
        letter = current_answer["letter"]
        current_question["choices"].append(
            {"letter": letter, "text": clean_text, "is_correct": has_ul}
        )

        current_answer = None

    def flush_question(final=False):
        """Kết thúc 1 câu hỏi -> đẩy sang all_results (và đổi sang cấu trúc JSON mong muốn)."""
        nonlocal current_question, all_results
        if current_question is None:
            return

        # Kết thúc đáp án còn dở
        flush_answer()

        # Xây JSON item
        q_text = " ".join(current_question["question_full"]).strip()
        q_text = re.sub(r"\s+", " ", q_text)

        # danh sách lựa chọn hiển thị "A. text"
        every_choices_list = [
            f"{c['letter']}. {c['text']}" for c in current_question["choices"]
        ]

        # đáp án đúng
        correct_letter = ""
        correct_text = ""
        for c in current_question["choices"]:
            if c["is_correct"]:
                correct_letter = c["letter"]
                correct_text = c["text"]
                break

        answer_full = (
            f"{correct_letter}. {correct_text}".strip(". ").strip()
            if correct_letter
            else ""
        )

        image_paths_abs = [im["path"] for im in current_question.get("images", [])]
        image_paths_json = [to_json_path(p) for p in image_paths_abs]
        image_path_json = image_paths_json[0] if image_paths_json else ""
        all_results.append(
            {
                "question": q_text,
                "answer": correct_letter,
                "answer_text": correct_text,
                "answer_full": answer_full,
                "every_choices": every_choices_list,
                "image_name": image_path_json,
            }
        )

        current_question = None

    # === DUYỆT TỪNG TRANG, GOM TEXT LINE + IMAGE BLOCK THEO THỨ TỰ Y ===
    for page_num in range(total_pages):
        page = doc[page_num]
        page_hlines = extract_hlines(page)

        # Gom element (text lines + images), sort theo y0 rồi x0 để giữ thứ tự đọc
        elements = build_ordered_elements(
            page,
            doc,
            page_hlines,
            min_area_ratio=min_area_ratio,
            min_px_side=min_px_side,
        )

        # === ĐỌC ELEMENT THEO THỨ TỰ ===
        for el in elements:
            if el["type"] == "text":
                text = el["text"]

                # Bắt đầu câu hỏi mới
                m_q = QUESTION_RE.match(text)
                if m_q:
                    # chốt câu trước
                    flush_question()

                    q_num = int(m_q.group(1))
                    current_question = {
                        "number": q_num,
                        "question_full": [text],  # có thể kéo dài nhiều dòng
                        "choices": [],
                        "images": [],  # lưu danh sách ảnh
                    }
                    current_answer = None
                    continue

                # Nếu đang trong 1 câu hỏi, thử xem đây có phải dòng đáp án mới
                if current_question is not None:
                    m_a = ANSWER_RE.match(text)
                    if m_a:
                        # chốt đáp án trước (nếu có)
                        flush_answer()
                        num_str = m_a.group(1) if m_a else None
                        fallback_idx = len(current_question["choices"])
                        letter = num_to_letter(num_str, fallback_index=fallback_idx)

                        current_answer = {
                            "lines": [text],
                            "line_spans": [el["spans"]],
                            "line_bboxes": [el["bbox"]],
                            "line_hlines": [el["hlines"]],
                            "letter": letter,
                        }
                        continue

                    # Dòng tiếp nối của đáp án
                    if current_answer is not None:
                        current_answer["lines"].append(text)
                        current_answer["line_spans"].append(el["spans"])
                        current_answer["line_bboxes"].append(el["bbox"])
                        current_answer["line_hlines"].append(el["hlines"])
                    # Phần mô tả dài của câu hỏi
                    elif current_question is not None:
                        current_question["question_full"].append(text)

            elif el["type"] == "image":
                # Ảnh xuất hiện trong phạm vi của câu hiện tại
                if current_question is not None:
                    try:
                        # Ưu tiên bytes đã cache
                        img_bytes = el.get("img_bytes")
                        ext = el.get("ext", "png")
                        if not img_bytes:
                            img = doc.extract_image(el["xref"])
                            img_bytes = img["image"]
                            ext = (img.get("ext") or "png").lower()

                        # Khử trùng lặp theo hash (trường hợp cùng xref vẽ nhiều lần / scale khác)
                        h = hashlib.md5(img_bytes).hexdigest()
                        existing_hashes = {
                            x.get("hash") for x in current_question["images"]
                        }
                        if h in existing_hashes:
                            continue

                        # Tên file: Q{number}_{index}.{ext}
                        idx = len(current_question["images"]) + 1
                        fname = f"Q{current_question['number']}_{idx}.{ext}"
                        abs_save_path = os.path.join(out_img_dir, fname)
                        abs_save_path = os.path.normpath(abs_save_path)

                        # Lưu file
                        with open(abs_save_path, "wb") as f:
                            f.write(img_bytes)

                        # Xác thực tồn tại
                        if not os.path.exists(abs_save_path):
                            # rất hiếm: thử đổi sang .png
                            alt_path = os.path.splitext(abs_save_path)[0] + ".png"
                            with open(alt_path, "wb") as f:
                                f.write(img_bytes)
                            abs_save_path = alt_path

                        current_question["images"].append(
                            {
                                "path": abs_save_path,  # luôn absolute để chắc chắn
                                "hash": h,
                                "bbox": el["bbox"],
                                "px": (el.get("px_w"), el.get("px_h")),
                            }
                        )

                    except Exception:
                        # Không cản luồng nếu trích ảnh lỗi
                        pass

    # Hết tài liệu: chốt phần đang dở
    flush_question(final=True)
    doc.close()

    # Ghi JSON
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    return all_results


if __name__ == "__main__":
    # === THAY ĐƯỜNG DẪN Ở ĐÂY ===
    pdf_path = r"C:\Users\ha.phan\Downloads\273963059_Bộ 600 câu hỏi dùng cho sát hạch lái xe cơ giới đường bộ.pdf"
    out_img_dir = r"C:\Users\ha.phan\Downloads\bo600_images"
    out_json_path = r"C:\Users\ha.phan\Downloads\bo600_questions.json"

    # Tuỳ chỉnh ngưỡng lọc ảnh nếu còn dính icon nhỏ:
    # - Tăng min_area_ratio lên 0.005 (0.5%) hoặc
    # - Tăng min_px_side lên 160
    try:
        results = extract_questions_answers_images(
            pdf_path=pdf_path,
            out_img_dir=out_img_dir,
            out_json_path=out_json_path,
            save_all_images=True,  # True: lưu mọi ảnh của câu; False: chỉ quan tâm ảnh đầu
            min_area_ratio=0.003,
            min_px_side=120,
            store_relative_paths=True,  # True -> trong JSON chỉ ghi tên file; kèm "image_dir"
        )
        print(f"✅ Đã trích {len(results)} câu hỏi.")
        print(f"💾 JSON: {out_json_path}")
        print(f"🖼️ Ảnh lưu tại: {os.path.abspath(out_img_dir)}")
        print(
            "ℹ️  Trong JSON: 'image_dir' là thư mục ảnh (absolute), "
            "'image_path'/'image_paths' là tên file (relative)."
        )
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {pdf_path}")
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
