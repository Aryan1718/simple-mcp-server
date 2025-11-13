from mcp.server.fastmcp import FastMCP

# 1. Create MCP server instance
mcp = FastMCP(
    name="simple-mcp",
    instructions="This MCP server provides simple tools like text summarization.",
)

# 2. Register a tool
@mcp.tool()
def summarize_text(text: str) -> str:
    """
    Very simple summarizer.
    Input: long text
    Output: short summary
    """
    # If text is too short, just return it
    if len(text.split()) < 10:
        return f"Summary: {text}"

    # Basic summarization logic (first sentence only)
    sentences = text.split(".")
    first_sentence = sentences[0].strip()
    return f"Summary: {first_sentence}"

# 3. Run server over HTTP
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
