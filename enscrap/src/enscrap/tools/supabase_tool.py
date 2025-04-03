from typing import Any, Dict, List, Optional, ClassVar
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import os
from supabase import create_client, Client
import logging
import json
from datetime import datetime
import uuid

class School(BaseModel):
    school_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique school identifier")
    school_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[int] = None
    county: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    lea_id: Optional[str] = None
    urban_area_classification: str = Field(default="Unknown", description="Urban area classification")
    school_type: str = Field(default="Unknown", description="Type of school")
    religious_orientation: Optional[str] = None
    school_network: Optional[str] = None
    catholic_diocese: Optional[str] = None
    days_in_school_year: Optional[float] = None
    total_student_enrollment: Optional[int] = None
    dast_pipeline_stage: Optional[str] = None
    source: Optional[str] = None
    edlink_id: Optional[str] = None
    twenty_id: Optional[str] = None
    nces_id: Optional[str] = None
    state_id: Optional[str] = None
    school_association: Optional[List[dict]] = None
    target_school: bool = Field(default=False, description="Whether this is a target school")
    lcms_district: Optional[str] = None

class SupabaseTool(BaseTool):
    name: str = "supabase_tool"
    description: str = "Fetch and update school data in Supabase"

    _supabase: ClassVar[Optional[Client]] = None
    _logger: ClassVar[logging.Logger] = None

    def __init__(self):
        super().__init__()
        if not SupabaseTool._logger:
            logging.basicConfig(
                filename=f'scraping_output_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
            SupabaseTool._logger = logging.getLogger(__name__)

        if not SupabaseTool._supabase:
            try:
                url = os.environ.get("SUPABASE_URL")
                key = os.environ.get("SUPABASE_ANON_KEY")
                if not url or not key:
                    raise ValueError("Supabase URL and key must be set in environment variables")
                SupabaseTool._supabase = create_client(url, key)
                SupabaseTool._logger.info("Connected to Supabase")
            except Exception as e:
                SupabaseTool._logger.error(f"Failed to connect to Supabase: {e}")
                raise

    def initialize_database(self, sample_data_file: Optional[str] = None) -> Dict[str, Any]:
        result = self._run("schools", "select")
        if isinstance(result, list) and len(result) > 0:
            return {"status": "Database already initialized", "school_count": len(result)}

        sample_schools = [
            {
                "school_id": str(uuid.uuid4()),
                "school_name": "Lowell High School",
                "address": "1101 Eucalyptus Dr",
                "city": "San Francisco",
                "zip": 94132,
                "county": "San Francisco County",
                "phone": "(415) 759-2730",
                "latitude": 37.7319,
                "longitude": -122.4754,
                "urban_area_classification": "Urban",
                "school_type": "Public",
                "total_student_enrollment": 2650,
                "source": "https://www.greatschools.org/california/san-francisco/6301-Lowell-High-School/",
                "target_school": True
            }
        ] if not sample_data_file else json.load(open(sample_data_file, 'r'))

        result = self._run("schools", "insert", sample_schools)
        return {"status": "Database initialized", "school_count": len(sample_schools), "result": result}

    def _run(self, table: str, query_type: str = "select", conditions: Optional[Dict[str, Any]] = None) -> Any:
        query = SupabaseTool._supabase.table(table)
        try:
            if query_type == "select":
                query = query.select("*")
                if conditions:
                    for key, value in conditions.items():
                        if key == "limit":
                            query = query.limit(value)
                        else:
                            query = query.eq(key, value)
                result = query.execute()
            elif query_type == "insert":
                result = query.insert(conditions).execute()
            elif query_type == "update":
                result = query.update(conditions["data"]).eq(**conditions["where"]).execute()
            elif query_type == "delete":
                result = query.delete().eq(**conditions).execute()
            else:
                raise ValueError(f"Unsupported query type: {query_type}")

            if hasattr(result, 'data'):
                return result.data
            return {"error": str(result.error)} if hasattr(result, 'error') else result
        except Exception as e:
            SupabaseTool._logger.error(f"Error in {query_type} query: {e}")
            return {"error": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        result = self._run("schools", "select", {"limit": 1})
        if isinstance(result, list) and len(result) > 0:
            return {"status": "success", "data": result[0]}
        return {"status": "success", "data": None, "message": "No data found"}

    def get_schools_needing_enrichment(self, limit: int = 5, minimal: bool = False) -> List[Dict[str, Any]]:
        schools = self._run("schools", "select", {"limit": limit})
        required_fields = School.model_fields.keys()
        if minimal:
            return [
                {
                    "school_id": school["school_id"],
                    "school_name": school["school_name"],
                    "missing_fields": [f for f in required_fields if school.get(f) is None or school.get(f) == "Unknown"]
                }
                for school in schools if any(school.get(f) is None or school.get(f) == "Unknown" for f in required_fields)
            ]
        return [
            {**school, "missing_fields": [f for f in required_fields if school.get(f) is None or school.get(f) == "Unknown"]}
            for school in schools if any(school.get(f) is None or school.get(f) == "Unknown" for f in required_fields)
        ]

    def update_school(self, school_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._run("schools", "update", {"where": {"school_id": school_id}, "data": data})

    def get_all_schools(self) -> List[Dict[str, Any]]:
        return self._run("schools", "select")