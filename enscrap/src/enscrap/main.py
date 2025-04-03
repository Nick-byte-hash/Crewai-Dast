import os
from dotenv import load_dotenv
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import litellm for configuration
import litellm

from .crew import Enscrap
from .tools.web_scraping_tool import WebScrapingTool    
from .tools.supabase_tool import SupabaseTool

load_dotenv()
model = os.getenv("MODEL", "gpt-4o-mini")  # Changed default to gpt-4o-mini
openai_api_key = os.getenv("OPENAI_API_KEY")
supabase_url = os.getenv("SUPABASE_URL")
supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")

# Set up litellm configuration
litellm.api_key = openai_api_key
# Configure provider mapping using the correct method
litellm.model_list = [
    {
        "model_name": "gpt-4o-turbo",
        "litellm_provider": "openai",
    },
    {
        "model_name": "gpt-4o-mini",
        "litellm_provider": "openai",
    },
    {
        "model_name": "gpt-4",
        "litellm_provider": "openai",
    },
    {
        "model_name": "gpt-3.5-turbo",
        "litellm_provider": "openai",
    }
]

def initialize_database(sample_data_file: str = None) -> Dict[str, Any]:
    supabase_tool = SupabaseTool()
    return supabase_tool.initialize_database(sample_data_file)

def run(batch_size: int = 2, output_file: str = None) -> List[Any]:
    """
    Run the school data enrichment process with optimized batch size to avoid context window limits.
    
    Args:
        batch_size: Number of schools to process in each batch (decreased from 5 to 2)
        output_file: Optional file to save results
        
    Returns:
        List of results from each batch
    """
    try:
        init_result = initialize_database()
        if "error" in init_result:
            raise Exception(f"Database initialization failed: {init_result['error']}")

        enscrap = Enscrap()
        
        # Process schools in smaller batches
        supabase_tool = SupabaseTool()
        all_schools = supabase_tool.get_schools_needing_enrichment()
        
        max_schools = 10  # Explicitly limit to 10 schools
        if len(all_schools) > max_schools:
            logger.warning(f"Limiting processing to {max_schools} schools to avoid token limits")
            all_schools = all_schools[:max_schools]
        
        results = []

        for i in range(0, len(all_schools), batch_size):
            batch = all_schools[i:i + batch_size]
            
            # Create minimal input data with only essential information
            input_data = {
                "input_data": {
                    "topic": "school data enrichment",
                    "current_year": str(datetime.now().year),
                    "school_sources": [
                        {"name": "GreatSchools", "base_url": "https://www.greatschools.org"},
                        {"name": "Niche", "base_url": "https://www.niche.com/k12"}
                        # Removed SchoolDigger to reduce token count
                    ],
                    "schools_needing_enrichment": batch
                }
            }
            
            logger.info(f"Processing batch {i // batch_size + 1} with {len(batch)} schools")
            
            try:
                # Create a new crew for each batch
                crew = enscrap.create_crew(input_data)
                result = crew.kickoff()
                results.append(result)
                
                # Important: Add a clear memory call if available in your version of CrewAI
                # crew.clear_memory()  # Uncomment if available in your CrewAI version
                
                logger.info(f"Successfully processed batch {i // batch_size + 1}")
            except Exception as batch_error:
                logger.error(f"Error processing batch {i // batch_size + 1}: {batch_error}")
                # Continue with next batch instead of failing entirely
                continue

        # Only fetch a limited number of schools for the final report to avoid token issues
        all_schools_sample = supabase_tool.get_all_schools()[:20]  # Limit to 20 schools
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump({"results_summary": f"Processed {len(results)} batches", 
                           "schools_sample": all_schools_sample[:5]}, f, indent=2)

        return results

    except Exception as e:
        logger.error(f"Error during run: {e}")
        raise

def test_db() -> None:
    supabase_tool = SupabaseTool()
    result = supabase_tool.test_connection()
    print("Test connection result:", json.dumps(result, indent=2))
    if result["data"] is None:
        print("No data found. Initializing database...")
        init_result = initialize_database()
        print("Initialization result:", json.dumps(init_result, indent=2))
        result = supabase_tool.test_connection()
        print("Test connection result after initialization:", json.dumps(result, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the school data enrichment crew')
    parser.add_argument('command', choices=['run', 'test_db'], help='Command to run')
    parser.add_argument('--output_file', type=str, help='File to save results to')
    parser.add_argument('--batch_size', type=int, default=2, help='Number of schools per batch')
    args = parser.parse_args()

    if args.command == "run":
        run(batch_size=args.batch_size, output_file=args.output_file)
    elif args.command == "test_db":
        test_db()