# 📊 Excel Analyst Agent

An intelligent Excel data analysis application powered by AI. Upload your Excel or CSV files and analyze them using natural language queries in English.

### 🌐 Try the Live Demo
- 🔗 **[Live Demo on Hugging Face Spaces](https://huggingface.co/spaces/devsu/excel-analyst-agent)**

## 🌟 Features

- **Natural Language Queries**: Describe what you want in plain English
- **Automatic Code Generation**: AI generates Python code to fulfill your requests
- **Data Analysis**: Perform complex data manipulation and statistical analysis
- **Visualizations**: Automatic chart and graph generation
- **Multi-Agent System**: MasterAgent coordinates ExcelAnalysisAgent and WebSearchAgent
- **Isolated Execution**: generated code runs in a separate, locked-down process (see [Security](#-security))
- **User-Friendly Interface**: Clean Gradio web interface

## 🏗️ Architecture

The application uses a multi-agent architecture built with OpenAI Agents SDK and Model Context Protocol (MCP):

```
┌─────────────────────────────────────────────────────────────┐
│                      Gradio Interface                        │
│                  (File Upload + Query Input)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 Master Agent (Coordinator)                   │
│  - Orchestrates analysis workflow                            │
│  - Delegates to agents/tools as needed                       │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
            ▼                             ▼
┌──────────────────────────────┐   ┌───────────────────────────┐
│       ExcelAnalysisAgent     │   │      WebSearchAgent       │
│  - Uses MCP: execute_python_code  │   │  - Uses MCP: search_web      │
│  - Python Sandbox via MCP Server  │   │  - DuckDuckGo documentation   │
└───────────┬───────────────────┘   └──────────────────────────┘
            │
            ▼
┌───────────────────────┐
│   MCP Server (stdio)  │
│  - PythonSandboxTool  │
│  - WebSearchTool      │
└───────────────────────┘
```

**Key Features**:
- **MCP (Model Context Protocol)**: Standardized tool exposure via stdio servers
- **Master Orchestration**: MasterAgent coordinates specialized agents
- **Tool Filtering**: Each agent sees only its designated tools
- **Assisted Recovery**: On errors, MasterAgent consults WebSearchAgent for help

### Project Structure

```
excel-analyst-agent/
├── app.py                          # Gradio UI entry point
├── requirements.txt                # Python dependencies
├── README.md                       # This file
└── app_agents/
    ├── __init__.py
    ├── master_agent.py             # Master agent (coordinator)
    ├── excel_agent.py              # Excel analysis agent (no handoff)
    ├── web_agent.py                # Web Search support agent
    ├── mcp_server.py               # MCP stdio server (FastMCP)
    └── tools/
        ├── __init__.py
        ├── python_tool.py          # AST validation + sandbox launcher
        ├── sandbox_worker.py       # locked-down child process that runs the code
        └── web_search_tool.py      # DuckDuckGo search integration
```

### Components

1. **Master Agent** (`app_agents/master_agent.py`)
   - Coordinates specialized agents
   - Decides when to consult WebSearchAgent
   - Retries analysis with web context when helpful

2. **Excel Analysis Agent** (`app_agents/excel_agent.py`)
   - Interprets user queries
   - Generates and executes Python code for analysis
   - Uses MCP tool `execute_python_code`

3. **WebSearch Agent** (`app_agents/web_agent.py`)
   - Finds documentation and examples
   - Uses MCP tool `search_web`
   - Provides context to MasterAgent

4. **MCP Server** (`app_agents/mcp_server.py`)
   - FastMCP-based stdio server
   - Exposes tools: `execute_python_code` and `search_web`
   - Lazy-loads tool implementations for fast startup
   - Tool filtering ensures each agent sees only its tools

5. **Python Sandbox Tool** (`app_agents/tools/python_tool.py`)
   - AST validation, then execution in an isolated child process (`sandbox_worker.py`)
   - Supports pandas, numpy, matplotlib, seaborn
   - 30-second timeout and captures output/figures

6. **Web Search Tool** (`app_agents/tools/web_search_tool.py`)
   - DuckDuckGo integration (no API key required)
   - Returns top 5 search results

## 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- OpenAI API key

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd excel-analyst-agent
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
# Create a .env file
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

Or export directly:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

## 💻 Usage

### Running Locally

Start the application:
```bash
python app.py
```

The interface will be available at `http://localhost:7860`

### Using the Interface

1. **Upload File**: Click to upload your `.xlsx` or `.csv` file
2. **Enter Query**: Describe what you want to analyze in English
3. **Click Analyze**: The agent will process your request
4. **View Results**: See text output, data tables, and visualizations

### Example Queries

- *"Show me the average sales per region and create a bar chart"*
- *"Find the top 10 customers by revenue"*
- *"Calculate monthly trends and visualize them as a line chart"*
- *"Identify outliers in the price column and show them in a box plot"*
- *"Create a correlation matrix heatmap for all numeric columns"*
- *"Group by category and show the sum of sales with a pie chart"*

## 🔧 Configuration

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required)

### Model Configuration

By default, the application uses `gpt-4o-mini`. To change the model, edit the initialization in `app.py`:

```python
agent = MasterAgent(api_key=used_api_key, model="gpt-4o")
```

### Timeout Settings

Code execution timeout is set to 30 seconds by default. To change it, modify `app_agents/mcp_server.py`:

```python
_python_tool = PythonSandboxTool(timeout=60)  # 60 seconds
```

Agent execution has a maximum of 20 turns (configurable in `app_agents/excel_agent.py`):

```python
return await Runner.run(excel_agent, msg, max_turns=20)
```

## 🌐 Deployment

### Hugging Face Spaces

1. Create a new Space on Hugging Face
2. Choose "Gradio" as the SDK
3. Upload all project files
4. **Do not add an `OPENAI_API_KEY` secret**: each visitor enters their own key in the interface, so the Space holds nothing to steal and you pay nothing for other people's use
5. The Space will automatically deploy

### Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t excel-analyst-agent .
docker run -p 7860:7860 -e OPENAI_API_KEY=your-key excel-analyst-agent
```

## 🔒 Security

The model writes Python and the app runs it, so the code is treated as untrusted. It never runs inside the app's
own process. Layers, from the outside in:

1. **AST validation** (friendly first filter, not the boundary): rejects `eval`, `exec`, `open`, `os`, `sys`,
   `subprocess`, dunder access and imports other than pandas, numpy, matplotlib and seaborn, with a clear message
   the agent can react to.
2. **Separate process** (`app_agents/tools/sandbox_worker.py`), started with:
   - an **empty environment**, so no API key or other secret exists in the process;
   - a **throw-away working folder** holding a private copy of the uploaded file (the original is never touched);
   - **resource limits**: CPU time, memory (4 GB by default) and maximum file size;
   - a **hard timeout** that kills the whole process group.
3. **Audit hook inside that process**: refuses network, subprocess, `exec` and `fork` calls, allows writing only in
   the work folder, and allows reading only the work folder and the Python installation.
4. **Restricted builtins and imports** for the generated code itself.

All of this is covered by tests that start the real worker: reading the environment, reading `/etc/hostname`, running a
shell command, writing outside the work folder, reaching the network, an infinite loop and a memory bomb are all stopped.
Legitimate CSV, Excel, matplotlib and seaborn analyses run unchanged.

**API keys.** Each request builds its own OpenAI client from the key in the interface; the key is never written to
`os.environ`, which every session shares, and never logged. Agent tracing is disabled so prompts and data are not
uploaded to OpenAI's trace service.

**What this is not.** An in-process audit hook is strong defence in depth but not a hard boundary: a determined attacker
with low-level (`ctypes`) tricks may still get out. For a public, multi-user deployment, run the app in a container with no
secrets, no outbound network and a read-only filesystem, so the worker's isolation is the second line, not the only one.

## 📦 Dependencies

- `gradio` - Web interface
- `openai-agents` - OpenAI Agents SDK with MCP support
- `fastmcp` - FastMCP for building MCP servers
- `pandas>=2.0.0` - Data manipulation
- `numpy>=1.24.0` - Numerical computing
- `openpyxl>=3.1.0` - Excel file support
- `matplotlib>=3.7.0` - Plotting
- `seaborn>=0.12.0` - Statistical visualizations
- `duckduckgo-search>=4.0.0` - Web search (no API key required)
- `python-dotenv>=1.0.0` - Environment management

**Note**: RestrictedPython is NOT used. We use standard Python `exec()` with AST validation for better compatibility and functionality.

## 🔧 Technical Details

### Why not RestrictedPython?

It was considered and dropped: it blocks legitimate pandas/numpy operations, needs configuration for each library
function and handles standard imports poorly. Process isolation lets the analysis code use the libraries normally
while the surrounding limits do the protecting.

### Why a process and not a thread

The first version ran `exec()` in a thread of the app. A Python thread cannot be killed, so the timeout did not stop an
infinite loop (the call waited for it), and the code shared the app's memory, environment and files. A separate process
can be killed, limited and given nothing to steal.

### Execution Flow

```
User Query → Gradio UI → MasterAgent
                           ↓
                 Try ExcelAnalysisAgent
                           ↓
             Call MCP Tool: execute_python_code
                           ↓
             MCP Server → PythonSandboxTool
                           ↓
                     Parse / Validate / Execute
                           ↓
                 Capture stdout/dataframes/plots
                           ↓
                 If insufficient or error →
                           ↓
                 MasterAgent calls WebSearchAgent
                           ↓
                Get docs/examples from search_web
                           ↓
         MasterAgent augments prompt and retries Excel
                           ↓
                     Return results to UI
```

## 🧪 Tests

```bash
pip install -r requirements.txt pytest
pytest
```

The sandbox tests start the real worker process: normal analyses must work, escape attempts must fail. The agent
tests check that API keys stay out of the shared environment. CI runs lint and tests on every push.

## ⚠️ Limitations

- The sandbox is defence in depth, not a guarantee; see [Security](#-security) for what to add in public deployments.
- Linux/macOS only: the worker relies on POSIX resource limits and process groups.
- Only pandas, numpy, matplotlib and seaborn are available to the generated code.
- Results depend on the model writing correct code; the answer is the model's, so check important numbers.

## 🐛 Troubleshooting

### "OPENAI_API_KEY not found"
- Ensure you've set the environment variable or entered it in the interface
- Check your `.env` file is in the project root

### "Code execution failed"
- Check the error message for details
- Ensure your file is a valid Excel or CSV file
- Try rephrasing your query to be more specific

### "Timeout error"
- Your query might be too complex
- Try breaking it into smaller requests
- Increase timeout in `python_tool.py`

### Import errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Use a fresh virtual environment if issues persist

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

For issues and questions, please open an issue on the GitHub repository.

---

**Built with ❤️ using OpenAI Agents SDK and Gradio**
