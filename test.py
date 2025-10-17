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

from src.llm.factory import get_llm

llm = get_llm("nxchat")
messages = [
    {
        "role": "user",
        "content": "Bạn có biết cách tạo một JSON theo đặc tả của Vega-Lite để vẽ biểu đồ cột không?",
    }
]
response = llm.invoke(messages)
print(response)
