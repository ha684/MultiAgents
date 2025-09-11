from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.services.document_service import DocumentService
from src.event_pub import get_event_publisher
from src.utils.constants import DOCUMENT_STATUS_CHANNEL
import uuid
import asyncio  
from src.utils.logger_conf import logger

router = APIRouter(prefix="/websocket", tags=["WebSocket"])

@router.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    """Simple test WebSocket endpoint"""
    await websocket.accept()
    logger.info("WebSocket test connection established")
    
    try:
        await websocket.send_json({"message": "Connected successfully", "status": "ok"})
        
        while True:
            try:
                data = await websocket.receive_text()
                logger.info(f"Received WebSocket message: {data}")
                
                # Echo back
                await websocket.send_json({
                    "echo": data,
                    "timestamp": str(asyncio.get_event_loop().time())
                })
                
            except WebSocketDisconnect:
                logger.info("WebSocket test connection disconnected")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket test: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })
                
    except Exception as e:
        logger.error(f"WebSocket test error: {e}")
    finally:
        logger.info("WebSocket test connection closed")

@router.websocket("/ws/document_status/{document_id}")
async def document_status_ws(websocket: WebSocket, document_id: uuid.UUID):
    """WebSocket endpoint for real-time document status updates"""
    await websocket.accept()
    logger.info(f"WebSocket connection established for document: {document_id}")
    
    try:
        document_service = DocumentService()
        
        try:
            initial_status = await document_service.get_document_status(document_id)
            status_data = initial_status.model_dump(mode='json')
            await websocket.send_json({
                "type": "initial_status",
                "data": status_data
            })
            logger.info(f"Sent initial status for document {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to get initial status for document {document_id}: {e}")
            await websocket.send_json({
                "type": "error",
                "message": f"Failed to get initial status: {str(e)}"
            })
            return
        
        event_publisher = get_event_publisher()
        
        async for event in event_publisher.subscribe(DOCUMENT_STATUS_CHANNEL):
            try:
                event_doc_id = event.get("id") or event.get("document_id")
                
                if event_doc_id == str(document_id):
                    await websocket.send_json({
                        "type": "status_update",
                        "data": event
                    })
                    
                    logger.info(f"Sent status update for document {document_id}: {event.get('status')}")
                    
                    if event.get("status") in ["COMPLETED", "FAILED"]:
                        await websocket.send_json({
                            "type": "complete",
                            "message": f"Processing finished with status: {event.get('status')}"
                        })
                        logger.info(f"Processing complete for document {document_id}")
                        break
                        
            except Exception as e:
                logger.error(f"Error processing event for document {document_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error processing event: {str(e)}"
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket for document {document_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for document {document_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"WebSocket error: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info(f"WebSocket connection closed for document {document_id}")

@router.get("/health")
async def websocket_health():
    """Health check for WebSocket router"""
    return {"status": "WebSocket router is working", "endpoints": ["/ws/test", "/ws/document_status/{document_id}"]}

