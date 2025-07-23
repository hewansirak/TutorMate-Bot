import requests
import json
from typing import List, Dict, Optional
import hashlib
from datetime import datetime
import openai
import xml.etree.ElementTree as ET
import re
import os

from dotenv import load_dotenv

load_dotenv()

class AcademicAPIClient:
    def __init__(self):
        self.mock_mode = False
        self.openai_client = openai.OpenAI() if not self.mock_mode else None
    
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
    
    def _mock_paper_search(self, query: str, year: Optional[str] = None, limit: int = 3) -> List[Dict]:
        """Mock paper search for MVP testing"""
        mock_papers = [
            {
                "id": f"paper_{hashlib.md5(f'{query}_1'.encode()).hexdigest()[:8]}",
                "title": f"A Comprehensive Study of {query.title()}: Recent Advances",
                "authors": ["Dr. Jane Smith", "Prof. John Doe", "Dr. Alice Johnson"],
                "year": int(year) if year else 2023,
                "abstract": f"This paper presents a comprehensive analysis of {query}. We investigate recent methodologies and present novel approaches that demonstrate significant improvements. Our experimental results show promising outcomes in various benchmarks and real-world applications.",
                "url": f"https://arxiv.org/abs/2023.{query.replace(' ', '')[:4]}.12345",
                "search_query": query
            },
            {
                "id": f"paper_{hashlib.md5(f'{query}_2'.encode()).hexdigest()[:8]}",
                "title": f"Machine Learning Approaches to {query.title()}: A Survey",
                "authors": ["Dr. Bob Wilson", "Prof. Sarah Chen"],
                "year": int(year) if year else 2022,
                "abstract": f"We survey the landscape of machine learning applications in {query}. This comprehensive review covers traditional methods, deep learning approaches, and emerging techniques. We provide insights into current challenges and future directions.",
                "url": f"https://arxiv.org/abs/2022.{query.replace(' ', '')[:4]}.67890",
                "search_query": query
            },
            {
                "id": f"paper_{hashlib.md5(f'{query}_3'.encode()).hexdigest()[:8]}",
                "title": f"Empirical Analysis of {query.title()} in Distributed Systems",
                "authors": ["Dr. Mike Zhang", "Prof. Lisa Wang", "Dr. Tom Brown"],
                "year": int(year) if year else 2024,
                "abstract": f"This work presents an empirical study of {query} implementation in distributed environments. We analyze performance characteristics, scalability issues, and propose optimization strategies. Our results demonstrate improved efficiency across multiple deployment scenarios.",
                "url": f"https://arxiv.org/abs/2024.{query.replace(' ', '')[:4]}.11111",
                "search_query": query
            }
        ]
        
        return mock_papers[:limit]
    
    def _mock_generate_summary(self, title: str, abstract: str) -> str:
        """Mock summary generation"""
        return f"""
**Summary of: {title}**

**Key Findings:**
• This research addresses important challenges in the field
• The authors propose novel methodologies that show significant improvements
• Experimental validation demonstrates the effectiveness of the approach

**Methodology:**
The study employs a combination of theoretical analysis and empirical evaluation to validate the proposed solutions.

**Impact:**
This work contributes to the field by providing new insights and practical solutions that can be applied in real-world scenarios.

**Significance:**
The findings have implications for future research and development in this area, potentially leading to improved performance and new applications.
        """.strip()
    
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
        
    def get_paper_details(self, paper_id: str) -> Dict:
        """Get detailed paper information"""
        # This would fetch full paper details from APIs
        return {}
    
    def search_by_author(self, author_name: str, limit: int = 5) -> List[Dict]:
        """Search papers by author"""
        # Extension feature - search by author name
        return self.search_papers(f"author:{author_name}", limit=limit)
    
    def get_related_papers(self, paper_id: str, limit: int = 3) -> List[Dict]:
        """Find related papers"""
        # Extension feature - find papers related to given paper
        return []