# 📊 Excel Analyst Agent

An intelligent Excel data analysis application powered by AI. Upload your Excel or CSV files and analyze them using natural language queries in English.

## 🌟 Features

- **Natural Language Queries**: Describe what you want in plain English
- **Automatic Code Generation**: AI generates Python code to fulfill your requests
- **Data Analysis**: Perform complex data manipulation and statistical analysis
- **Visualizations**: Automatic chart and graph generation
- **Multi-Agent System**: Orchestrator agent with web search capability
- **Secure Execution**: Sandboxed Python environment with restricted access
- **User-Friendly Interface**: Clean Gradio web interface

## 🏗️ Architecture

The application uses a multi-agent architecture built with OpenAI Agents SDK:

```
┌─────────────────────────────────────────────────────────────┐
│                      Gradio Interface                        │
│                  (File Upload + Query Input)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Excel Orchestrator Agent (Main)                 │
│  - Interprets natural language queries                       │
│  - Generates Python code for analysis                        │
│  - Coordinates tool execution                                │
│  - Returns formatted results                                 │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
            ▼                             ▼
┌───────────────────────┐    ┌──────────────────────────────┐
│  Python Sandbox Tool  │    │    WebSearch Agent           │
│  - AST Validation     │    │  - DuckDuckGo search         │
│  - Safe exec()        │    │  - Documentation lookup      │
│  - pandas/numpy       │    │  - Code examples             │
│  - matplotlib/seaborn │    │                              │
└───────────────────────┘    └──────────────────────────────┘
```

### Project Structure

```
excel-analyst-agent/
├── app.py                          # Gradio UI entry point
├── requirements.txt                # Python dependencies
├── README.md                       # This file
└── agents/
    ├── __init__.py
    ├── orchestrator.py             # Main Excel Analyst Agent
    ├── web_agent.py                # Web Search Support Agent
    └── tools/
        ├── __init__.py
        ├── python_tool.py          # Python Sandbox with AST validation
        └── web_search_tool.py      # DuckDuckGo search integration
```

### Components

1. **Excel Orchestrator Agent** (`agents/orchestrator.py`)
   - Main agent that interprets user queries
   - Generates Python code for data analysis
   - Uses OpenAI GPT-4o-mini model
   - Delegates to tools and sub-agents as needed

2. **WebSearch Agent** (`agents/web_agent.py`)
   - Support agent for finding documentation
   - Uses DuckDuckGo for web searches
   - Returns summarized, actionable information

3. **Python Sandbox Tool** (`agents/tools/python_tool.py`)
   - Secure code execution environment
   - AST (Abstract Syntax Tree) validation for security
   - Safe `exec()` with controlled namespace
   - Supports pandas, numpy, matplotlib, seaborn
   - 30-second timeout limit via ThreadPoolExecutor
   - Captures outputs, dataframes, and visualizations

4. **Web Search Tool** (`agents/tools/web_search_tool.py`)
   - DuckDuckGo integration
   - No API key required
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
agent = ExcelOrchestratorAgent(api_key=used_api_key, model="gpt-4o")
```

### Timeout Settings

Code execution timeout is set to 30 seconds by default. To change it, modify `agents/tools/python_tool.py`:

```python
self.python_tool = PythonSandboxTool(timeout=60)  # 60 seconds
```

## 🌐 Deployment

### Hugging Face Spaces

1. Create a new Space on Hugging Face
2. Choose "Gradio" as the SDK
3. Upload all project files
4. Add your `OPENAI_API_KEY` in the Space settings (Secrets)
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

The application implements multiple security layers:

### AST Validation (Pre-execution)
- Parses code before execution to detect dangerous operations
- Blocks: `eval`, `exec`, `compile`, `open`, `os`, `sys`, `subprocess`, etc.
- Allows only whitelisted imports: pandas, numpy, matplotlib, seaborn

### Controlled Namespace (Runtime)
- Limited `__builtins__` with only safe functions
- Custom `__import__` function for whitelisted modules only
- No access to system functions or file operations (except uploaded file)

### Execution Controls
- **Timeout Protection**: 30-second execution limit via ThreadPoolExecutor
- **File Access**: Limited to the uploaded file path only
- **Thread Isolation**: Code runs in separate thread for safety

### What is **BLOCKED**:
- ❌ File system operations (`open`, `file`)
- ❌ System commands (`os`, `sys`, `subprocess`)
- ❌ Network access (`socket`, `urllib`, `requests`)
- ❌ Dynamic code execution (`eval`, `exec`)
- ❌ Dangerous imports (`pickle`, `marshal`)

### What is **ALLOWED**:
- ✅ pandas, numpy for data manipulation
- ✅ matplotlib, seaborn for visualizations
- ✅ Reading the uploaded file (`pd.read_excel(file_path)`)
- ✅ Mathematical operations and statistics
- ✅ Print statements for output

## 📦 Dependencies

- `gradio` - Web interface
- `openai>=1.12.0` - OpenAI Agents SDK
- `pandas>=2.0.0` - Data manipulation
- `numpy>=1.24.0` - Numerical computing
- `openpyxl>=3.1.0` - Excel file support
- `matplotlib>=3.7.0` - Plotting
- `seaborn>=0.12.0` - Statistical visualizations
- `duckduckgo-search>=4.0.0` - Web search (no API key required)
- `python-dotenv>=1.0.0` - Environment management

**Note**: RestrictedPython is NOT used. We use standard Python `exec()` with AST validation for better compatibility and functionality.

## 🔧 Technical Details

### Why NOT RestrictedPython?

Initially, RestrictedPython was considered but abandoned because:
- Too restrictive for data analysis operations
- Blocks legitimate pandas/numpy operations
- Requires complex configuration for each library function
- Doesn't support standard import statements well

### Current Approach: AST Validation + Safe Namespace

**Security Model**:
1. **Parse code with `ast.parse()`** - Validates syntax
2. **Walk the AST tree** - Check for dangerous operations
3. **Compile if safe** - Standard Python `compile()`
4. **Execute in controlled namespace** - Limited builtins + whitelisted modules
5. **Timeout protection** - ThreadPoolExecutor with 30s limit

**Code Validator** (in `python_tool.py`):
```python
class CodeValidator(ast.NodeVisitor):
    # Blocks dangerous functions: eval, exec, open, os, sys, etc.
    # Blocks dangerous modules: subprocess, socket, pickle, etc.
    # Allows: pandas, numpy, matplotlib, seaborn imports
```

**Safe Import Handler**:
- Custom `__import__` function in namespace
- Maps import names to pre-loaded module objects
- `import pandas as pd` → returns pre-loaded pandas module
- `import matplotlib.pyplot as plt` → returns matplotlib.pyplot
- Blocks any non-whitelisted imports

### Execution Flow

```
User Query → OpenAI Agent → Python Code
                                ↓
                          AST Validation
                                ↓
                          Compile (if safe)
                                ↓
                    Execute in ThreadPoolExecutor
                                ↓
                  Capture: stdout, dataframes, plots
                                ↓
                        Return to Gradio UI
```

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
