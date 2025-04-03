from typing import Dict, Any, Optional, ClassVar, List, Tuple
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from urllib.parse import urljoin
from tenacity import retry, stop_after_attempt, wait_exponential

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebScrapingTool(BaseTool):
    name: str = "web_scraping_tool"
    description: str = (
        "Scrape school data from web pages using CSS selectors for all fields in the School schema"
    )

    # Default selectors for common fields across sources
    DEFAULT_SELECTORS: ClassVar[Dict[str, str]] = {
        "school_name": "h1.school-name, h1.name, .school-title",
        "address": ".school-address, .address, span[itemprop='streetAddress']",
        "city": ".school-city, .city, span[itemprop='addressLocality']",
        "zip": ".school-zip, .zip, span[itemprop='postalCode']",
        "county": ".school-county, .county",
        "phone": ".school-phone, .phone, .tel",
        "latitude": "meta[itemprop='latitude'], [data-latitude]",
        "longitude": "meta[itemprop='longitude'], [data-longitude]",
        "lea_id": ".lea-id, .district-id",
        "urban_area_classification": ".urban-classification, .locale",
        "school_type": ".school-type, .type, .category",
        "religious_orientation": ".religious-orientation, .faith",
        "school_network": ".network, .affiliation",
        "catholic_diocese": ".diocese, .catholic-diocese",
        "days_in_school_year": ".school-days, .calendar-days",
        "total_student_enrollment": ".enrollment, .student-count",
        "dast_pipeline_stage": ".pipeline-stage",
        "source": ".source-info",
        "edlink_id": ".edlink-id",
        "twenty_id": ".twenty-id",
        "nces_id": ".nces-id, .national-id",
        "state_id": ".state-id",
        "school_association": ".association-info, .memberships",
        "lcms_district": ".lcms-district"
    }

    # Specific selectors for each data source
    DATA_SOURCES: ClassVar[List[Dict[str, Any]]] = [
        {
            "name": "GreatSchools",
            "base_url": "https://www.greatschools.org",
            "search_path": "/search/search.page?q={query}",
            "selectors": {
                "school_name": ".school-name, h1",
                "address": ".school-address",
                "city": "span[itemprop='addressLocality']",
                "zip": "span[itemprop='postalCode']",
                "phone": ".school-phone",
                "total_student_enrollment": ".enrollment-number",
                "school_type": ".school-type",
                "nces_id": ".nces-id",
            }
        },
        {
            "name": "Niche",
            "base_url": "https://www.niche.com/k12",
            "search_path": "/search/schools/?q={query}",
            "selectors": {
                "school_name": ".school-header__name",
                "address": ".school-address__line",
                "city": ".school-address__city",
                "zip": ".school-address__zip",
                "phone": ".school-contact__phone",
                "total_student_enrollment": ".school-stats__enrollment",
                "school_type": ".school-stats__type",
                "nces_id": ".school-id--nces",
            }
        },
        {
            "name": "SchoolDigger",
            "base_url": "https://www.schooldigger.com",
            "search_path": "/go/XX/search.aspx?q={query}",
            "selectors": {
                "school_name": ".schoolTitle",
                "address": ".schoolAddress",
                "city": ".schoolCity",
                "zip": ".schoolZip",
                "phone": ".schoolPhone",
                "total_student_enrollment": ".enrollment",
                "school_type": ".schoolType",
                "nces_id": ".ncesID",
            }
        }
    ]

    session: requests.Session = Field(default_factory=requests.Session)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _fetch_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            time.sleep(random.uniform(2, 5))  # Rate limiting
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.text, response.url
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            raise

    def _extract_data(self, soup: BeautifulSoup, selectors: Dict[str, str]) -> Dict[str, Any]:
        data = {}
        for field, selector in selectors.items():
            element = soup.select_one(selector)
            if element:
                value = element.get_text(strip=True) or element.get("content")
                if field in ["latitude", "longitude"] and value:
                    data[field] = float(value)
                elif field in ["zip", "total_student_enrollment"] and value:
                    data[field] = int(''.join(filter(str.isdigit, value)))
                elif field == "days_in_school_year" and value:
                    data[field] = float(''.join(filter(lambda x: x.isdigit() or x == '.', value)))
                elif field == "school_association":
                    data[field] = [{"name": e.get_text(strip=True)} for e in soup.select(selector)]
                else:
                    data[field] = value
        return data

    def scrape_school(self, url: str, custom_selectors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            content, final_url = self._fetch_url(url)
            if not content:
                return {"error": f"Failed to fetch {url}"}
            soup = BeautifulSoup(content, 'html.parser')
            selectors = custom_selectors or self.DEFAULT_SELECTORS
            data = self._extract_data(soup, selectors)
            data["source_url"] = final_url
            logger.info(f"Scraped data from {url}: {data}")
            return data
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {"error": str(e)}

    def search_schools(self, query: str, source_name: str) -> List[Dict[str, Any]]:
        source = next((s for s in self.DATA_SOURCES if s["name"] == source_name), None)
        if not source:
            return [{"error": f"Unknown source: {source_name}"}]
        
        search_url = urljoin(source["base_url"], source["search_path"].format(query=query))
        try:
            content, _ = self._fetch_url(search_url)
            soup = BeautifulSoup(content, 'html.parser')
            school_links = [urljoin(source["base_url"], a["href"]) for a in soup.select("a[href*='school']")]
            return [{"url": link} for link in school_links[:5]]  # Limit to 5 for testing
        except Exception as e:
            logger.error(f"Error searching {source_name}: {e}")
            return [{"error": str(e)}]

    def _run(self, url: str, selectors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self.scrape_school(url, selectors)