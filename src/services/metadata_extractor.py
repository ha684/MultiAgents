# src/utils/metadata_extractor.py
import langextract as lx
import textwrap
import re
from typing import Dict, Any, List, Optional
from langchain_core.documents import Document
from langextract.factory import ModelConfig
from src.config import settings
from qdrant_client import models
from collections import defaultdict
from rapidfuzz import process, fuzz

METADATA_PROMPT = textwrap.dedent("""\
    Extract key metadata from the document chunk or text. Focus on identifying:
    
    - document_type: Infer the type/category of document based on content and structure
    - document_title: Main title or heading of the document (preserve original language)
    - main_topics: Key subject areas or themes discussed (preserve original key terms)
    - entities: Important names, organizations, products, or systems mentioned (preserve original language)
    - identifiers: Any codes, IDs, reference numbers, or version numbers found (preserve original format)
    - tools_technologies: Software, platforms, or technical tools mentioned (preserve original names)
    - summary: Brief 1-2 sentence summary of the main content
    - key_concepts: Important domain-specific concepts and terminology (preserve original language)
    - organizational_units: Teams, departments, or business units mentioned (preserve original names)
    
    IMPORTANT: Always preserve the original language and exact spelling of all key terms, 
    names, identifiers, and technical terminology. Do not translate or modify these terms.
    
    Extract exact text where possible. If information is not clearly present, omit that field.
    Focus on content useful for document discovery and relationship mapping.
    """)

METADATA_EXAMPLES = [
    lx.data.ExampleData(
        text="""
        Q2 2024 Marketing Campaign Performance Analysis
        
        Executive Summary:
        This report analyzes the performance of our digital marketing campaigns across Q2 2024.
        The Marketing Analytics team collaborated with the Sales Operations department to evaluate 
        ROI across Facebook Ads, Google AdWords, and LinkedIn campaigns.
        
        Key findings:
        - Campaign ROI improved by 23% compared to Q1
        - LinkedIn generated highest quality leads for B2B segment
        - Budget reallocation recommended for Q3
        
        Tools used: Google Analytics, Facebook Business Manager, Salesforce CRM
        Next steps: Present findings to CMO by July 15, 2024
        """,
        extractions=[
            lx.data.Extraction(
                extraction_class="document_type",
                extraction_text="Performance Analysis Report",
            ),
            lx.data.Extraction(
                extraction_class="document_title",
                extraction_text="Q2 2024 Marketing Campaign Performance Analysis",
            ),
            lx.data.Extraction(
                extraction_class="main_topics",
                extraction_text="digital marketing performance",
            ),
            lx.data.Extraction(
                extraction_class="main_topics", extraction_text="campaign ROI analysis"
            ),
            lx.data.Extraction(
                extraction_class="main_topics", extraction_text="lead generation"
            ),
            lx.data.Extraction(
                extraction_class="entities", extraction_text="Facebook Ads"
            ),
            lx.data.Extraction(
                extraction_class="entities", extraction_text="Google AdWords"
            ),
            lx.data.Extraction(extraction_class="entities", extraction_text="LinkedIn"),
            lx.data.Extraction(
                extraction_class="identifiers", extraction_text="Q2 2024"
            ),
            lx.data.Extraction(extraction_class="identifiers", extraction_text="Q1"),
            lx.data.Extraction(extraction_class="identifiers", extraction_text="Q3"),
            lx.data.Extraction(
                extraction_class="tools_technologies",
                extraction_text="Google Analytics",
            ),
            lx.data.Extraction(
                extraction_class="tools_technologies",
                extraction_text="Facebook Business Manager",
            ),
            lx.data.Extraction(
                extraction_class="tools_technologies", extraction_text="Salesforce CRM"
            ),
            lx.data.Extraction(
                extraction_class="summary",
                extraction_text="Analysis of Q2 2024 digital marketing campaign performance showing 23% ROI improvement with recommendations for Q3 budget reallocation",
            ),
            lx.data.Extraction(
                extraction_class="key_concepts", extraction_text="campaign ROI"
            ),
            lx.data.Extraction(
                extraction_class="key_concepts", extraction_text="lead quality"
            ),
            lx.data.Extraction(
                extraction_class="key_concepts", extraction_text="B2B segment"
            ),
            lx.data.Extraction(
                extraction_class="organizational_units",
                extraction_text="Marketing Analytics team",
            ),
            lx.data.Extraction(
                extraction_class="organizational_units",
                extraction_text="Sales Operations department",
            ),
        ],
    )
]


def extract_mentioned_files(text: str) -> List[str]:
    """Extracts filenames using regex."""
    pattern = r"[^\s\"'<>|*?:]+\.(docx|pdf|xlsx|xls|sql|pptx|drawio|png|jpg|jpeg|txt|md|py|js|ts|html|css|json|xml|yaml|yml)\b"
    files = list(set(re.findall(pattern, text, re.IGNORECASE)))
    return [f for f in files if len(f) > 3]


def extract_project_ids_regex(text: str) -> List[str]:
    """Extract project IDs using regex patterns."""
    patterns = [
        r"\b(PROJ-\d+)\b",
        r"\b(PRJ-\d+)\b",
        r"\b(PROJECT-\d+)\b",
        r"\b([A-Z]{2,4}-\d{3,5})\b",
    ]

    project_ids = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        project_ids.extend(matches)

    return list(set(project_ids))


def _select_representative_chunks(
    docs: List[Document],
    num_middle_chunks: int = 10,
    num_start_chunks: int = 3,
    num_end_chunks: int = 3,
) -> List[Document]:
    """
    Selects a representative subset of chunks from a list of documents.
    """
    if not docs:
        return []

    total_needed = num_start_chunks + num_end_chunks + num_middle_chunks
    if len(docs) <= total_needed:
        seen_hashes = set()
        unique_docs = []
        for doc in docs:
            doc_hash = hash(doc.page_content)
            if doc_hash not in seen_hashes:
                seen_hashes.add(doc_hash)
                unique_docs.append(doc)
        return unique_docs

    start_chunks = docs[:num_start_chunks]
    end_chunks = docs[-num_end_chunks:]

    middle_chunks = []
    middle_section_start_index = num_start_chunks
    middle_section_end_index = len(docs) - num_end_chunks
    middle_section = docs[middle_section_start_index:middle_section_end_index]

    if num_middle_chunks > 0 and len(middle_section) > 0:
        if len(middle_section) <= num_middle_chunks:
            middle_chunks = middle_section
        else:
            step = len(middle_section) / num_middle_chunks
            indices = [int(i * step) for i in range(num_middle_chunks)]
            middle_chunks = [middle_section[i] for i in indices]

    combined_chunks = start_chunks + middle_chunks + end_chunks

    seen_hashes = set()
    selected_docs = []

    for doc in combined_chunks:
        doc_hash = hash(doc.page_content)
        if doc_hash not in seen_hashes:
            seen_hashes.add(doc_hash)
            selected_docs.append(doc)

    return selected_docs


def extract_metadata_from_text_or_document(
    texts_or_docs: str | List[str] | Document | list[Document],
) -> dict:
    """
    Extracts structured metadata from a given text or Langchain Document using LLM and regex.
    """
    if isinstance(texts_or_docs, Document):
        full_text = texts_or_docs.page_content
    elif isinstance(texts_or_docs, list) and all(
        isinstance(doc, Document) for doc in texts_or_docs
    ):
        texts_or_docs = _select_representative_chunks(texts_or_docs)
        full_text = "\n".join([doc.page_content for doc in texts_or_docs])
    elif isinstance(texts_or_docs, list) and all(
        isinstance(doc, str) for doc in texts_or_docs
    ):
        full_text = "\n".join(texts_or_docs)
    elif isinstance(texts_or_docs, str):
        full_text = texts_or_docs
    else:
        raise ValueError("Invalid input type")

    llm_result = lx.extract(
        text_or_documents=full_text,
        prompt_description=METADATA_PROMPT,
        examples=METADATA_EXAMPLES,
        config=ModelConfig(
            model_id="nxchat",
            provider="openai",
            provider_kwargs={
                "base_url": settings.ntqai_base_url,
                "api_key": settings.ntqai_api_key,
            },
        ),
        debug=False,
        extraction_passes=1,
        max_workers=20,
        max_char_buffer=1000,
        batch_length=20,
    )

    extracted_data = {}
    for extraction in llm_result.extractions:
        if extraction.extraction_class in extracted_data:
            if isinstance(extracted_data[extraction.extraction_class], list):
                extracted_data[extraction.extraction_class].append(
                    extraction.extraction_text
                )
            else:
                extracted_data[extraction.extraction_class] = [
                    extracted_data[extraction.extraction_class],
                    extraction.extraction_text,
                ]
        else:
            extracted_data[extraction.extraction_class] = extraction.extraction_text

    mentioned_files = extract_mentioned_files(full_text)
    if mentioned_files:
        extracted_data["mentioned_files"] = mentioned_files

    metadata = _aggregate_document_metadata(extracted_data)
    return metadata


def _aggregate_document_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and limit metadata fields dynamically based on what was extracted"""
    processed_metadata = {}
    for field_name, field_data in metadata.items():
        if isinstance(field_data, list):
            if field_name == "summary" and field_data:
                processed_metadata[field_name] = ". ".join(set(field_data))
            elif field_name == "document_title" and field_data:
                titles_by_freq = defaultdict(int)
                for title in field_data:
                    titles_by_freq[title.strip()] += 1
                sorted_titles = sorted(
                    titles_by_freq.items(), key=lambda x: (-x[1], -len(x[0]))
                )
                if sorted_titles:
                    processed_metadata[field_name] = sorted_titles[0][0]
            else:
                processed_metadata[field_name] = _fuzzy_deduplicate_and_limit(
                    field_data
                )
        else:
            processed_metadata[field_name] = field_data

    return processed_metadata


def _fuzzy_deduplicate_and_limit(
    items: List[str], similarity_threshold: int = 80
) -> List[str]:
    """
    Deduplicates a list of strings using fuzzy matching, prioritizes more frequent items,
    and limits the result.
    """
    if not items:
        return []

    counts = defaultdict(int)
    for item in items:
        if item and str(item).strip():
            counts[str(item).strip()] += 1

    if not counts:
        return []

    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    final_results = []
    for item, _ in sorted_items:
        is_similar = False
        for existing_item in final_results:
            if fuzz.token_set_ratio(item, existing_item) > similarity_threshold:
                is_similar = True
                break

        if not is_similar:
            final_results.append(item)

    return final_results


def build_metadata_filters(source_metadata: Dict[str, Any]) -> models.Filter:
    """Build Qdrant filters based on source document metadata"""
    should_conditions = []
    ignored_fields = [
        "chunk_index",
        "images",
        "filename",
        "kb_id",
        "document_id",
        "original_filename",
        "sheet_name",
        "_id",
        "_collection_name",
    ]

    for field_name, field_value in source_metadata.items():
        if field_name in ignored_fields:
            continue

        if isinstance(field_value, list) and field_value:
            should_conditions.append(
                models.FieldCondition(
                    key=f"metadata.{field_name}", match=models.MatchAny(any=field_value)
                )
            )
        elif field_value and not isinstance(field_value, (dict, list)):
            should_conditions.append(
                models.FieldCondition(
                    key=f"metadata.{field_name}",
                    match=models.MatchValue(value=field_value),
                )
            )

    return models.Filter(should=should_conditions) if should_conditions else None


def build_search_query_from_metadata(source_metadata: Dict[str, Any]) -> str:
    """
    Build a rich semantic search query from document metadata
    """
    query_parts = []

    priority_fields = ["summary", "document_title", "title", "name"]
    for field in priority_fields:
        value = source_metadata.get(field)
        if value and isinstance(value, str):
            query_parts.append(value.strip("."))
            break

    all_keywords = []
    list_field_keywords = [
        "concept",
        "topic",
        "keyword",
        "tag",
        "subject",
        "theme",
        "entities",
        "technologies",
    ]

    for field_name, field_value in source_metadata.items():
        if isinstance(field_value, list) and any(
            kw in field_name.lower() for kw in list_field_keywords
        ):
            all_keywords.extend(str(item) for item in field_value if item)

    if all_keywords:
        query_parts.append(" ".join(all_keywords))

    query = " ".join(query_parts)
    if len(query) > 200:
        query = query[:200].rsplit(" ", 1)[0]
    return query


def aggregate_related_documents_with_reasons(
    related_chunks: List[Document],
    source_metadata: Dict[str, Any],
    source_doc_id: str,
    score_threshold: float,
) -> List[Dict]:
    """Aggregate chunks by document and determine relatedness reasons"""

    document_data = defaultdict(
        lambda: {"scores": [], "reasons": set(), "chunk_count": 0}
    )

    for chunk in related_chunks:
        doc_id = chunk.metadata.get("document_id")
        vector_score = chunk.metadata.get("vector_score", 0.0)

        if doc_id == source_doc_id or vector_score < score_threshold:
            continue

        document_data[doc_id]["scores"].append(vector_score)
        document_data[doc_id]["chunk_count"] += 1

        reasons = _determine_fuzzy_relatedness_reasons(chunk.metadata, source_metadata)
        document_data[doc_id]["reasons"].update(reasons)

    results = []
    for doc_id, data in document_data.items():
        if not data["scores"]:
            continue
        avg_score = sum(data["scores"]) / len(data["scores"])
        results.append(
            {
                "document_id": doc_id,
                "score": avg_score,
                "total_matching_chunks": data["chunk_count"],
                "relatedness_reasons": list(data["reasons"]),
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _find_fuzzy_common_items(
    list1: List[str], list2: List[str], threshold: int = 80
) -> List[str]:
    """Finds common items between two lists using fuzzy matching."""
    common = []
    temp_list2 = list(list2)

    for item1 in list1:
        result = process.extractOne(
            query=item1,
            choices=temp_list2,
            scorer=fuzz.token_set_ratio,
            score_cutoff=threshold,
        )

        if result:
            best_match = result[0]
            common.append(item1)
            temp_list2.remove(best_match)

    return common


def _determine_fuzzy_relatedness_reasons(
    target_metadata: Dict[str, Any],
    source_metadata: Dict[str, Any],
    similarity_threshold: int = 80,
) -> List[str]:
    """Determine why two documents are related using fuzzy matching."""
    reasons = set()
    ignored_fields = [
        "chunk_index",
        "images",
        "filename",
        "kb_id",
        "document_id",
        "original_filename",
        "sheet_name",
        "_id",
        "_collection_name",
    ]

    for field_name, source_value in source_metadata.items():
        if field_name in ignored_fields:
            continue

        target_value = target_metadata.get(field_name)
        if not target_value:
            continue

        display_name = field_name.replace("_", " ").title()

        if isinstance(source_value, list) and isinstance(target_value, list):
            source_list = [str(item) for item in source_value if item]
            target_list = [str(item) for item in target_value if item]

            common_items = _find_fuzzy_common_items(
                source_list, target_list, threshold=similarity_threshold
            )

            if common_items:
                items_str = ", ".join(list(set(common_items))[:3])
                reasons.add(f"{display_name}: {items_str}")

        elif isinstance(source_value, str) and isinstance(target_value, str):
            if (
                fuzz.ratio(source_value, target_value) > similarity_threshold
                and len(source_value) > 3
            ):
                reasons.add(f"{display_name}: {source_value}")

    if not reasons:
        return ["Content similarity"]

    return list(reasons)


def combine_filters(
    existing_filters: Optional[models.Filter], metadata_filters: Optional[models.Filter]
) -> Optional[models.Filter]:
    """Combine existing filters with metadata-based filters"""

    if not existing_filters and not metadata_filters:
        return None

    if not existing_filters:
        return metadata_filters

    if not metadata_filters:
        return existing_filters

    combined_must = []
    combined_should = []
    combined_must_not = []

    if existing_filters.must:
        combined_must.extend(
            existing_filters.must
            if isinstance(existing_filters.must, list)
            else [existing_filters.must]
        )
    if existing_filters.should:
        combined_should.extend(
            existing_filters.should
            if isinstance(existing_filters.should, list)
            else [existing_filters.should]
        )
    if existing_filters.must_not:
        combined_must_not.extend(
            existing_filters.must_not
            if isinstance(existing_filters.must_not, list)
            else [existing_filters.must_not]
        )

    if metadata_filters.should:
        combined_should.extend(
            metadata_filters.should
            if isinstance(metadata_filters.should, list)
            else [metadata_filters.should]
        )

    return models.Filter(
        must=combined_must if combined_must else None,
        should=combined_should if combined_should else None,
        must_not=combined_must_not if combined_must_not else None,
    )
