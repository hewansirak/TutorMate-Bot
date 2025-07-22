import requests
import json
from typing import List, Dict, Optional
import hashlib
from datetime import datetime
import openai
import os

class AcademicAPIClient:
    def __init__(self):
        # Mock API mode for MVP - set to True to use real APIs
        self.mock_mode = True
        self.openai_client = openai.OpenAI() if not self.mock_mode else None
    
    def search_papers(self, query: str, year: Optional[str] = None, limit: int = 3) -> List[Dict]:
        """Search for academic papers"""
        if self.mock_mode:
            return self._mock_paper_search(query, year, limit)
        else:
            # Real implementation would use arXiv API, Google Scholar API, etc.
            return self._arxiv_search(query, year, limit)
    
    def generate_summary(self, title: str, abstract: str) -> str:
        """Generate paper summary using LLM"""
        if self.mock_mode:
            return self._mock_generate_summary(title, abstract)
        else:
            return self._openai_generate_summary(title, abstract)
    
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
            
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            # Parse XML response (simplified - would need proper XML parsing)
            papers = []
            # XML parsing logic would go here
            # For now, fallback to mock data
            return self._mock_paper_search(query, year, limit)
            
        except Exception as e:
            print(f"ArXiv search error: {e}")
            return self._mock_paper_search(query, year, limit)
    
    def _openai_generate_summary(self, title: str, abstract: str) -> str:
        """Generate summary using OpenAI API"""
        try:
            prompt = f"""
            Please provide a concise but comprehensive summary of this academic paper:
            
            Title: {title}
            Abstract: {abstract}
            
            Structure your summary with:
            - Key findings (2-3 bullet points)
            - Methodology overview
            - Significance and impact
            
            Keep it accessible but accurate.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an academic research assistant that creates clear, concise summaries of research papers."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"OpenAI summary error: {e}")
            return self._mock_generate_summary(title, abstract)
    
    def get_paper_details(self, paper_id: str) -> Dict:
        """Get detailed paper information"""
        # This would fetch full paper details from APIs
        # For MVP, return empty dict (details come from cache)
        return {}
    
    def search_by_author(self, author_name: str, limit: int = 5) -> List[Dict]:
        """Search papers by author"""
        # Extension feature - search by author name
        return self.search_papers(f"author:{author_name}", limit=limit)
    
    def get_related_papers(self, paper_id: str, limit: int = 3) -> List[Dict]:
        """Find related papers"""
        # Extension feature - find papers related to given paper
        return []