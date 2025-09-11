import base64
import datetime
import json
import os
import uuid
import traceback
import asyncio
from typing import Optional, Any, AsyncGenerator, List, Dict
from ...common.types import (
    AgentCard,
    DataPart,
    FileContent,
    FilePart,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from google.adk import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events.event import Event as ADKEvent
from google.adk.events.event_actions import EventActions as ADKEventActions
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.genai import types
from ...agents.host_agent.host_agent import HostAgent
from ...agents.host_agent.remote_agent_connection import TaskCallbackArg
from ..server.application_manager import ApplicationManager
from ...services.types import Conversation, Event
from ...utils.agent_card import get_agent_card
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from src.utils.logger_conf import logger
from src.db.repository.conversation import ConversationRepository
from google.adk.events.event import Event as ADKEvent
from ...utils.decorators import singleton
class ADKHostManagerError(Exception):
    """Base exception for ADKHostManager errors"""
    pass

class DatabaseConnectionError(ADKHostManagerError):
    """Raised when database connection fails"""
    pass

class MessageProcessingError(ADKHostManagerError):
    """Raised when message processing fails"""
    pass

class TaskProcessingError(ADKHostManagerError):
    """Raised when task processing fails"""
    pass

@singleton
class ADKHostManager(ApplicationManager):
    """An implementation of database-backed management for production use
    
    This implements the interface of the ApplicationManager to plug into
    the AgentServer. This acts as the service contract that the Mesop app
    uses to send messages to the agent and provide information for the frontend.
    """

    _conversations: list[Conversation]
    _tasks: list[Task]
    _events: dict[str, Event]
    _pending_message_ids: list[str]
    _agents: list[AgentCard]
    _task_map: dict[str, str]
    _host_runner: dict[str, Runner]

    def __init__(self, api_key: str = '', uses_vertex_ai: bool = False, db_url: str = '') -> None:
        try:
            if not db_url:
                raise ValueError("Database URL is required for production use")
            
            try:
                self.conv_repository = ConversationRepository()
                logger.info("DatabaseService initialized successfully")
            except Exception as e:
                logger.error(f"Critical error initializing DatabaseService: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise DatabaseConnectionError(f"Failed to initialize database service: {e}")
            
            self._session_service = DatabaseSessionService(db_url=db_url)
            logger.info("DatabaseSessionService initialized successfully")

            
            try:
                self._artifact_service = InMemoryArtifactService()
                self._memory_service = InMemoryMemoryService()
                logger.info("Core services initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing core services: {e}")
                raise ADKHostManagerError(f"Failed to initialize core services: {e}")

            api_key = api_key or os.environ.get('GOOGLE_API_KEY', '')
            self.uses_vertex_ai = (
                uses_vertex_ai
                or os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', '').upper() == 'TRUE'
            )

            try:
                if self.uses_vertex_ai:
                    os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'TRUE'
                elif api_key:
                    os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'FALSE'
                    os.environ['GOOGLE_API_KEY'] = api_key
                else:
                    logger.warning("No API key provided and VertexAI not enabled")
            except Exception as e:
                logger.error(f"Error configuring API settings: {e}")
                
            self._host_agent = None
            self._pending_messages = {} 
            self._pending_messages_lock = asyncio.Lock()
            self._cleanup_task = None
            self._agents = []
            self._task_map = {}
            self._next_id = {}
            self._host_runner = {}
            
            logger.info("ADKHostManager initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Critical error during ADKHostManager initialization: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def update_api_key(
        self, 
        api_key: str,
        app_name: str,
    ) -> str:
        """Update the API key and reinitialize the host if needed"""
        try:
            if api_key:
                if not self.uses_vertex_ai:
                    os.environ['GOOGLE_API_KEY'] = api_key
                    await self._initialize_host(app_name)
                    logger.info("API key updated and host reinitialized")
                    return f"API key updated and host reinitialized for app: {app_name}"
                else:
                    return f"API key updated for app: {app_name}"
            else:
                return f"No API key provided for app: {app_name}"
        except Exception as e:
            logger.error(f"Error updating API key: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ADKHostManagerError(f"Failed to update API key: {e}")

    async def _initialize_host(
        self,
        app_name: str,
    ) -> str:
        """Initialize the host runner with error handling"""
        try:
            if app_name in list(self._host_runner.keys()):
                return f"Host runner already initialized for app: {app_name}"
            
            if self._host_agent is None:
                self._host_agent = HostAgent([], self.task_callback)
                
            agent = self._host_agent.create_agent()
            self._host_runner[app_name] = Runner(
                app_name=app_name,
                agent=agent,
                artifact_service=self._artifact_service,
                session_service=self._session_service,
                memory_service=self._memory_service,
            )   
            logger.info("Host runner initialized successfully")
            return f"Host runner initialized successfully for app: {app_name}"
        except Exception as e:
            logger.error(f"Error creating host runner: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ADKHostManagerError(f"Failed to initialize host runner: {e}")

    async def create_conversation(
        self, app_name: str, user_id: str
    ) -> Conversation:
        """Create a new conversation with comprehensive error handling"""
        try:
            session = await self._session_service.create_session(
                app_name=app_name, user_id=user_id
            )
            conversation_id = session.id
            
            conversation = await self.conv_repository.create_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                app_name=app_name,
            )
            logger.info(f"Created conversation {conversation_id} for user {user_id}")
            return conversation
            
        except Exception as e:
            logger.error(f"Error creating conversation for user {user_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ADKHostManagerError(f"Failed to create conversation: {e}")

    async def sanitize_message(self, message: Message) -> Message:
        """Sanitize message with error handling"""
        try:    
            if 'message_id' not in message.metadata:
                message.metadata.update({'message_id': str(uuid.uuid4())})
                
            if 'conversation_id' in message.metadata:
                conversation_id = message.metadata['conversation_id']
                try:
                    conversation = await self.conv_repository.get_conversation(
                        conversation_id,
                        app_name=message.metadata.get('app_name',None)
                    )
                    if conversation:
                        messages = await self.conv_repository.get_messages(conversation_id)
                        if messages:
                            last_message_id = get_message_id(messages[-1])
                            if last_message_id:
                                message.metadata.update(
                                    {'last_message_id': last_message_id}
                                )
                except Exception as e:
                    logger.warning(f"Error getting conversation history for {conversation_id}: {e}")                    
            return message
            
        except Exception as e:
            logger.error(f"Error sanitizing message: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise MessageProcessingError(f"Failed to sanitize message: {e}")

    async def process_message(
        self, 
        message: Message,
        stream: bool = False
    ) -> AsyncGenerator[dict, None]:
        """Process message with comprehensive error handling and streaming"""
        message_id = None
        
        try: 
            message_id = get_message_id(message)
            conversation_id = (
                message.metadata.get('conversation_id') if message.metadata else None
            )
            user_id = (
                message.metadata.get('user_id') if message.metadata else None
            )
            app_name = (
                message.metadata.get('app_name') if message.metadata else None
            )

            logger.info(f"Processing message {message_id} for conversation {conversation_id} with app_name {app_name}")
            
            if conversation_id:
                await self.conv_repository.add_message(message, conversation_id)
                logger.debug(f"Message {message_id} stored in database")
            
            if message_id:
                async with self._pending_messages_lock:
                    user_pending_count = sum(1 for info in self._pending_messages.values() if info.get('user_id') == user_id)
                    if user_pending_count >= 10:
                        raise MessageProcessingError(f"Too many pending messages for user {user_id}")
                    
                    self._pending_messages[message_id] = {
                        'timestamp': datetime.datetime.now(datetime.timezone.utc).timestamp(),
                        'user_id': user_id,
                        'conversation_id': conversation_id
                    }

            state_update = {
                'input_message_metadata': message.metadata,
                'session_id': conversation_id,
            }
            
            session = await self._session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=conversation_id
            )
            await self._session_service.append_event(
                session=session,
                event=ADKEvent(
                    id=ADKEvent.new_id(),
                    author='HostAgent',
                    invocation_id=ADKEvent.new_id(),
                    actions=ADKEventActions(state_delta=state_update),
                ),
            )
            logger.info(f"Appended event to session {conversation_id}")
            
            if app_name not in list(self._host_runner.keys()):
                raise ADKHostManagerError(f"Host runner not found for app: {app_name}. Available: {list(self._host_runner.keys())}")
            
            final_event = None
            
            async for event in self._host_runner[app_name].run_async(
                user_id=user_id,
                session_id=conversation_id,
                new_message=self.adk_content_from_message(message),
                run_config = RunConfig(
                    streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE,
                )
            ):
                agent_name = None
                if event.is_final_response():
                    final_event = event
                    
                    if stream:
                        final_event.content.role = 'model'
                        response = self.adk_content_to_message(
                            final_event.content, 
                            conversation_id, 
                            app_name, 
                            user_id
                        )
                        
                        last_message_id = get_message_id(message)
                        new_message_id = str(uuid.uuid4())
                                
                        response.metadata = {
                            **(message.metadata or {}),
                            'last_message_id': last_message_id,
                            'message_id': new_message_id,
                        }
                        
                        yield {
                            'type': 'final_result',
                            'response': response.model_dump() if hasattr(response, 'model_dump') else response.__dict__,
                        }
                                        
                elif stream:
                    content = None
                    content_type = 'text'
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                content = part.text
                                content_type = 'text'
                                break
                            elif part.function_call:
                                func_call = part.function_call
                                content = func_call.name
                                content_type = 'function_call'
                                agent_name = func_call.args.get('agent_name', None)
                                break
                            elif part.function_response:
                                func_resp = part.function_response
                                content = func_resp.name
                                content_type = 'function_response'
                                break
                    
                    if content is not None:
                        if agent_name:
                            yield {
                                'type': 'progress',
                                'is_task_complete': False,
                                'require_user_input': False,
                                'content': content,
                                'content_type': content_type,
                                'agent_name': agent_name,
                            }
                        else:
                            yield {
                                'type': 'progress',
                                'is_task_complete': False,
                                'require_user_input': False,
                                'content': content,
                                'content_type': content_type,
                            }
            
            if final_event:

                if conversation_id:
                    final_event.content.role = 'model'
                    response = self.adk_content_to_message(
                        final_event.content, 
                        conversation_id, 
                        app_name, 
                        user_id
                    )
                    
                    last_message_id = get_message_id(message)
                    new_message_id = str(uuid.uuid4())
                            
                    response.metadata = {
                        **(message.metadata or {}),
                        'last_message_id': last_message_id,
                        'message_id': new_message_id,
                    }
                    
                    await self.conv_repository.add_message(response, conversation_id)
                    
                    if not stream:
                        yield {
                            'type': 'final_result',
                            'response': response.model_dump() if hasattr(response, 'model_dump') else response.__dict__,
                        }
                    
            logger.info(f"Message processing completed for {message_id}")
            
        except Exception as e:
            logger.error(f"Critical error processing message {message_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            if message_id:
                async with self._pending_messages_lock:
                    self._pending_messages.pop(message_id, None)
                    
            raise MessageProcessingError(f"Failed to process message {message_id}: {e}") from e
        
        finally:
            if message_id:
                async with self._pending_messages_lock:
                    self._pending_messages.pop(message_id, None)

    async def add_task(self, task: Task):
        """Add task with error handling"""
        try:
            await self.conv_repository.add_task(task)
            logger.debug(f"Task {task.id} added successfully")
        except Exception as e:
            logger.error(f"Error adding task {task.id}: {e}")
            raise TaskProcessingError(f"Failed to add task: {e}")
        
    async def update_task(self, task: Task):
        """Update task with error handling"""
        try:
            await self.conv_repository.add_task(task)
            logger.debug(f"Task {task.id} updated successfully")
        except Exception as e:
            logger.error(f"Error updating task {task.id}: {e}")
            raise TaskProcessingError(f"Failed to update task: {e}")

    async def task_callback(self, task: TaskCallbackArg, agent_card: AgentCard):
        """Task callback with comprehensive error handling"""
        try:
            logger.debug(f"Processing task callback for {task.id}")
            
            try:
                await self.emit_event(task, agent_card)
            except Exception as e:
                logger.error(f"Error emitting task event: {e}")
                
            if isinstance(task, TaskStatusUpdateEvent):
                try:
                    current_task = await self.add_or_get_task(task)
                    current_task.status = task.status
                    
                    await self.attach_message_to_task(task.status.message, current_task.id)
                    await self.insert_message_history(current_task, task.status.message)
                    await self.update_task(current_task)
                    await self.insert_id_trace(task.status.message)
                    
                    return current_task
                except Exception as e:
                    logger.error(f"Error processing TaskStatusUpdateEvent: {e}")
                    raise TaskProcessingError(f"Failed to process status update: {e}")
                    
            elif isinstance(task, TaskArtifactUpdateEvent):
                try:
                    current_task = await self.add_or_get_task(task)
                    await self.process_artifact_event(current_task, task)
                    await self.update_task(current_task)
                    return current_task
                except Exception as e:
                    logger.error(f"Error processing TaskArtifactUpdateEvent: {e}")
                    raise TaskProcessingError(f"Failed to process artifact update: {e}")
                    
            try:
                existing_task = await self.conv_repository.get_task(task.id)
                if not existing_task:
                    await self.attach_message_to_task(task.status.message, task.id)
                    await self.insert_id_trace(task.status.message)
                    await self.add_task(task)
                    return task
                    
                await self.attach_message_to_task(task.status.message, task.id)
                await self.insert_id_trace(task.status.message)
                await self.update_task(task)
                return task
                
            except Exception as e:
                logger.error(f"Error processing generic task: {e}")
                raise TaskProcessingError(f"Failed to process task: {e}")
                
        except Exception as e:
            logger.error(f"Critical error in task callback for {task.id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def emit_event(self, task: TaskCallbackArg, agent_card: AgentCard):
        """Emit event with error handling"""
        try:
            content = None
            conversation_id = get_conversation_id(task)
            metadata = (
                {'conversation_id': conversation_id} if conversation_id else None
            )
            
            if isinstance(task, TaskStatusUpdateEvent):
                if task.status.message:
                    content = task.status.message
                else:
                    content = Message(
                        parts=[TextPart(text=str(task.status.state))],
                        role='agent',
                        metadata=metadata,
                    )
            elif isinstance(task, TaskArtifactUpdateEvent):
                content = Message(
                    parts=task.artifact.parts,
                    role='agent',
                    metadata=metadata,
                )
            elif task.status and task.status.message:
                content = task.status.message
            elif task.artifacts:
                parts = []
                for a in task.artifacts:
                    parts.extend(a.parts)
                content = Message(
                    parts=parts,
                    role='agent',
                    metadata=metadata,
                )
            else:
                content = Message(
                    parts=[TextPart(text=str(task.status.state))],
                    role='agent',
                    metadata=metadata,
                )
            
        except Exception as e:
            logger.error(f"Error emitting event: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def attach_message_to_task(self, message: Message | None, task_id: str):
        """Attach message to task with error handling"""
        try:
            if message and message.metadata and 'message_id' in message.metadata:
                await self.conv_repository.add_task_mapping(message.metadata['message_id'], task_id)
        except Exception as e:
            logger.error(f"Error attaching message to task {task_id}: {e}")
            raise e

    async def insert_id_trace(self, message: Message | None):
        """Insert ID trace with error handling"""
        try:
            if not message:
                return
            message_id = get_message_id(message)
            last_message_id = get_last_message_id(message)
            if message_id and last_message_id:
                await self.conv_repository.add_next_id_mapping(last_message_id, message_id)
        except Exception as e:
            logger.error(f"Error inserting ID trace: {e}")
            raise e

    async def insert_message_history(self, task: Task, message: Message | None):
        """Insert message history with error handling"""
        try:
            if not message:
                return
            if task.history is None:
                task.history = []
            message_id = get_message_id(message)
            if not message_id:
                return
            if get_message_id(task.status.message) not in [
                get_message_id(x) for x in task.history
            ]:
                task.history.append(task.status.message)
            else:
                logger.warning(
                    f'Message id {get_message_id(task.status.message)} already in history'
                )
        except Exception as e:
            logger.error(f"Error inserting message history: {e}")
            raise e

    async def add_or_get_task(self, task: TaskCallbackArg):
        """Add or get task with error handling"""
        try:
            current_task = await self.conv_repository.get_task(task.id)
            if not current_task:
                conversation_id = None
                if task.metadata and 'conversation_id' in task.metadata:
                    conversation_id = task.metadata['conversation_id']
                current_task = Task(
                    id=task.id,
                    status=TaskStatus(
                        state=TaskState.SUBMITTED
                    ),
                    metadata=task.metadata,
                    artifacts=[],
                    sessionId=conversation_id,
                )
                await self.add_task(current_task)
                
            return current_task
            
        except Exception as e:
            logger.error(f"Error adding or getting task {task.id}: {e}")
            raise TaskProcessingError(f"Failed to add or get task: {e}")

    async def process_artifact_event(
        self, current_task: Task, task_update_event: TaskArtifactUpdateEvent
    ):
        """Process artifact event with error handling"""
        try:
            artifact = task_update_event.artifact
            if not artifact.append:
                if artifact.lastChunk is None or artifact.lastChunk:
                    if not current_task.artifacts:
                        current_task.artifacts = []
                    current_task.artifacts.append(artifact)
                else:
                    # Store chunk in database
                    try:
                        await self.conv_repository.add_artifact_chunk(
                            task_update_event.id,
                            artifact.index,
                            {
                                'parts': self.conv_repository._serialize_parts(artifact.parts),
                                'append': artifact.append,
                                'lastChunk': artifact.lastChunk
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error storing artifact chunk: {e}")
                        raise
            else:
                # Get chunks from database
                try:
                    chunks = await self.conv_repository.get_artifact_chunks(task_update_event.id)
                    if artifact.index in chunks:
                        current_temp_artifact = type('Artifact', (), chunks[artifact.index])()
                        current_temp_artifact.parts.extend(artifact.parts)
                        if artifact.lastChunk:
                            current_task.artifacts.append(current_temp_artifact)
                            await self.conv_repository.remove_artifact_chunk(task_update_event.id, artifact.index)
                except Exception as e:
                    logger.error(f"Error processing artifact chunks: {e}")
                    raise
                    
        except Exception as e:
            logger.error(f"Error processing artifact event: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise TaskProcessingError(f"Failed to process artifact event: {e}")

    async def get_conversation(
        self, conversation_id: str | None
    ) -> Conversation | None:
        """Get conversation with error handling"""
        try:
            if not conversation_id:
                return None
            return await self.conv_repository.get_conversation(conversation_id)
        except Exception as e:
            logger.error(f"Error getting conversation {conversation_id}: {e}")
            return None

    async def get_pending_messages(self) -> list[tuple[str, str]]:
        """Get pending messages with error handling"""
        try:
            rval = []
            async with self._pending_messages_lock:
                message_ids = list(self._pending_messages.keys())
                
            for message_id in message_ids:
                try:
                    task_id = await self.conv_repository.get_task_id_for_message(message_id)
                    if task_id:
                        task = await self.conv_repository.get_task(task_id)
                        if not task:
                            rval.append((message_id, ''))
                        elif task.history and task.history[-1].parts:
                            if len(task.history) == 1:
                                rval.append((message_id, 'Working...'))
                            else:
                                part = task.history[-1].parts[0]
                                rval.append(
                                    (
                                        message_id,
                                        part.text
                                        if part.type == 'text'
                                        else 'Working...',
                                    )
                                )
                        else:
                            rval.append((message_id, 'Working...'))
                    else:
                        rval.append((message_id, ''))
                except Exception as e:
                    logger.warning(f"Error processing pending message {message_id}: {e}")
                    rval.append((message_id, 'Error'))
            return rval
        except Exception as e:
            logger.error(f"Error getting pending messages: {e}")
            return []

    async def register_agent(
        self, 
        url: str, 
        app_name: str,
    ) -> str:
        """Register agent with error handling"""
        try:
            normalized_url = f"http://{url}" if not url.startswith('http') else url
            
            for agent_wrapper in self._agents:
                agent_card : AgentCard = agent_wrapper["agent"]
                stored_app_name = agent_wrapper["app_name"]
                current_url_clean = normalized_url.rstrip('/')
                stored_url_clean = agent_card.url.rstrip('/')
                if (current_url_clean == stored_url_clean and stored_app_name == app_name):
                    return f"Agent already registered for app '{app_name}': {normalized_url}"

            agent_data = await get_agent_card(url if not url.startswith('http') else url.replace('http://', ''))            
            agent_data.url = normalized_url
            
            agent_wrapper = {
                "agent": agent_data,
                "app_name": app_name
            }
            self._agents.append(agent_wrapper)
            await self._initialize_host(app_name)
            await self._host_agent.register_agent_card(agent_data)
            return f"Agent registered successfully for app '{app_name}': {normalized_url}."
        except Exception as e:
            logger.error(f"Error registering agent {url}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ADKHostManagerError(f"Failed to register agent: {e}")
        
    @property
    def agents(self) -> List[Dict[str, Any]]:
        """Returns list of agent wrappers with structure: {"agent": AgentCard, "app_name": str}"""
        return self._agents

    async def list_conversations(self, app_name: Optional[str], user_id: Optional[str]) -> list[Conversation]:
        """List conversations with error handling"""
        try:
            return await self.conv_repository.list_conversations(app_name, user_id)
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            raise ADKHostManagerError(f"Failed to list conversations: {e}")

    async def list_tasks(self) -> list[Task]:
        """List tasks with error handling"""
        try:
            return await self.conv_repository.list_tasks()
        except Exception as e:
            logger.error(f"Error listing tasks: {e}")
            raise ADKHostManagerError(f"Failed to list tasks: {e}")

    async def get_events(
        self
    ) -> None:
        """Deprecated"""
        raise NotImplementedError("get_events is deprecated")

    async def get_events_host_agent(
        self, 
        conversation_id: Optional[str]
    ) -> Any:
        """Get events with error handling"""
        try:
            sessions = await self.conv_repository.get_events_host_agent(
                conversation_id=conversation_id
            )
            return sessions
        except Exception as e:
            logger.error(f"Error getting events for conversation {conversation_id}: {e}")
            raise ADKHostManagerError(f"Failed to get events: {e}")

    async def get_events_all(
        self, 
        conversation_id: Optional[str]
    ) -> Any:
        """Get all events"""
        try:
            sessions = await self.conv_repository.get_events_all(
                conversation_id=conversation_id
            )
            return sessions
        except Exception as e:
            logger.error(f"Error getting events for conversation {conversation_id}: {e}")
            raise ADKHostManagerError(f"Failed to get events: {e}")

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all related data with error handling"""
        try:
            return await self.conv_repository.delete_conversation(conversation_id)
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            raise ADKHostManagerError(f"Failed to delete conversation: {e}")

    def adk_content_from_message(self, message: Message) -> types.Content:
        """Convert message to ADK content with error handling"""
        try:
            parts: list[types.Part] = []
            for part in message.parts:
                try:
                    if part.type == 'text':
                        parts.append(types.Part.from_text(text=part.text))
                    elif part.type == 'data':
                        json_string = json.dumps(part.data)
                        parts.append(types.Part.from_text(text=json_string))
                    elif part.type == 'file':
                        if part.uri:
                            parts.append(
                                types.Part.from_uri(
                                    file_uri=part.uri, mime_type=part.mimeType
                                )
                            )
                        elif part.bytes:
                            parts.append(
                                types.Part.from_bytes(
                                    data=part.bytes.encode('utf-8'),
                                    mime_type=part.mimeType,
                                )
                            )
                        else:
                            logger.warning(f"Unsupported file part without URI or bytes")
                            continue
                    else:
                        logger.warning(f"Unknown part type: {part.type}")
                        continue
                except Exception as e:
                    logger.error(f"Error processing message part {part.type}: {e}")
                    continue
                    
            return types.Content(parts=parts, role=message.role)
            
        except Exception as e:
            logger.error(f"Error converting message to ADK content: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return types.Content(
                parts=[types.Part.from_text(text="Error processing message")], 
                role=message.role if message else 'user'
            )

    def adk_content_to_message(
        self, content: types.Content, conversation_id: str, app_name: str, user_id: str
    ) -> Message:
        """Convert ADK content to message with error handling"""
        try:
            parts: list[Part] = []

            if not content.parts:
                return Message(
                    parts=[],
                    role=content.role if content.role == 'user' else 'agent',
                    metadata={'conversation_id': conversation_id},
                )
                
            for part in content.parts:
                try:
                    if part.text:
                        try:
                            data = json.loads(part.text)
                            parts.append(DataPart(data=data))
                        except (json.JSONDecodeError, TypeError):
                            parts.append(TextPart(text=part.text))
                    elif part.inline_data:
                        try:
                            parts.append(
                                FilePart(
                                    data=part.inline_data.decode('utf-8'),
                                    mimeType=part.inline_data.mime_type,
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error processing inline data: {e}")
                            continue
                    elif part.file_data:
                        try:
                            parts.append(
                                FilePart(
                                    file=FileContent(
                                        uri=part.file_data.file_uri,
                                        mimeType=part.file_data.mime_type,
                                    )
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error processing file data: {e}")
                            continue
                    elif part.video_metadata:
                        try:
                            parts.append(DataPart(data=part.video_metadata.model_dump()))
                        except Exception as e:
                            logger.error(f"Error processing video metadata: {e}")
                            continue
                    elif part.thought:
                        parts.append(TextPart(text='thought'))
                    elif part.executable_code:
                        try:
                            parts.append(DataPart(data=part.executable_code.model_dump()))
                        except Exception as e:
                            logger.error(f"Error processing executable code: {e}")
                            continue
                    elif part.function_call:
                        try:
                            parts.append(DataPart(data=part.function_call.model_dump()))
                        except Exception as e:
                            logger.error(f"Error processing function call: {e}")
                            continue
                    elif part.function_response:
                        try:
                            response_parts = self._handle_function_response(
                                part, 
                                conversation_id, 
                                app_name, 
                                user_id
                            )
                            parts.extend(response_parts)
                        except Exception as e:
                            logger.error(f"Error processing function response: {e}")
                            continue
                    else:
                        logger.warning(f"Unknown content part type, skipping")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error processing content part: {e}")
                    continue
                    
            return Message(
                role=content.role if content.role == 'user' else 'agent',
                parts=parts,
                metadata={'conversation_id': conversation_id},
            )
            
        except Exception as e:
            logger.error(f"Error converting ADK content to message: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Message(
                role='agent',
                parts=[TextPart(text="Error processing response")],
                metadata={'conversation_id': conversation_id},
            )

    def _handle_function_response(
        self, 
        part: types.Part, 
        conversation_id: str,
        app_name: str,
        user_id: str
    ) -> list[Part]:
        """Handle function response with error handling"""
        parts = []
        try:
            if not part.function_response or not part.function_response.response:
                return parts
                
            result = part.function_response.response.get('result', [])
            
            for p in result:
                try:
                    if isinstance(p, str):
                        parts.append(TextPart(text=p))
                    elif isinstance(p, dict):
                        if 'type' in p and p['type'] == 'file':
                            try:
                                parts.append(FilePart(**p))
                            except Exception as e:
                                logger.error(f"Error creating FilePart: {e}")
                                parts.append(DataPart(data=p))
                        else:
                            parts.append(DataPart(data=p))
                    elif isinstance(p, DataPart):
                        try:
                            if 'artifact-file-id' in p.data:
                                file_part = self._artifact_service.load_artifact(
                                    user_id=user_id,
                                    session_id=conversation_id,
                                    app_name=app_name,
                                    filename=p.data['artifact-file-id'],
                                )
                                file_data = file_part.inline_data
                                base64_data = base64.b64encode(file_data.data).decode('utf-8')
                                parts.append(
                                    FilePart(
                                        file=FileContent(
                                            bytes=base64_data,
                                            mimeType=file_data.mime_type,
                                            name='artifact_file',
                                        )
                                    )
                                )
                            else:
                                parts.append(DataPart(data=p.data))
                        except Exception as e:
                            logger.error(f"Error processing DataPart with artifact: {e}")
                            parts.append(DataPart(data=p.data))
                    else:
                        try:
                            parts.append(TextPart(text=json.dumps(p)))
                        except Exception as e:
                            logger.error(f"Error serializing unknown part type: {e}")
                            parts.append(TextPart(text=str(p)))
                            
                except Exception as e:
                    logger.error(f"Error processing function response part: {e}")
                    parts.append(TextPart(text=f"Error processing part: {str(p)[:100]}"))
                    
        except Exception as e:
            logger.error(f"Error handling function response: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                parts.append(DataPart(data=part.function_response.model_dump()))
            except Exception as fallback_error:
                logger.error(f"Error creating fallback DataPart: {fallback_error}")
                parts.append(TextPart(text="Error processing function response"))
                
        return parts


def get_message_id(m: Message | None) -> str | None:
    """Get message ID with error handling"""
    try:
        if not m or not m.metadata or 'message_id' not in m.metadata:
            return None
        return m.metadata['message_id']
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None


def get_last_message_id(m: Message | None) -> str | None:
    """Get last message ID with error handling"""
    try:
        if not m or not m.metadata or 'last_message_id' not in m.metadata:
            return None
        return m.metadata['last_message_id']
    except Exception as e:
        logger.error(f"Error getting last message ID: {e}")
        return None


def get_conversation_id(
    t: (
        Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent | Message | None
    ),
) -> str | None:
    """Get conversation ID with error handling"""
    try:
        if (
            t
            and hasattr(t, 'metadata')
            and t.metadata
            and 'conversation_id' in t.metadata
        ):
            return t.metadata['conversation_id']
        return None
    except Exception as e:
        logger.error(f"Error getting conversation ID: {e}")
        return None


def task_still_open(task: Task | None) -> bool:
    """Check if task is still open with error handling"""
    try:
        if not task or not task.status:
            return False
        return task.status.state in [
            TaskState.SUBMITTED,
            TaskState.WORKING,
            TaskState.INPUT_REQUIRED,
        ]
    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return False