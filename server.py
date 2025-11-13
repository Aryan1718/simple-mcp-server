from fastmcp import FastMCP

# 1. Create FastMCP server instance
mcp = FastMCP("simple-mcp")

# 2. Register a tool
@mcp.tool
def summarize_text(text: str) -> str:
    """
    Very simple summarizer.
    Input: long text
    Output: short summary
    """
    # If text is too short, just return it
    if len(text.split()) < 10:
        return f"Summary: {text}"

    # Basic summarization logic (take the first sentence)
    sentences = text.split(".")
    first_sentence = sentences[0].strip()
    return f"Summary: {first_sentence}"

# 3. Local run only – FastMCP Cloud ignores this block
if __name__ == "__main__":
    # For local testing: `python server.py`
    mcp.run()  # default transport is fine here
