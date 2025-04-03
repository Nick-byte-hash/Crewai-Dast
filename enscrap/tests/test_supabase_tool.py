import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
import os

# Add the project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.enscrap.tools.supabase_tool import SupabaseTool

class TestSupabaseTool(unittest.TestCase):
    def setUp(self):
        self.tool = SupabaseTool()
    
    @patch('supabase.Client.table')
    def test_get_schools_needing_enrichment(self, mock_table):
        """Test getting schools needing enrichment"""
        # Mock database response
        mock_schools = [
            {
                "school_id": "1",
                "school_name": "Test School 1",
                "address": None,
                "phone": "555-1234",
                "updated_at": "2024-01-01T00:00:00Z"
            },
            {
                "school_id": "2",
                "school_name": "Test School 2",
                "address": "123 Test St",
                "phone": None,
                "updated_at": "2025-01-01T00:00:00Z"
            },
            {
                "school_id": "3",
                "school_name": "Test School 3",
                "address": "456 Test St",
                "phone": "555-4321",
                "updated_at": "2025-03-01T00:00:00Z"
            }
        ]
        
        mock_response = MagicMock()
        mock_response.data = mock_schools
        mock_table.return_value.select.return_value.execute.return_value = mock_response
        
        # Mock datetime to be in April 2025
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 4, 1)
            
            result = self.tool.get_schools_needing_enrichment()
            
            # Should return all 3 schools since they all have either missing data or outdated timestamps
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["school_id"], "1")
            self.assertEqual(result[1]["school_id"], "2")
            self.assertEqual(result[2]["school_id"], "3")
    
    @patch('supabase.Client.table')
    def test_get_school_attributes(self, mock_table):
        """Test getting school attributes"""
        mock_school = {
            "school_id": "1",
            "school_name": "Test School",
            "address": "123 Test St",
            "phone": "555-1234",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z"
        }
        
        mock_response = MagicMock()
        mock_response.data = [mock_school]
        mock_table.return_value.select.return_value.limit.return_value.execute.return_value = mock_response
        
        result = self.tool.get_school_attributes()
        self.assertEqual(len(result), len(mock_school))
        for key in mock_school.keys():
            self.assertIn(key, result)
    
    @patch('supabase.Client.table')
    def test_update_school_attribute(self, mock_table):
        """Test updating school attribute"""
        mock_response = MagicMock()
        mock_response.data = [{"school_id": "1", "school_name": "Updated School"}]
        mock_table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response
        
        result = self.tool.update_school_attribute("1", "school_name", "Updated School")
        self.assertTrue(result)
        
        # Test failed update
        mock_response.data = []
        result = self.tool.update_school_attribute("1", "school_name", "Updated School")
        self.assertFalse(result)
    
    @patch('supabase.Client.table')
    def test_get_schools_with_missing_attributes(self, mock_table):
        """Test getting schools with missing attributes"""
        mock_schools = [
            {
                "school_id": "1",
                "school_name": "Test School 1",
                "address": None,
                "phone": "555-1234"
            },
            {
                "school_id": "2",
                "school_name": "Test School 2",
                "address": "123 Test St",
                "phone": None
            },
            {
                "school_id": "3",
                "school_name": "Test School 3",
                "address": "456 Test St",
                "phone": "555-4321"
            }
        ]
        
        mock_response = MagicMock()
        mock_response.data = mock_schools
        mock_table.return_value.select.return_value.execute.return_value = mock_response
        
        result = self.tool.get_schools_with_missing_attributes(["address", "phone"])
        
        # Should return schools 1 and 2 with their missing attributes
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["school_id"], "1")
        self.assertEqual(result[0]["missing_attributes"], ["address"])
        self.assertEqual(result[1]["school_id"], "2")
        self.assertEqual(result[1]["missing_attributes"], ["phone"])
    
    @patch('supabase.Client.table')
    def test_get_school_by_id(self, mock_table):
        """Test getting school by ID"""
        mock_school = {
            "school_id": "1",
            "school_name": "Test School",
            "address": "123 Test St",
            "phone": "555-1234",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z"
        }
        
        mock_response = MagicMock()
        mock_response.data = [mock_school]
        mock_table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        result = self.tool.get_school_by_id("1")
        self.assertEqual(result, mock_school)
        
        # Test school not found
        mock_response.data = []
        result = self.tool.get_school_by_id("1")
        self.assertIsNone(result)
    
    @patch('supabase.Client.table')
    def test_update_school(self, mock_table):
        """Test updating school data"""
        mock_school = {
            "school_id": "1",
            "school_name": "Test School",
            "address": "123 Main St",
            "phone": "555-1234"
        }
        
        # Test successful update
        mock_table.return_value.update.return_value.eq.return_value.execute.return_value = [mock_school]
        result = self.tool.update_school("1", mock_school)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["updated_fields"]), 4)
        self.assertIn("school_id", result["updated_fields"])
        self.assertIn("school_name", result["updated_fields"])
        self.assertIn("address", result["updated_fields"])
        self.assertIn("phone", result["updated_fields"])
        
        # Test failed update
        mock_table.return_value.update.return_value.eq.return_value.execute.return_value = []
        result = self.tool.update_school("1", mock_school)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["updated_fields"]), 0)

if __name__ == '__main__':
    unittest.main()
