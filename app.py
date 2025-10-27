"""
Excel Analyst Agent - Gradio Application
Main entry point for the web interface
"""

import os
import logging
import base64
from io import BytesIO
from typing import Optional, Tuple, List
import gradio as gr
import pandas as pd
from PIL import Image
from dotenv import load_dotenv
from agents.orchestrator import ExcelOrchestratorAgent

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not found in environment variables")


def process_analysis(
    file: Optional[gr.File],
    query: str,
    api_key: Optional[str] = None
) -> Tuple[str, Optional[pd.DataFrame], Optional[List[Image.Image]]]:
    """
    Process the user's file and query
    
    Args:
        file: Uploaded file object
        query: User's natural language query
        api_key: Optional API key override
        
    Returns:
        Tuple of (output_text, dataframe, images)
    """
    try:
        # Validate inputs
        if not file:
            return "❌ Please upload an Excel (.xlsx) or CSV (.csv) file.", None, None
        
        if not query or query.strip() == "":
            return "❌ Please enter a query describing what you want to analyze.", None, None
        
        # Get API key
        used_api_key = api_key if api_key else OPENAI_API_KEY
        if not used_api_key:
            return "❌ Please provide an OpenAI API key either in the interface or as an environment variable (OPENAI_API_KEY).", None, None
        
        # Get file path
        file_path = file.name
        logger.info(f"Processing file: {file_path}")
        logger.info(f"User query: {query}")
        
        # Validate file extension
        if not (file_path.endswith('.xlsx') or file_path.endswith('.csv')):
            return "❌ Please upload a valid Excel (.xlsx) or CSV (.csv) file.", None, None
        
        # Initialize the orchestrator agent
        logger.info("Initializing Excel Orchestrator Agent...")
        agent = ExcelOrchestratorAgent(api_key=used_api_key, model="gpt-4o-mini")
        
        # Analyze the file
        logger.info("Starting analysis...")
        result = agent.analyze(user_query=query, file_path=file_path)
        
        if not result['success']:
            error_msg = result.get('error', 'Unknown error occurred')
            return f"❌ Analysis failed:\n\n{error_msg}", None, None
        
        # Format output
        output_parts = ["✅ **Analysis Complete**\n"]
        
        # Add text output
        if result['output']:
            output_parts.append("### Results:\n")
            output_parts.append(result['output'])
            output_parts.append("\n")
        
        # Add code if available
        if result['code']:
            output_parts.append("\n### Generated Code:\n")
            output_parts.append("```python\n")
            output_parts.append(result['code'])
            output_parts.append("\n```\n")
        
        output_text = "\n".join(output_parts)
        
        # Prepare dataframe
        df_output = None
        if result['dataframe']:
            try:
                df_output = pd.DataFrame(result['dataframe'])
                logger.info(f"Dataframe prepared: {len(df_output)} rows")
            except Exception as e:
                logger.error(f"Error preparing dataframe: {e}")
                output_text += f"\n\n⚠️ Note: Could not display dataframe - {str(e)}"
        
        # Prepare images
        images_output = None
        if result['images']:
            try:
                images_output = []
                for img_base64 in result['images']:
                    img_data = base64.b64decode(img_base64)
                    img = Image.open(BytesIO(img_data))
                    images_output.append(img)
                logger.info(f"Prepared {len(images_output)} images")
            except Exception as e:
                logger.error(f"Error preparing images: {e}")
                output_text += f"\n\n⚠️ Note: Could not display images - {str(e)}"
        
        return output_text, df_output, images_output
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}", None, None


def create_interface() -> gr.Blocks:
    """
    Create the Gradio interface
    
    Returns:
        Gradio Blocks interface
    """
    with gr.Blocks(
        title="Excel Analyst Agent",
        theme=gr.themes.Soft()
    ) as interface:
        
        gr.Markdown(
            """
            # 📊 Excel Analyst Agent
            
            **Intelligent data analysis powered by AI**
            
            Upload your Excel or CSV file and describe what you want to analyze in plain English.
            The agent will generate and execute Python code to fulfill your request.
            
            ### Features:
            - 📈 Data analysis and statistics
            - 📊 Automatic visualizations
            - 🔍 Natural language queries
            - 🤖 Powered by OpenAI GPT-4o-mini
            
            ### Example queries:
            - *"Show me the average sales per region and create a bar chart"*
            - *"Find the top 10 customers by revenue"*
            - *"Calculate monthly trends and visualize them"*
            - *"Identify outliers in the price column"*
            """
        )
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Input")
                
                file_input = gr.File(
                    label="Upload Excel or CSV file",
                    file_types=[".xlsx", ".csv"],
                    type="filepath"
                )
                
                query_input = gr.Textbox(
                    label="What would you like to analyze?",
                    placeholder="E.g., Show me the average sales per region and create a bar chart",
                    lines=3
                )
                
                api_key_input = gr.Textbox(
                    label="OpenAI API Key (optional if set in environment)",
                    placeholder="sk-...",
                    type="password"
                )
                
                with gr.Row():
                    submit_btn = gr.Button("🚀 Analyze", variant="primary", size="lg")
                    clear_btn = gr.ClearButton(
                        components=[file_input, query_input, api_key_input],
                        value="🔄 Clear"
                    )
            
            with gr.Column(scale=2):
                gr.Markdown("### 📊 Results")
                
                output_text = gr.Markdown(
                    label="Analysis Output",
                    value="Results will appear here..."
                )
                
                output_dataframe = gr.Dataframe(
                    label="Data Preview",
                    interactive=False,
                    wrap=True
                )
                
                output_images = gr.Gallery(
                    label="Visualizations",
                    columns=2,
                    height="auto"
                )
        
        gr.Markdown(
            """
            ---
            ### 💡 Tips:
            - Be specific in your queries for better results
            - The agent can create multiple visualizations in one request
            - If something doesn't work, try rephrasing your query
            - All processing is done securely in a sandboxed environment
            
            ### 🔒 Privacy:
            - Your files are processed temporarily and not stored
            - Code execution is sandboxed without internet access
            - Only you and OpenAI's API see your data
            """
        )
        
        # Connect the submit button
        submit_btn.click(
            fn=process_analysis,
            inputs=[file_input, query_input, api_key_input],
            outputs=[output_text, output_dataframe, output_images]
        )
        
        # Also allow Enter key to submit
        query_input.submit(
            fn=process_analysis,
            inputs=[file_input, query_input, api_key_input],
            outputs=[output_text, output_dataframe, output_images]
        )
    
    return interface


def main():
    """
    Main entry point
    """
    logger.info("Starting Excel Analyst Agent application...")
    
    # Create and launch the interface
    interface = create_interface()
    
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )


if __name__ == "__main__":
    main()


