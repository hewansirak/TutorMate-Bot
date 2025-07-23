from pathlib import Path
import requests
import json
from typing import Any, List, Dict, Optional
import hashlib
from datetime import datetime
import openai
import xml.etree.ElementTree as ET
import re
import os

from dotenv import load_dotenv

import sqlite3

load_dotenv()

class AcademicAPIClient:
    def __init__(self, db_path: str = "academic_assistant.db"):
        self.mock_mode = False
        self.openai_client = openai.OpenAI() if not self.mock_mode else None
        self.db_path = db_path
        
    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def _get_arxiv_id_from_paper_id(self, paper_id: str) -> str:
        """Extract arXiv ID from paper data stored in database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT url FROM cached_papers WHERE paper_id = ?
                """, (paper_id,))
                
                result = cursor.fetchone()
                if not result or not result[0]:
                    print(f"No URL found for paper_id: {paper_id}")
                    return None
                
                url = result[0]
                print(f"Found URL: {url}")
                
                # Extract arXiv ID from different URL formats:
                # https://arxiv.org/abs/1234.5678v1
                # https://arxiv.org/abs/1234.5678
                # http://export.arxiv.org/abs/1234.5678
                
                # Pattern to match arXiv URLs and extract the ID
                arxiv_patterns = [
                    r'arxiv\.org/abs/([^/?]+)',  # Matches most arXiv URLs
                    r'export\.arxiv\.org/abs/([^/?]+)',  # Alternative arXiv domain
                ]
                
                for pattern in arxiv_patterns:
                    match = re.search(pattern, url)
                    if match:
                        arxiv_id = match.group(1)
                        print(f"Extracted arXiv ID: {arxiv_id}")
                        return arxiv_id
                
                print(f"No arXiv ID pattern found in URL: {url}")
                return None
                
        except Exception as e:
            print(f"Error extracting arXiv ID for {paper_id}: {e}")
            return None
    
    # Updated download_paper method that uses the database lookup
    def download_paper(self, paper_id: str, download_dir: str = "downloads") -> Dict[str, Any]:
        """Download paper PDF from arXiv using database lookup"""
        try:
            # Create downloads directory if it doesn't exist
            Path(download_dir).mkdir(exist_ok=True)
            
            # Get arXiv ID from database
            arxiv_id = self._get_arxiv_id_from_paper_id(paper_id)
            
            if not arxiv_id:
                return {
                    "success": False,
                    "error": "Could not find arXiv ID for this paper. Make sure the paper is from arXiv.",
                    "paper_id": paper_id
                }
            
            # Construct arXiv PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            
            # Generate safe filename
            safe_filename = f"{arxiv_id.replace('/', '_').replace(':', '_')}.pdf"
            file_path = os.path.join(download_dir, safe_filename)
            
            # Check if file already exists
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"File already exists: {file_path}")
                return {
                    "success": True,
                    "file_path": file_path,
                    "file_size": file_size,
                    "arxiv_id": arxiv_id,
                    "paper_id": paper_id,
                    "download_url": pdf_url,
                    "already_existed": True
                }
            
            # Download the PDF
            print(f"Downloading paper from: {pdf_url}")
            response = requests.get(pdf_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Check if we got a valid PDF (arXiv returns HTML error pages sometimes)
            content_type = response.headers.get('content-type', '').lower()
            if 'html' in content_type:
                return {
                    "success": False,
                    "error": "Paper not available for download (received HTML instead of PDF)",
                    "paper_id": paper_id
                }
            
            # Save the file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(file_path)
            
            # Verify we downloaded a valid PDF (basic check)
            if file_size < 1024:  # Less than 1KB is suspicious
                os.remove(file_path)  # Clean up
                return {
                    "success": False,
                    "error": "Downloaded file appears to be invalid (too small)",
                    "paper_id": paper_id
                }
            
            print(f"Successfully downloaded: {file_path} ({file_size} bytes)")
            
            return {
                "success": True,
                "file_path": file_path,
                "file_size": file_size,
                "arxiv_id": arxiv_id,
                "paper_id": paper_id,
                "download_url": pdf_url,
                "already_existed": False
            }
            
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Download timed out. The paper might be large or the server is slow.",
                "paper_id": paper_id
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Download failed: {str(e)}",
                "paper_id": paper_id
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "paper_id": paper_id
            }
         
    def search_papers(self, query: str, year: Optional[str] = None, limit: int = 3) -> List[Dict]:
        """Search for academic papers"""
        if self.mock_mode:
            return self._mock_paper_search(query, year, limit)
        else:
            # Real implementation would use arXiv API, Google Scholar API, etc.
            return self._arxiv_search(query, year, limit)
    
    def generate_summary(self, title: str, abstract: str) -> str:
        """Generate summary using Gemini API - PUBLIC METHOD"""
        return self._openai_generate_summary(title, abstract)

    def _openai_generate_summary(self, title: str, abstract: str) -> str:
        """Generate summary using Gemini API (replacing OpenAI)"""
        try:
            import google.generativeai as genai
            from dotenv import load_dotenv
            
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")
            
            if not api_key:
                print("GEMINI_API_KEY not found - using mock summary")
                return self._mock_generate_summary(title, abstract)
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            prompt = f"""
            Please provide a concise but comprehensive summary of this academic paper:
            
            Title: {title}
            Abstract: {abstract}
            
            Structure your summary with:
            **Key Findings:**
            • [2-3 bullet points of main findings]
            
            **Methodology:**
            [Brief overview of the research approach]
            
            **Significance:**
            [Why this research matters and its potential impact]
            
            Keep it accessible but accurate, suitable for someone wanting to quickly understand the paper's contribution.
            """
            
            response = model.generate_content(prompt)
            return response.text
            
        except ImportError:
            print("google-generativeai not installed - using mock summary")
            return self._mock_generate_summary(title, abstract)
        except Exception as e:
            print(f"Gemini summary error: {e}")
            return self._mock_generate_summary(title, abstract)
    
    
    def _arxiv_search(self, query: str, year: Optional[str] = None, limit: int = 3) -> List[Dict]:
        """Real arXiv API search"""
        try:
            base_url = "http://export.arxiv.org/api/query"
            search_query = f"all:{query}"
            
            if year:
                search_query += f" AND submittedDate:[{year}0101 TO {year}1231]"
            
            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": limit,
                "sortBy": "relevance",
                "sortOrder": "descending"
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Define namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            papers = []
            entries = root.findall('atom:entry', ns)
            
            for entry in entries:
                # Extract arXiv ID from the entry ID
                entry_id = entry.find('atom:id', ns).text
                arxiv_match = re.search(r'arxiv\.org/abs/(.+)$', entry_id)
                arxiv_id = arxiv_match.group(1) if arxiv_match else entry_id.split('/')[-1]
                
                # Extract title
                title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                
                # Extract authors
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns)
                    if name is not None:
                        authors.append(name.text)
                
                # Extract abstract
                summary = entry.find('atom:summary', ns)
                abstract = summary.text.strip().replace('\n', ' ') if summary is not None else ""
                
                # Extract published date and year
                published = entry.find('atom:published', ns)
                year_published = 2023  # default
                if published is not None:
                    try:
                        year_published = int(published.text[:4])
                    except:
                        year_published = 2023
                
                paper = {
                    "id": f"paper_{hashlib.md5(arxiv_id.encode()).hexdigest()[:8]}",
                    "title": title,
                    "authors": authors,
                    "year": year_published,
                    "abstract": abstract,
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "search_query": query,
                    "arxiv_id": arxiv_id
                }
                papers.append(paper)
            
            return papers
            
        except requests.exceptions.Timeout:
            print("ArXiv API timeout - falling back to mock data")
            return self._mock_paper_search(query, year, limit)
        except requests.exceptions.RequestException as e:
            print(f"ArXiv API request error: {e}")
            return self._mock_paper_search(query, year, limit)
        except ET.ParseError as e:
            print(f"ArXiv XML parsing error: {e}")
            return self._mock_paper_search(query, year, limit)
        except Exception as e:
            print(f"ArXiv search error: {e}")
            return self._mock_paper_search(query, year, limit)
        