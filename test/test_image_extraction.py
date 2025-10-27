from PIL import Image
import fitz  # PyMuPDF
import io
import os  # Thêm import os


def read_pdf_with_images(pdf_path, output_folder="extracted_images", num_pages=3):
    """
    Đọc PDF, trích xuất văn bản và lưu hình ảnh vào một thư mục

    Args:
        pdf_path: Đường dẫn đến file PDF
        output_folder: Tên thư mục để lưu ảnh
        num_pages: Số trang muốn đọc (mặc định là 3)
    """

    # Tạo thư mục output nếu chưa tồn tại
    os.makedirs(output_folder, exist_ok=True)

    # Mở file PDF với PyMuPDF
    try:
        pdf_document = fitz.open(pdf_path)
    except fitz.errors.EmptyFileError:
        print(f"❌ Lỗi: File PDF '{pdf_path}' bị hỏng hoặc trống.")
        return
    except Exception as e:
        print(f"❌ Lỗi khi mở file PDF: {str(e)}")
        return

    total_pages = len(pdf_document)
    pages_to_read = min(num_pages, total_pages)

    print(f"📄 Tổng số trang: {total_pages}")
    print(f"📖 Đọc {pages_to_read} trang đầu tiên")
    print(f"📁 Hình ảnh sẽ được lưu vào: {output_folder}\n")
    print("=" * 80)

    for page_num in range(pages_to_read):
        page = pdf_document[page_num]

        print(f"\n📃 TRANG {page_num + 1}")
        print("-" * 80)

        # Trích xuất văn bản
        text = page.get_text()
        print("\n📝 NỘI DUNG VĂN BẢN:")
        print(text if text.strip() else "(Không có văn bản)")

        # Trích xuất hình ảnh
        image_list = page.get_images(full=True)

        if image_list:
            print(f"\n🖼️  SỐ LƯỢNG HÌNH ẢNH: {len(image_list)}")

            for img_index, img in enumerate(image_list):
                xref = img[0]  # XREF của hình ảnh

                try:
                    base_image = pdf_document.extract_image(xref)
                except Exception as e:
                    print(
                        f"  ├─ Lỗi khi trích xuất hình {img_index + 1} (xref={xref}): {e}"
                    )
                    continue

                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # Tạo tên file và đường dẫn đầy đủ
                base_filename = f"page_{page_num + 1}_image_{img_index + 1}.{image_ext}"
                image_filename = os.path.join(output_folder, base_filename)

                # Lưu hình ảnh vào thư mục
                try:
                    with open(image_filename, "wb") as image_file:
                        image_file.write(image_bytes)
                except OSError as e:
                    print(f"  ├─ Lỗi khi lưu file {image_filename}: {e}")
                    continue

                try:
                    # Lấy kích thước hình ảnh
                    img_obj = Image.open(io.BytesIO(image_bytes))
                    width, height = img_obj.size

                    print(f"  ├─ Hình {img_index + 1}: Đã lưu tại '{image_filename}'")
                    print(f"  │  Kích thước: {width}x{height} px")
                    print(f"  │  Định dạng: {image_ext.upper()}")

                    # Đã xóa lệnh img_obj.show()

                except Image.UnidentifiedImageError:
                    print(
                        f"  ├─ Hình {img_index + 1} (xref={xref}): Đã lưu file '{image_filename}' nhưng không thể đọc (định dạng không được PIL hỗ trợ)."
                    )
                except Exception as e:
                    print(f"  ├─ Hình {img_index + 1}: Lỗi khi xử lý bằng PIL: {e}")

        else:
            print("\n🖼️  HÌNH ẢNH: Không có")

        print("\n" + "=" * 80)

    pdf_document.close()
    print(f"\n✅ Hoàn thành! Đã đọc {pages_to_read} trang.")


# Sử dụng hàm
if __name__ == "__main__":
    # Thay đổi đường dẫn file PDF của bạn ở đây
    pdf_file = r"C:\Users\ha.phan\Downloads\273963059_Bộ 600 câu hỏi dùng cho sát hạch lái xe cơ giới đường bộ.pdf"

    # Đặt tên thư mục bạn muốn lưu ảnh
    output_directory = "images_from_pdf"

    try:
        read_pdf_with_images(pdf_file, output_folder=output_directory, num_pages=30)
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {pdf_file}")
        print("Vui lòng kiểm tra đường dẫn file!")
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
