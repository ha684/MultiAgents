# import os

# from langchain_core.documents import Document
# from langchain_openai import ChatOpenAI
# from LLMGraphTransformer import LLMGraphTransformer
# from LLMGraphTransformer.schema import NodeSchema, RelationshipSchema

# additional_instructions = """
# You are a helpful assistant that can extract information from a text and convert it into a graph.
# """

# node_schemas = [
#     NodeSchema(
#         "Person",
#         ["name", "birth_year", "death_year", "nationalitie", "profession"],
#         "Represents an individual",
#     ),
#     NodeSchema(
#         "Organization",
#         ["name", "founding_year", "industrie"],
#         "Represents a group, company, or institution",
#     ),
#     NodeSchema(
#         "Location",
#         ["name"],
#         "Represents a geographical area such as a city, country, or region",
#     ),
#     NodeSchema(
#         "Award", ["name", "field"], "Represents an honor, prize, or recognition"
#     ),
# ]

# relationship_schemas = [
#     RelationshipSchema("Person", "SPOUSE_OF", "Person"),
#     RelationshipSchema(
#         "Person", "MEMBER_OF", "Organization", ["start_year", "end_year", "year"]
#     ),
#     RelationshipSchema("Person", "AWARDED", "Award", ["year"]),
#     RelationshipSchema("Person", "LOCATED_IN", "Location"),
#     RelationshipSchema("Organization", "LOCATED_IN", "Location"),
# ]

# llm = ChatOpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     base_url=os.getenv("OPENAI_BASE_URL"),
#     model=os.getenv("OPENAI_MODEL"),
#     temperature=0,
# )

# llm_transformer = LLMGraphTransformer(
#     llm=llm,
#     allowed_nodes=node_schemas,
#     allowed_relationships=relationship_schemas,
#     additional_instructions=additional_instructions,
# )

# text = """
# John Doe is a software engineer at Google. He was born in 1990 in San Francisco. He has a wife named Jane Doe and two children named Jim Doe and Jill Doe.
# """
# document = Document(page_content=text)
# graph_document = llm_transformer.convert_to_graph_document(document)
# # Kết nối DB
# graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="password")

# # Lưu một phát ăn ngay
# # add_graph_documents sẽ tự động sinh câu lệnh Cypher để INSERT dữ liệu
# graph.add_graph_documents([graph_document])
