import os
import click
from ...common.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from .adk_agent import DocumentSearchAgent
from src.agents.task_manager import AgentTaskManager
from src.utils.logger_conf import logger
from ...common.a2a_server.server import A2AServer

class MissingAPIKeyError(Exception):
    """Exception for missing API key."""
    pass

@click.command()
@click.option('--host', default='0.0.0.0')
@click.option('--port', default=10000)
def main(host, port):
    try:
        if not os.getenv('GOOGLE_GENAI_USE_VERTEXAI') == 'TRUE':
            if not os.getenv('GOOGLE_API_KEY'):
                raise MissingAPIKeyError(
                    'GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE.'
                )

        capabilities = AgentCapabilities()
        
        skill = AgentSkill(
            id='Document search and retrieval',
            name='Document Search Expert',
            description='Specialized agent for searching and retrieving relevant documents from BM25 databases. Efficiently finds the most relevant content based on user queries and provides organized, ranked results.',
            tags=['document-search'],
            examples=[
                'What are the contents of the management project about?',
            ],
        )

        agent_card = AgentCard(
            name='DocumentSearchAgent',
            description='Specialized document search and retrieval agent that efficiently searches databases to find the most relevant content. Provides ranked results with relevance scores and organized document summaries.',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            defaultInputModes=DocumentSearchAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=DocumentSearchAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=DocumentSearchAgent()),
            host=host,
            port=port,
        )
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f'Error: {e}')
        exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        exit(1)


if __name__ == '__main__':
    main()