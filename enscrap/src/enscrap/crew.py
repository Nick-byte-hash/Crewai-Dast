import os
from typing import Dict, Any, List
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from pydantic import BaseModel, Field
import logging
import json

# Add these imports
from litellm import completion
from litellm.utils import get_token_count
import litellm

# Add the imports for your tools
from .tools.web_scraping_tool import WebScrapingTool
from .tools.supabase_tool import SupabaseTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.api_key = os.getenv("OPENAI_API_KEY")
# Update provider configuration using the proper litellm method
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

class ScrapingAgentData(BaseModel):
    topic: str = Field(description="Topic to research")
    current_year: str = Field(description="Current year")
    school_sources: List[Dict[str, str]] = Field(description="List of school data sources")
    schools_needing_enrichment: List[Dict[str, Any]] = Field(default_factory=list, description="Schools to enrich")

class ScrapingAgentInput(BaseModel):
    input_data: ScrapingAgentData = Field(description="Input data for the scraping agent")

@CrewBase
class Enscrap:
    def __init__(self):
        # Other initialization code...
        self.web_scraping_tool = WebScrapingTool()
        self.supabase_tool = SupabaseTool()
        
        # Set a more conservative token limit for agents
        self.max_tokens_per_agent = 30000  # Adjust based on your needs
        
    # Updated method to check token count with correct parameters
    def _prepare_school_data(self, schools: List[Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
        """Prepare school data by simplifying and limiting to fit within token budget."""
        simplified_schools = []
        total_tokens = 0
        
        # First, simplify each school to only include essential fields
        for school in schools:
            # Create a simplified version with only essential fields
            simplified_school = {
                "school_id": school["school_id"],
                "school_name": school.get("school_name", "Unknown School"),
                "missing_fields": school.get("missing_fields", [])[:10]  # Limit missing fields
            }
            
            # Add a few more important fields if they exist
            for field in ["address", "city", "zip", "school_type"]:
                if field in school and school[field]:
                    simplified_school[field] = school[field]
            
            # Estimate token count - use safe parameters for token counting
            school_json = json.dumps(simplified_school)
            try:
                # Updated to use messages parameter correctly
                school_tokens = get_token_count(
                    model="gpt-4", 
                    messages=[{"role": "user", "content": school_json}]
                )
            except Exception as e:
                # Fallback to a rough estimation if token counting fails
                logger.warning(f"Token count failed, using rough estimation: {e}")
                school_tokens = len(school_json) // 4  # Rough estimate
            
            # Add school if it fits within budget
            if total_tokens + school_tokens <= max_tokens:
                simplified_schools.append(simplified_school)
                total_tokens += school_tokens
            else:
                logger.warning(f"Skipping school {simplified_school['school_name']} to stay within token limits")
                break
                
        logger.info(f"Prepared {len(simplified_schools)} schools using {total_tokens} tokens")
        return simplified_schools

    @agent
    def researcher(self) -> Agent:
        return Agent(
            role="Researcher",
            goal="Identify schools needing data enrichment",
            backstory="Expert in educational data analysis focusing on key missing fields.",
            tools=[self.supabase_tool],
            verbose=True,
            # Add LLM configuration with reduced context and specify provider
            llm_config={
                "config_list": [{"model": "openai/gpt-4o-mini"}],  # Using the provider/model format
                "temperature": 0.7,
                "max_tokens": 4000  # Limit response length
            }
        )

    @agent
    def scraping_agent(self) -> Agent:
        return Agent(
            role="Web Scraper",
            goal="Enrich school data from web sources for critical fields only.",
            backstory="Specialist in efficient web data extraction",
            tools=[self.web_scraping_tool, self.supabase_tool],
            args_schema=ScrapingAgentInput,
            verbose=True,
            # Add LLM configuration with reduced context and specify provider
            llm_config={
                "config_list": [{"model": "openai/gpt-4o-mini"}],  # Using the provider/model format
                "temperature": 0.7,
                "max_tokens": 4000  # Limit response length 
            }
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            role="Analyst",
            goal="Generate concise reports on enriched school data",
            backstory="Data analysis expert focused on essential metrics",
            tools=[self.supabase_tool],
            verbose=True,
            # Add LLM configuration with reduced context and specify provider
            llm_config={
                "config_list": [{"model": "openai/gpt-4o-mini"}],  # Using the provider/model format
                "temperature": 0.7,
                "max_tokens": 4000  # Limit response length
            }
        )

    @task
    def research_task(self) -> Task:
        return Task(
            description="Identify schools that need data enrichment",
            agent=self.researcher(),
            expected_output="A list of schools that need data enrichment with missing fields"
        )

    @task
    def scraping_task(self) -> Task:
        return Task(
            description="Scrape data for schools from web sources",
            agent=self.scraping_agent(),
            expected_output="Enriched school data from web sources"
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            description="Generate report on enriched school data",
            agent=self.reporting_analyst(),
            expected_output="Report on enriched school data with key metrics"
        )

    def create_crew(self, input_data: Dict[str, Any]) -> Crew:
        """Create a crew with the given input data focused on the current batch of schools."""
        # Process the schools to fit within token limits
        if "input_data" in input_data and "schools_needing_enrichment" in input_data["input_data"]:
            schools = input_data["input_data"]["schools_needing_enrichment"]
            input_data["input_data"]["schools_needing_enrichment"] = self._prepare_school_data(
                schools, 
                max_tokens=self.max_tokens_per_agent
            )
        
        # Create a new crew with the optimized input data
        return Crew(
            agents=[self.researcher(), self.scraping_agent(), self.reporting_analyst()],
            tasks=[self.research_task(), self.scraping_task(), self.reporting_task()],
            process=Process.sequential,
            verbose=True,
            inputs=input_data,  # Pass the optimized input data
            # Add crew-level LLM configuration with provider specified
            llm_config={
                "config_list": [{"model": "openai/gpt-4o-mini"}],  # Using the provider/model format
                "temperature": 0.7,
                "request_timeout": 120  # Longer timeout for complex tasks
            }
        )