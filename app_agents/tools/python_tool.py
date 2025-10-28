"""
Python Sandbox Tool for safe code execution
Uses standard exec() with AST validation and namespace control
"""

import io
import sys
import base64
import logging
import ast
from typing import Dict, Any, Optional, Set
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when code execution times out"""
    pass


class CodeValidator(ast.NodeVisitor):
    """
    AST validator to block dangerous operations
    """
    
    # Dangerous functions/modules to block
    BLOCKED_NAMES: Set[str] = {
        'eval', 'exec', 'compile',
        'open', 'file', 'input', 'raw_input',
        'execfile', 'reload', 'breakpoint',
        'exit', 'quit', 'help',
    }
    
    # Dangerous modules to block
    BLOCKED_MODULES: Set[str] = {
        'os', 'sys', 'subprocess', 'socket', 'urllib',
        'requests', 'http', 'ftplib', 'telnetlib',
        'pickle', 'shelve', 'marshal', 'importlib',
    }
    
    def __init__(self):
        self.errors = []
    
    def visit_Import(self, node):
        """Check import statements"""
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if module_name in self.BLOCKED_MODULES:
                self.errors.append(f"Import of '{alias.name}' is not allowed")
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Check from-import statements"""
        if node.module:
            module_name = node.module.split('.')[0]
            if module_name in self.BLOCKED_MODULES:
                self.errors.append(f"Import from '{node.module}' is not allowed")
        self.generic_visit(node)
    
    def visit_Name(self, node):
        """Check for blocked names"""
        if node.id in self.BLOCKED_NAMES:
            self.errors.append(f"Use of '{node.id}' is not allowed")
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        """Check for dangerous attribute access"""
        # Block access to __builtins__, __globals__, etc.
        if isinstance(node.attr, str) and node.attr.startswith('__') and node.attr.endswith('__'):
            if node.attr not in {'__init__', '__str__', '__repr__'}:
                self.errors.append(f"Access to '{node.attr}' is not allowed")
        self.generic_visit(node)


class PythonSandboxTool:
    """
    Safe Python code execution sandbox with restricted access
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the sandbox tool
        
        Args:
            timeout: Maximum execution time in seconds (default: 30)
        """
        self.timeout = timeout
        self.allowed_modules = {
            'pd': pd,
            'pandas': pd,
            'np': np,
            'numpy': np,
            'plt': plt,
            'matplotlib': matplotlib,
            'sns': sns,
            'seaborn': sns,
        }
    
    def _safe_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        """
        Custom import function that uses pre-loaded modules
        
        Args:
            name: Module name to import
            globals: Global namespace (ignored)
            locals: Local namespace (ignored)
            fromlist: Names to import from module
            level: Relative import level
            
        Returns:
            Pre-loaded module object if allowed
            
        Raises:
            ImportError: If module is not allowed
        """
        # Map import names to allowed modules
        allowed = {
            'pandas': pd,
            'numpy': np,
            'matplotlib': matplotlib,
            'seaborn': sns,
        }
        
        # Return pre-loaded module if allowed
        if name in allowed:
            return allowed[name]
        
        # Handle matplotlib sub-modules (e.g., matplotlib.pyplot)
        if name.startswith('matplotlib.'):
            # Return the base matplotlib module
            # Python will then access the sub-module as an attribute
            return matplotlib
        
        # Check if it's a blocked module
        if name.split('.')[0] in CodeValidator.BLOCKED_MODULES:
            raise ImportError(f"Import of '{name}' is not allowed for security reasons")
        
        # For any other module not specifically allowed, raise error
        raise ImportError(f"Cannot import '{name}'. Only pandas, numpy, matplotlib, and seaborn are allowed.")
    
    def _create_safe_globals(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a safe globals dictionary with whitelisted modules
        
        Args:
            file_path: Path to the uploaded Excel/CSV file
            
        Returns:
            Dictionary of safe globals
        """
        # Create a limited builtins dictionary
        safe_builtins = {
            'print': print,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            'sorted': sorted,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'isinstance': isinstance,
            'type': type,
            'hasattr': hasattr,
            'getattr': getattr,
            'setattr': setattr,
            'True': True,
            'False': False,
            'None': None,
            '__import__': self._safe_import,  # Enable safe imports
            # Exception types (necessary for try/except blocks)
            'Exception': Exception,
            'ValueError': ValueError,
            'TypeError': TypeError,
            'KeyError': KeyError,
            'IndexError': IndexError,
            'AttributeError': AttributeError,
            'RuntimeError': RuntimeError,
            'ImportError': ImportError,
            'ZeroDivisionError': ZeroDivisionError,
            # Additional useful builtins
            'locals': locals,
            'globals': lambda: safe_builtins,  # Return safe version
            'dir': dir,
            'any': any,
            'all': all,
        }
        
        safe_dict = {
            '__builtins__': safe_builtins,
            '__name__': 'sandbox',
        }
        
        # Add allowed modules (also available directly without import)
        safe_dict.update(self.allowed_modules)
        
        # Add file path if provided
        if file_path:
            safe_dict['file_path'] = file_path
            
        return safe_dict
    
    def _execute_code(self, byte_code, safe_dict, stdout_capture, stderr_capture) -> None:
        """
        Helper method to execute code (can be run in a separate thread)
        
        Args:
            byte_code: Compiled code object
            safe_dict: Safe globals dictionary
            stdout_capture: StringIO for capturing stdout
            stderr_capture: StringIO for capturing stderr
        """
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(byte_code, safe_dict)
    
    def execute(self, code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute Python code in a restricted environment
        
        Args:
            code: Python code to execute
            file_path: Path to the uploaded Excel/CSV file
            
        Returns:
            Dictionary containing:
                - success: bool
                - output: str (stdout)
                - error: str (if any)
                - dataframe: dict (if df variable exists)
                - images: list of base64 encoded images
        """
        result = {
            'success': False,
            'output': '',
            'error': '',
            'dataframe': None,
            'images': []
        }
        
        try:
            # Validate code using AST
            try:
                tree = ast.parse(code, filename='<user_code>', mode='exec')
            except SyntaxError as e:
                result['error'] = f"Syntax error: {str(e)}"
                logger.error(f"Syntax error: {str(e)}")
                return result
            
            # Check for dangerous operations
            validator = CodeValidator()
            validator.visit(tree)
            
            if validator.errors:
                result['error'] = f"Security validation failed:\n" + "\n".join(validator.errors)
                logger.error(f"Validation errors: {validator.errors}")
                return result
            
            # Configure pandas display to avoid truncated columns/rows in printed output
            try:
                pd.set_option('display.max_columns', None)
                pd.set_option('display.width', 2000)
                pd.set_option('display.max_colwidth', None)
                pd.set_option('display.expand_frame_repr', False)
            except Exception:
                pass

            # Compile the validated code
            byte_code = compile(tree, filename='<user_code>', mode='exec')
            
            # Create safe execution environment
            safe_dict = self._create_safe_globals(file_path)
            
            # Capture stdout and stderr
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            # Execute with timeout using ThreadPoolExecutor
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self._execute_code,
                        byte_code,
                        safe_dict,
                        stdout_capture,
                        stderr_capture
                    )
                    # Wait for completion with timeout
                    future.result(timeout=self.timeout)
                
                # Get stdout
                result['output'] = stdout_capture.getvalue()
                
                # Check for dataframe in the namespace
                if 'df' in safe_dict and isinstance(safe_dict['df'], pd.DataFrame):
                    # Convert dataframe to dict and make it JSON-safe
                    records = safe_dict['df'].head(5).to_dict('records')
                    result['dataframe'] = self._make_json_safe_records(records)
                elif 'result' in safe_dict and isinstance(safe_dict['result'], pd.DataFrame):
                    records = safe_dict['result'].head(5).to_dict('records')
                    result['dataframe'] = self._make_json_safe_records(records)
                
                # Capture matplotlib figures
                figures = [plt.figure(i) for i in plt.get_fignums()]
                for fig in figures:
                    buf = io.BytesIO()
                    fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
                    buf.seek(0)
                    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
                    result['images'].append(img_base64)
                    buf.close()
                
                # Close all figures to free memory
                plt.close('all')
                
                result['success'] = True
                logger.info("Code executed successfully")
                
            except FuturesTimeoutError:
                result['error'] = f"Execution timeout: Code took longer than {self.timeout} seconds"
                logger.error(f"Timeout: Code execution exceeded {self.timeout} seconds")
            except Exception as e:
                result['error'] = f"Runtime error: {str(e)}"
                logger.error(f"Runtime error: {str(e)}")
                
                # Include stderr if available
                stderr_output = stderr_capture.getvalue()
                if stderr_output:
                    result['error'] += f"\n{stderr_output}"
        
        except Exception as e:
            result['error'] = f"Sandbox error: {str(e)}"
            logger.error(f"Sandbox error: {str(e)}")

        logger.info(f"Result: {result}")
        
        return result

    def _make_json_safe_records(self, records):
        """
        Convert a list of dict records into JSON-serializable values:
        - pandas.Timestamp -> ISO string
        - numpy types -> native Python
        - NaN -> None
        """
        import math
        from datetime import datetime

        def to_safe(value):
            if isinstance(value, pd.Timestamp):
                return value.isoformat()
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, np.generic):
                # numpy scalar -> native python
                py = value.item()
                if isinstance(py, float) and (math.isnan(py) or py == float('inf') or py == float('-inf')):
                    return None
                return py
            if isinstance(value, float):
                if math.isnan(value) or value == float('inf') or value == float('-inf'):
                    return None
                return value
            return value

        safe_records = []
        for rec in records or []:
            safe_rec = {k: to_safe(v) for k, v in rec.items()}
            safe_records.append(safe_rec)
        return safe_records
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for OpenAI function calling
        
        Returns:
            Tool definition dictionary
        """
        return {
            "type": "function",
            "function": {
                "name": "execute_python_code",
                "description": "Execute Python code to analyze Excel/CSV data. Use pandas (pd), numpy (np), matplotlib (plt), and seaborn (sns). The uploaded file path is available as 'file_path' variable. Store results in 'df' or 'result' variable to return dataframes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute. Must use pandas to read the file (e.g., pd.read_excel(file_path) or pd.read_csv(file_path)). Store final dataframe in 'df' or 'result' variable."
                        }
                    },
                    "required": ["code"]
                }
            }
        }



