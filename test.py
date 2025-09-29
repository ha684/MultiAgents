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
#       "conversation_id": "068d35e5-9423-716b-8000-5cd0aeb06bdc",
#       "kb_id": "068da9ca-5467-713d-8000-edc609d6fcfb",
#       "user_id": "123",
#       "app_name": "test"
#     }
#   },
#   "agentic": false,
#   "web_search": true
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
# loader = SpreadsheetStrategy({})
# docs = loader.chunk(r"C:\workspace\data\サンプル_QMSシステム開発_RD_エンティティ一覧.xlsx", db_document)

# for doc in docs:
#     print(doc.page_content)
#     print("-"*100)

from langchain_pymupdf4llm import PyMuPDF4LLMLoader

loader = PyMuPDF4LLMLoader(r"C:\workspace\data\2506.09250v1.pdf")
docs = loader.load()
for doc in docs:
    print(doc.page_content)
    print("-" * 100)
