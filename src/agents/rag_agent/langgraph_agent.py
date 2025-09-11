from typing import List, Dict, Any, Optional, TypedDict, Annotated, cast, Union, AsyncGenerator
from pydantic import BaseModel
import tiktoken
from langchain_core.runnables import Runnable
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from qdrant_client.models import Filter, models
import json
from src.utils.decorators import singleton
from src.models.chat import ChatRequest
from src.llm.factory import get_llm
from src.rag.vector import vector_retrieval
from src.agents.citation_agent import CitationAgent
from src.agents.filename_agent import FilenameAgent
from src.agents.folder_categorization_agent import FolderCategorizationAgent
from src.agents.query_context_agent import QueryContextAgent
from src.agents.response_agent import ResponseAgent
from src.config.llm_config import LangGraphRAGConfig
from src.agents.rag_agent.prompts import (
    summary_prompt,
    verification_prompt,
    decision_prompt,
)
from src.models.agent import (
    SearchDecision,
    VerificationResult,
    ConversationSummary,
    NextAction,
    SearchType,
)
from src.utils.logger_conf import logger

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    original_query: str
    contextualized_query: str
    kb_id: str
    folder_context: Optional[str]
    folder_structure: Dict[str, Any]
    conversation_summary: Optional[str]
    summarized_history: Optional[str]
    search_history: List[Dict[str, Any]]
    cited_documents: List[Document]
    search_iterations: int
    max_iterations: int
    last_decision: Optional[SearchDecision]
    verification_results: List[VerificationResult]
    answer: Optional[str]

@singleton
class LangGraphRAGAgent:
    """LangGraph-based RAG agent with deep research capabilities"""
    
    def __init__(self, config: Optional[LangGraphRAGConfig] = None):
        self.config = config or LangGraphRAGConfig()
        self.citation_agent = CitationAgent()
        self.filename_agent = FilenameAgent()
        self.folder_categorization_agent = FolderCategorizationAgent()
        self.query_context_agent = QueryContextAgent()
        self.response_agent = ResponseAgent()
        self.llm = get_llm("nxchat")
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.graph = self._build_graph()
        logger.info("LangGraph RAG Agent initialized successfully")

    def _build_graph(self) -> CompiledStateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("check_history", self._check_history_node)
        workflow.add_node("summarize_conversation", self._summarize_conversation_node)
        workflow.add_node("initialize", self._initialize_node)
        workflow.add_node("search", self._search_node)
        workflow.add_node("verify", self._verify_node)
        workflow.add_node("decide_next", self._decide_next_node)
        workflow.add_node("respond", self._respond_node)
        
        workflow.add_edge(START, "check_history")
        
        workflow.add_conditional_edges(
            "check_history",
            self._route_history_check,
            {
                "summarize": "summarize_conversation",
                "initialize": "initialize"
            }
        )
        
        workflow.add_edge("summarize_conversation", "initialize")
        workflow.add_edge("initialize", "search")
        workflow.add_edge("search", "verify")
        workflow.add_edge("verify", "decide_next")
        
        workflow.add_conditional_edges(
            "decide_next",
            self._route_decision,
            {
                "search": "search",
                "respond": "respond"
            }
        )
        
        workflow.add_edge("respond", END)
        
        return workflow.compile()
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))

    def _format_messages(self, messages: List[BaseMessage]) -> str:
        """Format messages for both summary and response purposes"""
        if not messages:
            return "No conversation history."
        
        formatted = []
        for msg in messages:
            if isinstance(msg, SystemMessage) and "CONVERSATION SUMMARY" in msg.content:
                formatted.append(f"Previous Context: {msg.content}")
            elif isinstance(msg, HumanMessage):
                formatted.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                formatted.append(f"Assistant: {msg.content}")
        return "\n\n".join(formatted)
    
    async def _get_structured_output_with_retry(self, chain: Runnable, input_data: dict) -> Union[BaseModel, None]:
        """Get structured output with retry logic and error feedback"""
        last_error = None
        last_response = None
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt == 0:
                    result = await chain.ainvoke(input_data)
                    return result
                else:
                    error_feedback = self._format_error_feedback(last_error, last_response, attempt)
                    retry_input = input_data.copy()
                    retry_input["previous_response"] = last_response
                    retry_input["error_feedback"] = error_feedback
                    retry_input["attempt_number"] = attempt
                    result = await chain.ainvoke(retry_input)
                    return result
                        
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error: {last_error}")
                if hasattr(e, 'input_value'):
                    last_response = str(e.input_value)
                elif "Invalid JSON:" in str(e):
                    error_parts = str(e).split("input_value='")
                    if len(error_parts) > 1:
                        last_response = error_parts[1].split("'")[0]
                else:
                    last_response = "Unable to capture previous response"
                
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")
                
                if attempt == max_retries:
                    logger.error(f"All retry attempts failed: {last_error}")
                    return None
        
        return None
    
    def _format_error_feedback(self, error: str, previous_response: str, attempt: int) -> str:
        """Format error feedback showing what the model actually produced"""
        feedback = f"\n\nERROR FEEDBACK (Attempt {attempt}):\n"
        feedback += f"Your previous response was:\n{previous_response}\n\n"
        feedback += f"This failed with error: {error}\n\n"
        
        if "JSON parsing error" in error or "json_invalid" in error:
            feedback += "ISSUE: Your response was not valid JSON. Common problems:\n"
            feedback += "- You included text outside the JSON object\n"
            feedback += "- You used markdown code blocks (```json)\n"
            feedback += "- You have syntax errors in the JSON\n"
            feedback += "- You included comments or explanations\n\n"
            feedback += "SOLUTION: Respond with ONLY a valid JSON object, nothing else.\n\n"
        
        if "enum" in error.lower() or "Input should be" in error:
            feedback += "ISSUE: You used an invalid enum value.\n"
            if "search_type" in error:
                feedback += "SOLUTION: For search_type, use exactly one of: 'initial', 'focused', 'broader', 'alternative'\n"
            if "next_action" in error:
                feedback += "SOLUTION: For next_action, use exactly one of: 'search', 'verify', 'respond', 'end'\n"
            feedback += "Make sure to use lowercase values exactly as shown.\n\n"
        
        if "Field required" in error:
            feedback += "ISSUE: You're missing required fields in your JSON.\n"
            feedback += "SOLUTION: Make sure all required fields are present in your response.\n\n"
        
        feedback += "Please correct the issue and respond again with valid JSON:"
        return feedback
    
    def _check_history_node(self, state: AgentState) -> AgentState:
        """Check if conversation history needs summarization"""
        logger.info("Checking conversation history length")
        
        messages = state["messages"]
        history_text = self._format_messages(messages)
        token_count = self._count_tokens(history_text)
        logger.info(f"Current history tokens: {token_count}, Max allowed: {self.config.max_context_tokens}")
        
        return state

    def _route_history_check(self, state: AgentState) -> str:
        """Route based on history token length"""
        messages = state["messages"]
        history_text = self._format_messages(messages)
        token_count = self._count_tokens(history_text)
        
        if token_count > self.config.max_context_tokens:
            logger.info("History token length exceeded, routing to summarization")
            return "summarize"
        else:
            logger.info("History token length acceptable, routing to initialization")
            return "initialize"

    async def _summarize_conversation_node(self, state: AgentState) -> AgentState:
        """Summarize conversation history to maintain context while reducing length"""
        logger.info("Summarizing conversation history")
        
        messages = state["messages"]
        
        if len(messages) < 4:
            logger.info("Too few messages to summarize")
            return state
        
        recent_messages = messages[-2:]
        messages_to_summarize = messages[:-2]
        
        if not messages_to_summarize:
            logger.info("No messages to summarize")
            return state
        
        conversation_text = self._format_messages(messages_to_summarize)
        
        structured_llm = self.llm.with_structured_output(ConversationSummary)
        summary_chain = summary_prompt | structured_llm
        
        summary_result = await self._get_structured_output_with_retry(
            summary_chain,
            {"conversation": conversation_text},
        )
        
        if summary_result:
            summary_result = summary_result.model_dump()
            
            summary_message = SystemMessage(
                content=f"CONVERSATION SUMMARY:\n"
                    f"Summary: {summary_result['summary']}\n"
                    f"Key Topics: {', '.join(summary_result['key_topics'])}\n"
                    f"Important Context: {'; '.join(summary_result['important_context'])}\n"
                    f"User Preferences: {'; '.join(summary_result['user_preferences'])}"
            )
            
            updated_messages = [summary_message] + recent_messages
            
            logger.info(f"Conversation summarized. Reduced from {len(messages)} to {len(updated_messages)} messages")
            
            return {
                **state,
                "messages": updated_messages,
                "conversation_summary": summary_result['summary'],
                "summarized_history": summary_message.content
            }
        else:
            logger.error("Conversation summarization failed")
            return {
                **state,
                "messages": recent_messages,
                "conversation_summary": None,
                "summarized_history": None
            }


    async def _initialize_node(self, state: AgentState) -> AgentState:
        """Initialize the agent state with separate original and contextualized queries"""
        logger.info("Initializing agent state")
        
        original_query = state["messages"][-1].content
        contextualized_query = original_query
        
        conversation_history = state["messages"][:-1]
        
        if conversation_history:
            try:
                contextualized_query = await self.query_context_agent.contextualize_query(
                    query=original_query,
                    conversation_history=conversation_history
                )
                logger.info(f"Contextualized query: {contextualized_query}")
            except Exception as e:
                logger.error(f"Query contextualization failed: {str(e)}")
                contextualized_query = original_query
        
        return {
            **state,
            "original_query": original_query,
            "contextualized_query": contextualized_query,
            "search_history": [],
            "cited_documents": [],
            "search_iterations": 0,
            "max_iterations": self.config.max_search_iterations,
            "verification_results": []
        }

    async def _search_node(self, state: AgentState) -> AgentState:
        """Unified search node that handles all search types and strategies"""
        logger.info(f"Performing search - iteration {state['search_iterations']}")
        
        query = state["contextualized_query"] if state["contextualized_query"] else state["original_query"]
        search_type = SearchType.INITIAL
        search_strategy = "standard"
        
        last_decision = state.get("last_decision")
        if last_decision:
            if last_decision.search_query:
                query = last_decision.search_query
            search_type = last_decision.search_type or SearchType.FOCUSED
        
        if search_type == SearchType.INITIAL:
            top_k, top_n = self.config.initial_top_k, self.config.initial_top_n
        elif search_type == SearchType.FOCUSED:
            top_k, top_n = self.config.focused_top_k, self.config.focused_top_n
        elif search_type == SearchType.BROADER:
            top_k, top_n = self.config.broader_top_k, self.config.broader_top_n
            search_strategy = "broader"
        elif search_type == SearchType.ALTERNATIVE:
            top_k, top_n = self.config.broader_top_k, self.config.broader_top_n
            search_strategy = "alternative"
        else:
            top_k, top_n = self.config.initial_top_k, self.config.initial_top_n
        
        filters = await self._build_filters(state)
        all_cited_docs = []
        
        if search_strategy == "alternative":
            verification_result = state["verification_results"][-1] if state["verification_results"] else None
            alternative_queries = []
            
            if verification_result and verification_result.suggested_searches:
                alternative_queries = verification_result.suggested_searches[:2]
            else:
                alternative_queries = [
                    f"detailed information about {query}",
                    f"comprehensive guide {query}"
                ]
            
            for alt_query in alternative_queries:
                cited_docs = await self._perform_single_search(
                    kb_id=state["kb_id"], 
                    query=alt_query, 
                    filters=filters, 
                    top_k=top_k, 
                    top_n=top_n,
                    original_query=state["original_query"]
                )
                all_cited_docs.extend(cited_docs)
                logger.info(f"Alternative search with query '{alt_query}' found {len(cited_docs)} cited results")
            
            search_entry = {
                "query": "alternative_search",
                "search_type": search_type.value,
                "alternative_queries": alternative_queries,
                "results_count": len(all_cited_docs),
                "iteration": state["search_iterations"]
            }
        else:
            all_cited_docs = await self._perform_single_search(
                kb_id=state["kb_id"], 
                query=query, 
                filters=filters, 
                top_k=top_k, 
                top_n=top_n,
                original_query=state["original_query"]
            )
            
            search_entry = {
                "query": query,
                "search_type": search_type.value,
                "results_count": len(all_cited_docs),
                "iteration": state["search_iterations"]
            }
        
        existing_cited = state.get("cited_documents", [])
        combined_cited = existing_cited + all_cited_docs
        
        unique_cited = []
        seen_content = set()
        for doc in combined_cited:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_content:
                unique_cited.append(doc)
                seen_content.add(content_hash)        
        return {
            **state,
            "cited_documents": unique_cited,
            "search_history": state["search_history"] + [search_entry],
            "search_iterations": state["search_iterations"] + 1
        }

    async def _perform_single_search(self, kb_id: str, query: str, filters : Filter, top_k: int, top_n: int, original_query: str) -> List[Document]:
        """Perform a single search and return cited documents"""
        try:
            search_results = await vector_retrieval.retrieve(
                kb_id=kb_id,
                query=query,
                filters=filters,
                top_k=top_k,
                top_n=top_n
            )
            
            if not search_results:
                logger.warning(f"Search returned no results for query: {query}")
                return []
            
            logger.info(f"Retrieved {len(search_results)} documents for query: {query}")
            
            citations = await self.citation_agent.extract_citations(
                query=original_query,
                reference=search_results
            )
            
            cited_docs = []
            if citations.indexes:
                cited_docs = [
                    search_results[i] for i in citations.indexes if i < len(search_results)
                ]
            
            return cited_docs
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {str(e)}")
            return []

    async def _verify_node(self, state: AgentState) -> AgentState:
        """Verify if cited search results satisfy the user query with retry logic"""
        logger.info("Verifying cited search results")
        
        query = state["original_query"]
        cited_documents = state["cited_documents"]

        if not cited_documents:
            logger.warning("No cited search results to verify")
            default_verification = VerificationResult(
                is_sufficient=False,
                missing_aspects=["No cited documents found"],
                reasoning="No cited documents were found from the search",
                suggested_searches=[f"use alternative search query for {query}"]
            )
            return {
                **state,
                "verification_results": state["verification_results"] + [default_verification]
            }

        cited_documents_xml = self._format_context_as_xml(cited_documents)
        
        structured_llm = self.llm.with_structured_output(VerificationResult)
        verification_chain = verification_prompt | structured_llm
        
        input_data = {
            "query": query,
            "cited_documents_xml": cited_documents_xml
        }
        
        verification_result = await self._get_structured_output_with_retry(
            verification_chain, 
            input_data
        )
                
        if verification_result:
            logger.info(f"Is sufficient: {verification_result.is_sufficient}")
            return {
                **state,
                "verification_results": state["verification_results"] + [verification_result]
            }
        else:
            logger.error("Verification failed after all retries, using default")
            default_verification = VerificationResult(
                is_sufficient=len(cited_documents) > 0,
                missing_aspects=[],
                reasoning="Verification failed after retries, using default assessment",
                suggested_searches=[]
            )
            return {
                **state,
                "verification_results": state["verification_results"] + [default_verification]
            }

    async def _decide_next_node(self, state: AgentState) -> AgentState:
        """Decide the next action based on verification results with retry logic"""
        logger.info("Deciding next action")
        
        current_verification = state["verification_results"][-1] if state["verification_results"] else None
        search_iterations = state["search_iterations"]
        max_iterations = state["max_iterations"]
        verification_summary = self._format_verification_summary(current_verification)
        search_history = str(state["search_history"])
        
        structured_llm = self.llm.with_structured_output(SearchDecision)
        decision_chain = decision_prompt | structured_llm
        
        input_data = {
            "original_query": state["original_query"],
            "search_iterations": search_iterations,
            "max_iterations": max_iterations,
            "verification_summary": verification_summary,
            "search_history": search_history
        }
        
        decision = await self._get_structured_output_with_retry(
            decision_chain,
            input_data
        )
        
        if decision:
            logger.info(f"Taking action: {decision.next_action}")
            return {
                **state,
                "last_decision": decision
            }
        else:
            logger.error("Decision making failed after all retries, using default logic")
            
            if search_iterations >= max_iterations:
                default_decision = SearchDecision(
                    next_action=NextAction.RESPOND,
                    reasoning="Max iterations reached",
                    search_query=None,
                    search_type=None
                )
            elif current_verification and current_verification.get('is_sufficient', False):
                default_decision = SearchDecision(
                    next_action=NextAction.RESPOND,
                    reasoning="Verification indicates sufficient information",
                    search_query=None,
                    search_type=None
                )
            else:
                new_search_query = state["contextualized_query"]
                search_type = SearchType.FOCUSED
                
                if current_verification and current_verification.get('missing_aspects'):
                    missing = ", ".join(current_verification['missing_aspects'][:2])
                    new_search_query = f"{state['contextualized_query']} {missing}"
                    search_type = SearchType.ALTERNATIVE
                
                default_decision = SearchDecision(
                    next_action=NextAction.SEARCH,
                    reasoning="Continue searching with refined query",
                    search_query=new_search_query,
                    search_type=search_type
                )
            
            return {
                **state,
                "last_decision": default_decision
            }

    def _route_decision(self, state: AgentState) -> str:
        """Route based on the last decision"""
        last_decision = state.get("last_decision")
        if not last_decision:
            return "respond"
        
        if last_decision.next_action == NextAction.SEARCH:
            return "search"
        elif last_decision.next_action == NextAction.RESPOND:
            return "respond"
        else:
            return "respond"

    async def _build_filters(self, state: AgentState):
        """Build search filters based on state"""
        
        filters = Filter(must=[])
        
        query = state["contextualized_query"]
        requested_filename = await self.filename_agent.extract_filename(query=query)
        if requested_filename:
            cast(List[models.Condition], filters.must).append(
                models.FieldCondition(
                    key="metadata.original_filename",
                    match=models.MatchText(text=requested_filename),
                )
            )
        
        folder_context = await self.folder_categorization_agent.get_relevant_folder(query=query, folder_structure=state["folder_structure"]) if state.get("folder_context") else None
        if folder_context:
            cast(List[models.Condition], filters.must).append(
                models.FieldCondition(
                    key="metadata.folder_path",
                    match=models.MatchAny(any=[folder_context.relevant_folders]),
                )
            )
        
        return filters

    def _format_context_as_xml(self, contexts: List[Document]) -> str:
        """Format contexts as XML for response generation"""
        if not contexts:
            return "<documents>No relevant documents found.</documents>"
            
        xml_output = "<documents>\n"
        
        for i, doc in enumerate(contexts):
            xml_output += f'  <document index="{i+1}">\n'
            metadata = getattr(doc, 'metadata', {})
            source = metadata.get('original_filename', f'Document {i+1}')
            folder_path = metadata.get('folder_path', '')
            xml_output += f"<source>{source}</source>\n"
            if folder_path:
                xml_output += f"<folder_path>{folder_path}</folder_path>\n"
            content = getattr(doc, 'page_content', '')
            xml_output += "<document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "</document_content>\n"
            xml_output += "</document>\n"
        xml_output += "</documents>"
        
        return xml_output

    def _format_verification_summary(self, verification: Optional[VerificationResult]) -> str:
        """Format verification result for decision making"""
        if not verification:
            return "No verification performed"
        
        summary = f"Sufficient: {verification.is_sufficient}\n"
        summary += f"Reasoning: {verification.reasoning}\n"
        if verification.missing_aspects:
            summary += f"Missing: {', '.join(verification.missing_aspects)}\n"
        if verification.suggested_searches:
            summary += f"Suggested searches: {', '.join(verification.suggested_searches)}"
        
        return summary
    
    async def _respond_node(self, state: AgentState) -> AgentState:
        """Generate final response using original query"""
        logger.info("Generating final response")
        
        original_query = state["original_query"]
        cited_docs = state["cited_documents"]
        messages = state["messages"]
        
        try:
            response = await self.response_agent.generate_response(
                query=original_query,
                contexts=cited_docs,
                history=messages,
            )

            return {
                **state,
                "answer": response,
            }
            
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            final_answer = "I apologize, but I encountered an error while generating the response. Please try rephrasing your question or try again."
            
            return {
                **state,
                "answer": final_answer,
            }

    def _make_json_serializable(self, obj):
        """Convert LangChain objects to JSON serializable format"""
        if isinstance(obj, BaseMessage):
            return {
                "type": obj.__class__.__name__,
                "content": obj.content,
                "role": getattr(obj, 'role', None)
            }
        elif isinstance(obj, Document):
            return {
                "page_content": obj.page_content,
                "metadata": obj.metadata
            }
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        else:
            return str(obj)        

    async def _stream_langgraph_response(self, initial_state: AgentState) -> AsyncGenerator[str, None]:
        """A dedicated generator to format and yield streaming chunks."""
        async for chunk in self.graph.astream(initial_state):
            yield f"data: {json.dumps(self._make_json_serializable(chunk))}\n\n"
            
    async def ask(self, request: ChatRequest):
        """Process a chat request using the LangGraph workflow"""
        try:
            messages = []
            for msg in request.messages:
                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                    if msg.role == "user":
                        messages.append(HumanMessage(content=msg.content))
                    elif msg.role == "assistant":
                        messages.append(AIMessage(content=msg.content))
                    elif msg.role == "system":
                        messages.append(SystemMessage(content=msg.content))
                else:
                    messages.append(HumanMessage(content=str(msg)))
            
            initial_state = AgentState(
                messages=messages,
                original_query="",
                contextualized_query="",
                kb_id=str(request.knowledge_base_id),
                folder_context=request.folder_context,
                folder_structure=request.folder_structure or {},
                conversation_summary=None,
                summarized_history=None,
                search_history=[],
                cited_documents=[],
                search_iterations=0,
                max_iterations=self.config.max_search_iterations,
                last_decision=None,
                verification_results=[],
                answer=None,
            )
            
            logger.info(f"Initial state created with messages: {len(messages)}")
            logger.info(f"Request stream mode: {request.stream}")
            
            if not request.stream:
                final_state = await self.graph.ainvoke(initial_state)
                return final_state
            else:
                return await self._stream_langgraph_response(initial_state)
            
        except Exception as e:
            logger.error(f"LangGraph RAG Agent error: {str(e)}")
            return {
                "original_query": request.messages[-1].content if request.messages else "",
                "answer": "I apologize, but I encountered an error while processing your request. Please try again or rephrase your question.",
                "error": str(e),
                "search_iterations": 0,
                "cited_documents": [],
                "search_history": [],
            }