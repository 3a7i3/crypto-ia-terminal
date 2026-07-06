"""Launch the SDOS Terminal API server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "sdos_terminal.api.app:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info",
    )
