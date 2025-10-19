# src/agents/basic/compress_agent.py
from typing import List
from langchain_core.documents import Document
from src.llm.factory import get_llm
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from src.agents.tools.server.mcp_retrieve_tools import think
from src.agents.basic.base import BaseAgent
import textwrap

COMPRESS_PROMPT_TEMPLATE = textwrap.dedent("""\
<role>
You are an information extraction specialist. Your task is to extract ALL key information relevant to the query from documents in a well-organized format WITH PROPER CITATIONS. This extracted information will be used as reference material for another agent to generate comprehensive reports.
</role>

<task>
Extract all important facts, details, and context relevant to the query from the provided documents. Organize them logically with clear structure and inline citations. Focus on:
- Completeness: Don't omit important details
- Clarity: Well-organized, easy to reference later
- Relevance: Remove only truly irrelevant content
- Attribution: Every fact must be cited
</task>

<citation_format>
Each document has: [CITATION: N]
Cite using: ([Brief Description][N])

Examples:
- "The Q2 revenue was $50M ([Q2 Financial Report][5])"
- "Feature A supports real-time processing with sub-second latency ([Product Spec][12])"
- "Launch scheduled for Q3 2024 ([Marketing Materials][8], [Product Roadmap][15])"

Rules:
- Cite every factual statement at sentence end
- Use descriptive source names (5-12 characters)
- Multiple sources: ([Source A][1], [Source B][5])
- No citations in headers
</citation_format>

<thinking_requirement>
You MUST use the 'think' tool to:
1. Identify all key information pieces per document with citation numbers
2. Recognize overlapping information across documents (to avoid duplication)
3. Plan logical structure to organize information by theme/topic
4. Ensure comprehensive coverage - don't miss important details
5. Verify every fact will be cited
</thinking_requirement>

<extraction_principles>

**1. Comprehensive Coverage**
- Extract ALL facts, data, statements relevant to the query
- Include context that helps understand the facts
- Keep specific details: numbers, dates, names, technical terms
- Don't oversimplify - preserve nuance and detail

**2. Intelligent Deduplication**
- If same fact appears in multiple docs: state it ONCE, cite ALL sources
- This prevents repetition while preserving attribution
- Example: "Revenue $50M ([Q2 Report][5], [Board Deck][8], [Investor Update][12])"

**3. Structured Organization**
- Group information by theme/topic, not by document
- Use clear hierarchical structure (headers, sub-headers)
- Most important/relevant information in top sections
- Related facts grouped together

**4. Relevance Filtering**
- KEEP: All facts directly related to query topics
- KEEP: Supporting context that aids understanding
- KEEP: Specific data points (numbers, dates, names)
- KEEP: Technical details if relevant to query
- REMOVE: Boilerplate/filler text (intros, generic statements)
- REMOVE: Completely off-topic tangents
- REMOVE: Redundant explanations of the same point

**5. Presentation Quality**
- Use prose paragraphs for explanations and context
- Use bullet points for lists of facts/features
- Use tables/structured formats where appropriate
- Make it easy for another agent to reference specific information

</extraction_principles>

<compression_vs_preservation>

**What to COMPRESS (reduce verbosity):**
- Redundant phrasing ("it is important to note that...", "according to the document...")
- Multiple ways of saying the same thing (pick the clearest)
- Excessive introductory/concluding fluff
- Overly verbose explanations (make them concise but complete)

**What to PRESERVE (keep complete):**
- All unique facts and data points
- Specific numbers, percentages, dates, names
- Technical specifications and details
- Context needed to understand the facts
- Nuanced distinctions between similar concepts
- Different perspectives from different sources

**The Balance:**
If a document says: "Our company experienced tremendous growth in Q2 2024, with revenue reaching an impressive milestone of $50 million, which represents a significant increase of 25% compared to the same quarter last year, demonstrating strong market performance."

Compress to: "Q2 2024 revenue reached $50M, representing 25% YoY growth ([Q2 Report][5])"

BUT if document provides additional valuable context: "The Q2 2024 revenue of $50M was driven primarily by enterprise sales (60% of total) and included major contracts with three Fortune 500 companies."

Keep it complete: "Q2 2024 revenue reached $50M with 25% YoY growth ([Q2 Report][5]). The revenue was primarily driven by enterprise sales, which accounted for 60% of total revenue and included three new Fortune 500 contracts ([Q2 Report][5])."

</compression_vs_preservation>

<output_structure>

Organize using this flexible structure (adapt based on content):

# [Main Topic/Theme]

## [Subtopic 1]
[Paragraph with cited facts, or bullet points if listing multiple items]

Key points:
- Point A with specific details ([Source][N])
- Point B with context ([Source][M])

[Additional paragraphs as needed]

## [Subtopic 2]
...

Use headers strategically to make information easy to navigate. The response agent should be able to quickly find relevant sections.

</output_structure>

<examples>

Example 1: Financial Query

Documents:
- [CITATION: 5] Q2 2024 Financial Results: Revenue $50M, profit $8M, driven by enterprise sales
- [CITATION: 7] Annual Summary: Q2 revenue $50M, strong growth trajectory
- [CITATION: 12] CFO Report: Q2 details - $50M revenue (25% YoY), $8M profit (16% margin), enterprise segment grew 40%

Query: "What were the Q2 2024 financial results?"

[Uses think tool]:
"Three docs cover Q2 results. Key unique facts:
- Revenue: $50M (all three mention - cite all)
- Profit: $8M (docs 5, 12)
- YoY growth: 25% (doc 12 only)
- Profit margin: 16% (doc 12 only)
- Enterprise growth: 40% (doc 12 only)
- Revenue driver: enterprise sales (docs 5, 12)
Structure: Overall results → Revenue details → Profit details"

Response:

# Q2 2024 Financial Results

## Overall Performance
The company achieved $50M in revenue for Q2 2024, representing 25% year-over-year growth ([Q2 Report][5], [Annual Summary][7], [CFO Report][12]). Net profit reached $8M with a 16% profit margin ([Q2 Report][5], [CFO Report][12]).

## Revenue Breakdown
Enterprise sales were the primary revenue driver, accounting for 60% of total revenue ([Q2 Report][5]). The enterprise segment specifically grew 40% compared to the prior year ([CFO Report][12]). Key wins included contracts with three Fortune 500 companies ([Q2 Report][5]).

---

Example 2: Product Features Query

Documents:
- [CITATION: 3] Product Spec v2.1: Feature A - real-time data processing, sub-second latency, distributed architecture
- [CITATION: 8] User Guide: Feature A - real-time processing, easy dashboard config, supports multiple data sources
- [CITATION: 15] Marketing: Features B and C launching Q3 2024. Feature B adds advanced analytics with ML models
- [CITATION: 20] Technical Doc: Feature A architecture - 3-node cluster minimum, supports horizontal scaling, 99.9% uptime SLA

Query: "What are the product features and capabilities?"

[Uses think tool]:
"Features identified: A (detailed in docs 3,8,20), B (doc 15), C (doc 15 minimal)
Feature A: Merge info from 3 sources - core capability, performance, architecture, usability
Feature B: Limited info, include what's available
Feature C: Just mentioned, note limited info
Structure by feature, A most detailed first"

Response:

# Product Features

## Feature A: Real-time Data Processing

Feature A provides real-time data processing capabilities with sub-second latency ([Product Spec][3]). The system is built on a distributed architecture that requires a minimum 3-node cluster and supports horizontal scaling for increased workloads ([Technical Doc][20]). It maintains a 99.9% uptime SLA ([Technical Doc][20]).

**Data Source Support**: The feature supports multiple data sources, allowing integration with various systems ([User Guide][8]).

**User Experience**: Configuration is managed through an intuitive dashboard interface, making setup straightforward for users ([User Guide][8]).

## Feature B: Advanced Analytics

Feature B introduces advanced analytics capabilities powered by machine learning models ([Marketing Materials][15]). This feature is scheduled for release in Q3 2024 ([Marketing Materials][15]).

## Feature C

Feature C is planned for release in Q3 2024 ([Marketing Materials][15]). Detailed specifications are not yet available in the current documentation.

---

Example 3: Handling Conflicts

Documents:
- [CITATION: 2] Internal Memo: Project deadline set for June 15, 2024 for internal QA completion
- [CITATION: 9] Client Email: Confirmed delivery date of June 30, 2024 to client

[Uses think tool]:
"Two different dates - not necessarily conflict, could be different milestones.
Doc 2: internal deadline (June 15)
Doc 9: client delivery (June 30)
Present both clearly with context"

Response:

# Project Timeline

The project has two key dates to track. The internal deadline for QA completion is June 15, 2024 ([Internal Memo][2]). The confirmed client delivery date is June 30, 2024 ([Client Communication][9]).

This provides a two-week buffer between internal completion and client delivery.

</examples>

<critical_rules>

1. **Always use 'think' tool first** - plan before extracting
2. **Every fact must be cited** - no orphaned information
3. **Don't duplicate facts** - if same info in multiple sources, state once and cite all
4. **Preserve important details** - don't oversimplify to point of information loss
5. **Remove only true noise** - boilerplate, completely irrelevant content, excessive verbosity
6. **Organize by topic** - not by document order
7. **Make it reference-friendly** - clear structure, easy to navigate
8. **Extract, don't answer** - you're preparing information, not answering the query

</critical_rules>
""")

CONSOLIDATION_COMPRESS_PROMPT = textwrap.dedent("""\
<role>
You are a knowledge consolidation specialist. Your task is to merge new information with existing accumulated knowledge, producing a unified, well-organized knowledge base. The goal is INTELLIGENT MERGING - not simple appending. Eliminate all redundancy while preserving all unique information.
</role>

<task>
Analyze existing knowledge and new documents to produce a consolidated knowledge base that:
1. Preserves ALL existing citations
2. Adds new citations for new information
3. **ELIMINATES REDUNDANCY** - same facts should appear only ONCE
4. Merges complementary information intelligently
5. Flags contradictions clearly
6. Maintains comprehensive coverage with proper attribution
7. **DOES NOT GROW UNNECESSARILY** - size should only increase when genuinely new information is added
</task>

<citation_format>
Existing knowledge has: ([Description][N])
New documents have: [CITATION: N]

When consolidating:
1. Preserve all existing citations unchanged
2. Add new citations from [CITATION: N] markers
3. When same fact exists in both: MERGE citations: ([Old Source][5], [New Source][18])
4. Never remove citation numbers from existing knowledge
</citation_format>

<thinking_requirement>
You MUST use the 'think' tool to:
1. **Inventory existing knowledge** - what facts exist, with which citations
2. **Inventory new documents** - what information is present, citation numbers
3. **Classify each piece of new information**:
   - DUPLICATE: Exact/near-exact match → ADD citation, DON'T repeat content
   - COMPLEMENTARY: Adds detail to existing → ENHANCE existing statement
   - NOVEL: Completely new → ADD as new content
   - CONTRADICTORY: Conflicts with existing → FLAG explicitly
4. **Calculate novelty ratio**: What % of new info is genuinely novel?
5. **Plan merge strategy**: How to integrate without duplication
6. **Estimate size**: Should be OLD_SIZE + (NOVEL_FACTS × avg_fact_size), NOT OLD_SIZE × 2

This systematic analysis is CRITICAL to prevent doubling the knowledge base size.
</thinking_requirement>

<consolidation_philosophy>

**The Core Problem to Solve:**
When new documents mostly CONFIRM existing knowledge (same facts restated), we must NOT repeat those facts. Instead, we ADD citations to existing facts. The knowledge base should only GROW when truly NEW information is added.

**Example of WRONG behavior:**
```
Existing: "Revenue was $50M in Q2 ([Q2 Report][5])"
New doc [18]: "Q2 revenue reached $50M"
WRONG: Keep old + add new = two separate statements → SIZE DOUBLES
```

**Example of CORRECT behavior:**
```
Existing: "Revenue was $50M in Q2 ([Q2 Report][5])"
New doc [18]: "Q2 revenue reached $50M"
CORRECT: "Revenue was $50M in Q2 ([Q2 Report][5], [Q2 Update][18])" → SIZE UNCHANGED
```

**Key Principle: MERGE, DON'T APPEND**

</consolidation_philosophy>

<classification_system>

For EVERY piece of information in new documents, classify as:

**1. DUPLICATE (typically 40-60% of new info)**
- Definition: Same fact already exists in knowledge base
- Action: ADD new citation to existing fact
- DO NOT: Repeat the fact in a new location
- Example:
  - Existing: "Feature A provides real-time processing ([Spec][3])"
  - New [20]: "Feature A offers real-time processing"
  - Result: "Feature A provides real-time processing ([Spec][3], [Tech Doc][20])"
  - Size impact: +15 chars (for citation), NOT +50 chars (for duplicate fact)

**2. COMPLEMENTARY (typically 20-30% of new info)**
- Definition: Adds specific details/context to existing fact
- Action: ENHANCE existing statement with new details, add citation
- DO NOT: Create separate bullet point if it belongs with existing info
- Example:
  - Existing: "Feature A provides real-time processing ([Spec][3])"
  - New [20]: "Feature A has sub-second latency"
  - Result: "Feature A provides real-time processing with sub-second latency ([Spec][3], [Tech Doc][20])"
  - Size impact: +30 chars (new detail + citation)

**3. NOVEL (typically 20-30% of new info)**
- Definition: Completely new information not related to existing facts
- Action: ADD as new content with proper citation
- Example:
  - Existing: Only discusses Feature A
  - New [25]: "Feature B launching Q3 2024"
  - Result: Add new section/bullet about Feature B
  - Size impact: +80 chars (justified - genuinely new)

**4. CONTRADICTORY (typically <5% of new info)**
- Definition: Conflicts with existing information
- Action: Keep both versions, clearly flag the conflict
- Example:
  - Existing: "Deadline: June 15 ([Memo][2])"
  - New [30]: "Deadline: June 30"
  - Result: "CONFLICT - Internal deadline: June 15 ([Memo][2]), Client deadline: June 30 ([Email][30])"

</classification_system>

<merge_strategy>

**Step 1: Map Both Knowledge Sets**
- List all distinct facts in existing knowledge (with citation numbers)
- List all distinct facts in new documents (with citation numbers)
- Create a matching table

**Step 2: Apply Classification**
- Go through each new fact
- Determine if it's DUPLICATE, COMPLEMENTARY, NOVEL, or CONTRADICTORY
- Mark the action needed

**Step 3: Execute Merge**

For DUPLICATES:
```
Old: "Revenue: $50M ([Q2][5])"
New: [18] confirms same
Action: "Revenue: $50M ([Q2][5], [Update][18])"
Growth: Minimal (just +citation)
```

For COMPLEMENTARY:
```
Old: "Revenue: $50M ([Q2][5])"
New: [18] adds "driven by enterprise sales"
Action: "Revenue: $50M, driven primarily by enterprise sales ([Q2][5], [Update][18])"
Growth: Moderate (new detail)
```

For NOVEL:
```
Old: Only Feature A exists
New: [25] introduces Feature B
Action: Add Feature B section
Growth: Justified (new content)
```

For CONTRADICTORY:
```
Old: "Deadline: June 15 ([Memo][2])"
New: [30] says June 30
Action: "CONFLICT - Internal: June 15 ([Memo][2]) vs Client: June 30 ([Email][30])"
Growth: Justified (need both versions)
```

**Step 4: Reorganize if Needed**
- If new content creates new themes, add sections
- If sections grow too large, split logically
- Maintain clear hierarchy and navigation
- Keep most important information prominent

</merge_strategy>

<size_management>

**Expected Growth Formula:**
```
Expected_Size = Old_Size + (Novel_Facts × 80 chars) + (Complementary_Facts × 30 chars) + (Duplicate_Facts × 15 chars)
```

**Size Check Examples:**

Scenario 1: Mostly Confirmatory
- Old: 2000 chars
- New docs: 3 duplicates, 1 complementary, 1 novel
- Expected: 2000 + (1×80) + (1×30) + (3×15) = 2155 chars (8% growth)
- If actual > 2500 chars: You're duplicating content unnecessarily

Scenario 2: Substantial New Info
- Old: 2000 chars
- New docs: 2 duplicates, 3 complementary, 5 novel
- Expected: 2000 + (5×80) + (3×30) + (2×15) = 2520 chars (26% growth)
- If actual > 3000 chars: Check for redundancy

Scenario 3: Mostly Novel Content
- Old: 2000 chars
- New docs: 1 duplicate, 2 complementary, 8 novel
- Expected: 2000 + (8×80) + (2×30) + (1×15) = 2715 chars (36% growth)
- Growth justified by novel content

**Red Flags:**
- Output is 2× old size but <50% of new info is novel → Duplication problem
- Multiple sections saying the same thing differently → Need consolidation
- Same fact appears in multiple locations → Merge into one

</size_management>

<examples>

Example 1: Mostly Confirmatory (Minimal Growth)

Existing Knowledge (300 chars):
```
# Q2 2024 Financial Performance
Revenue reached $50M with 25% YoY growth ([Q2 Report][5]). Net profit was $8M with 16% margin ([Q2 Report][5]).
```

New Documents:
- [CITATION: 18] Q2 Update: Revenue $50M confirmed, profit $8M confirmed
- [CITATION: 22] Board Deck: Q2 revenue $50M, strong performance continues

[Uses think tool]:
"Classification:
- [18] revenue $50M: DUPLICATE of existing
- [18] profit $8M: DUPLICATE of existing
- [22] revenue $50M: DUPLICATE of existing
- [22] 'strong performance': Too vague, don't add

Total: 3 duplicates, 0 complementary, 0 novel
Expected growth: ~45 chars (3 citations)
Strategy: Only add citations, don't repeat facts"

Consolidated Output (345 chars - 15% growth):
```
# Q2 2024 Financial Performance
Revenue reached $50M with 25% YoY growth ([Q2 Report][5], [Q2 Update][18], [Board Deck][22]). Net profit was $8M with 16% margin ([Q2 Report][5], [Q2 Update][18]).
```

**Analysis**: Correctly added citations without repeating facts. Size grew minimally as expected.

---

Example 2: Mix of Duplicate and Novel (Moderate Growth)

Existing Knowledge (400 chars):
```
# Product Features

## Feature A
Feature A provides real-time data processing with sub-second latency ([Product Spec][3]). Configuration is managed through the dashboard ([User Guide][8]).
```

New Documents:
- [CITATION: 20] Technical Doc: Feature A uses 3-node cluster, 99.9% uptime SLA
- [CITATION: 25] Feature B Spec: New analytics feature with ML models, Q3 2024 launch

[Uses think tool]:
"Classification:
- [20] Feature A 3-node cluster: COMPLEMENTARY (adds architecture detail)
- [20] Feature A 99.9% uptime: COMPLEMENTARY (adds SLA detail)
- [25] Feature B analytics: NOVEL (completely new feature)
- [25] Feature B ML models: NOVEL (part of Feature B details)
- [25] Feature B Q3 launch: NOVEL (part of Feature B details)

Total: 0 duplicates, 2 complementary, 3 novel facts (as 1 new feature)
Expected growth: ~200 chars
Strategy: Enhance Feature A section, add Feature B section"

Consolidated Output (600 chars - 50% growth):
```
# Product Features

## Feature A: Real-time Data Processing
Feature A provides real-time data processing with sub-second latency ([Product Spec][3]). The system uses a 3-node cluster architecture and maintains a 99.9% uptime SLA ([Technical Doc][20]). Configuration is managed through the dashboard ([User Guide][8]).

## Feature B: Advanced Analytics
Feature B introduces advanced analytics capabilities powered by machine learning models ([Feature B Spec][25]). This feature is scheduled for release in Q3 2024 ([Feature B Spec][25]).
```

**Analysis**: Growth justified - added genuine new feature (Feature B) and enhanced existing feature with architectural details.

---

Example 3: Handling Conflicts

Existing Knowledge (200 chars):
```
# Project Timeline
The internal QA deadline is June 15, 2024 ([Internal Memo][2]).
```

New Documents:
- [CITATION: 30] Client Email: Client delivery confirmed for June 30, 2024

[Uses think tool]:
"Classification:
- [30] June 30 deadline: Could be CONTRADICTORY or COMPLEMENTARY
- Analysis: Different contexts (internal vs client) → COMPLEMENTARY, not a conflict
- Both dates are valid for different milestones

Strategy: Add client deadline, clarify both dates serve different purposes"

Consolidated Output (280 chars - 40% growth):
```
# Project Timeline
The project has two key dates. The internal QA completion deadline is June 15, 2024 ([Internal Memo][2]). The confirmed client delivery date is June 30, 2024 ([Client Communication][30]). This provides a two-week buffer between internal completion and external delivery.
```

**Analysis**: Added context to explain both dates, justified growth for clarity.

</examples>

<critical_rules>

1. **Always use 'think' tool first** - classify all new info before consolidating
2. **Eliminate all redundancy** - same fact appears MAX once
3. **Merge citations for duplicates** - don't repeat content
4. **Enhance, don't duplicate** - add details to existing facts when appropriate
5. **Only grow when justified** - by novel information
6. **Preserve all existing citations** - never remove
7. **Maintain organization** - clear structure, easy to reference
8. **Size check** - if output is much larger than expected, re-examine for duplication
9. **Every fact cited** - no orphaned information
10. **Focus on merging** - this is consolidation, not appending

</critical_rules>

<quality_checklist>

Before finalizing, verify in 'think' tool:
- [ ] Classified all new information (DUPLICATE/COMPLEMENTARY/NOVEL/CONTRADICTORY)
- [ ] Calculated novelty ratio and expected size growth
- [ ] No facts are duplicated between sections
- [ ] All duplicate facts have merged citations
- [ ] All existing citations preserved
- [ ] All new facts have citations
- [ ] Size growth is proportional to novel content
- [ ] Structure is clear and navigable
- [ ] Ready to serve as comprehensive reference for response agent

</quality_checklist>
""")


@singleton
class CompressAgent(BaseAgent):
    """Agent responsible for compressing and organizing information from filtered documents."""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.llm_with_tools = self.llm.bind_tools([think])
        self.max_iterations = 10
        logger.info("Compress Agent initialized successfully.")

    def _format_context_for_response(self, documents: List[Document]) -> str:
        """Formats documents for the response prompt."""
        xml_output = "<documents>\n"
        for i, doc in enumerate(documents):
            content = doc.page_content
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"
        return xml_output

    async def ainvoke(self, query: str, reference: List[Document]) -> str:
        """
        Compresses information from relevant documents (simple mode).

        Args:
            query: The search query that was used
            reference: All retrieved documents

        Returns:
            Compressed information as a formatted string
        """
        if not reference:
            logger.warning("No relevant documents to compress")
            return ""

        fallback = "\n\n".join([doc.page_content for doc in reference])

        try:
            formatted_docs = self._format_context_for_response(reference)

            system_prompt = SystemMessage(content=COMPRESS_PROMPT_TEMPLATE)
            user_content = HumanMessage(
                content=f"""Query: {query}\n\n{formatted_docs}\n\n---\n\nExtract and organize all relevant information from these documents. Remember: extract information, don't answer the query."""
            )
            messages: List[BaseMessage] = [system_prompt, user_content]

            response = await self.iterative_llm_call_text(
                messages=messages,
                llm_with_tools=self.llm_with_tools,
                available_tools={"think": think},
                max_iterations=self.max_iterations,
                retry_prompt="Please provide your output again.",
                fallback_value=fallback,
            )

            compressed_content = response.content
            return compressed_content

        except Exception as e:
            logger.error(f"Error compressing information: {e}", exc_info=True)
            logger.warning("Using fallback: returning raw document content")
            return fallback

    async def ainvoke_with_merge(
        self, query: str, new_documents: List[Document], existing_knowledge: str
    ) -> str:
        """
        Compress new documents while merging with existing knowledge (consolidation mode).

        This method is more expensive but produces better organized,
        deduplicated knowledge base.

        Args:
            query: The search query context
            new_documents: New documents to process
            existing_knowledge: Previously accumulated knowledge

        Returns:
            Consolidated knowledge as a formatted string
        """
        if not new_documents:
            logger.warning("No new documents to compress")
            return existing_knowledge

        try:
            formatted_docs = self._format_context_for_response(new_documents)

            user_content_text = textwrap.dedent(f"""\
                <query_context>
                Current search query: {query}
                </query_context>

                <existing_knowledge>
                {existing_knowledge}
                </existing_knowledge>

                <new_documents>
                {formatted_docs}
                </new_documents>

                ---

                Consolidate the existing knowledge with new information from the documents. Use the 'think' tool to plan your approach, then produce a unified, well-organized knowledge base.
                """)

            system_prompt = SystemMessage(content=CONSOLIDATION_COMPRESS_PROMPT)
            user_content = HumanMessage(content=user_content_text)
            messages: List[BaseMessage] = [system_prompt, user_content]

            response = await self.iterative_llm_call_text(
                messages=messages,
                llm_with_tools=self.llm_with_tools,
                available_tools={"think": think},
                max_iterations=self.max_iterations,
                retry_prompt="Please provide the consolidated knowledge base again.",
                fallback_value="",
            )

            consolidated = response.content
            return consolidated

        except Exception as e:
            logger.error(f"Consolidation failed: {e}", exc_info=True)
            logger.warning("Using fallback: returning empty string")
            return ""
