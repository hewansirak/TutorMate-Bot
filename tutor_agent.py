import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any
import google.generativeai as genai
from api_integrations import AcademicAPIClient
from database import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

class AcademicTutorAgent:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.api_client = AcademicAPIClient()
        
        # Configure Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        self.conversation_memory = {}  # Simple in-memory storage for MVP
    
    async def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        try:
            # Store conversation context
            if user_id not in self.conversation_memory:
                self.conversation_memory[user_id] = []
            
            self.conversation_memory[user_id].append({"role": "user", "message": message})
            
            # Analyze the message to determine what action to take
            action = self._analyze_user_intent(message)
            
            response_data = await self._handle_user_request(user_id, message, action)
            
            # Store response
            self.conversation_memory[user_id].append({"role": "assistant", "message": response_data["response"]})
            
            # Log to database
            self.db_manager.log_chat_session(
                user_id, 
                message, 
                response_data["response"], 
                response_data.get("function_calls", [])
            )
            
            return response_data
            
        except Exception as e:
            print(f"Error in process_message: {str(e)}")
            return {"response": f"I encountered an error: {str(e)}", "error": True}
    
    def _analyze_user_intent(self, message: str) -> str:
        """Analyze user message to determine intent"""
        message_lower = message.lower()
        
        if any(keyword in message_lower for keyword in ["search", "find", "paper", "research"]):
            return "search_papers"
        elif any(keyword in message_lower for keyword in ["summarize", "summary", "explain"]):
            return "generate_summary"
        elif any(keyword in message_lower for keyword in ["history", "previous", "past searches"]):
            return "get_history"
        elif any(keyword in message_lower for keyword in ["interests", "topics", "my research"]):
            return "get_interests"
        else:
            return "general_chat"
    
    async def _handle_user_request(self, user_id: str, message: str, action: str) -> Dict[str, Any]:
        """Handle different types of user requests"""
        
        if action == "search_papers":
            return await self._handle_paper_search(user_id, message)
        elif action == "generate_summary":
            return await self._handle_summary_request(user_id, message)
        elif action == "get_history":
            return await self._handle_history_request(user_id)
        elif action == "get_interests":
            return await self._handle_interests_request(user_id)
        else:
            return await self._handle_general_chat(user_id, message)
    
    async def _handle_paper_search(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle paper search requests"""
        try:
            # Extract search query and year from message using Gemini
            extraction_prompt = f"""
            Extract the search query and year (if mentioned) from this user message: "{message}"
            
            Respond in this exact format:
            QUERY: [extracted search terms]
            YEAR: [year if mentioned, otherwise "none"]
            
            Examples:
            - "Find papers about machine learning from 2023" -> QUERY: machine learning, YEAR: 2023
            - "Search for deep learning papers" -> QUERY: deep learning, YEAR: none
            """
            
            extraction_response = self.model.generate_content(extraction_prompt)
            extracted_text = extraction_response.text
            
            # Parse the extraction
            query_match = re.search(r'QUERY:\s*(.+)', extracted_text)
            year_match = re.search(r'YEAR:\s*(.+)', extracted_text)
            
            query = query_match.group(1).strip() if query_match else message
            year = year_match.group(1).strip() if year_match and year_match.group(1).strip().lower() != "none" else None
            
            # Search for papers
            papers = self.api_client.search_papers(query, year=year, limit=3)
            
            if not papers:
                return {"response": "I couldn't find any papers matching your search criteria. Try different keywords or check the spelling."}
            
            # Cache papers and update user interests
            for paper in papers:
                self.db_manager.cache_paper(paper)
            
            # Update user search history and interests
            self.db_manager.log_search(user_id, query)
            topics = self._extract_topics_from_query(query)
            for topic in topics:
                self.db_manager.update_user_interest(user_id, topic)
            
            # Format response
            response_text = f"I found {len(papers)} papers related to '{query}':\n\n"
            
            for i, paper in enumerate(papers, 1):
                response_text += f"**{i}. {paper['title']}** ({paper['year']})\n"
                response_text += f"Authors: {', '.join(paper['authors'][:3])}\n"
                response_text += f"Paper ID: `{paper['id']}`\n"
                response_text += f"URL: {paper['url']}\n\n"
            
            response_text += "You can ask me to summarize any of these papers by mentioning the paper ID or title!"
            
            return {
                "response": response_text,
                "papers": papers,
                "function_calls": ["search_papers"]
            }
            
        except Exception as e:
            return {"response": f"Error searching for papers: {str(e)}"}
    
    async def _handle_summary_request(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle paper summary requests"""
        try:
            # Extract paper ID or find paper from recent searches
            paper_id_match = re.search(r'paper_[a-f0-9]{8}', message)
            
            if paper_id_match:
                paper_id = paper_id_match.group(0)
            else:
                # Try to find paper from recent context or search history
                return {"response": "Please specify which paper you'd like me to summarize. You can mention the paper ID (like `paper_12345678`) or search for papers first."}
            
            # Get cached paper
            cached_paper = self.db_manager.get_cached_paper(paper_id)
            
            if not cached_paper:
                return {"response": "I couldn't find that paper. Please search for papers first or provide a valid paper ID."}
            
            # Check if we have a cached summary
            if cached_paper.get("summary"):
                summary = cached_paper["summary"]
            else:
                # Generate new summary
                summary = self.api_client.generate_summary(
                    cached_paper["title"], 
                    cached_paper["abstract"]
                )
                # Cache the summary
                self.db_manager.save_paper_summary(paper_id, summary)
            
            response_text = f"Here's a summary of **{cached_paper['title']}**:\n\n{summary}"
            
            return {
                "response": response_text,
                "summary": summary,
                "function_calls": ["generate_summary"]
            }
            
        except Exception as e:
            return {"response": f"Error generating summary: {str(e)}"}
    
    async def _handle_history_request(self, user_id: str) -> Dict[str, Any]:
        """Handle search history requests"""
        try:
            history = self.db_manager.get_user_search_history(user_id, limit=10)
            
            if not history:
                return {"response": "You haven't made any searches yet. Try asking me to find some papers!"}
            
            response_text = "Here are your recent searches:\n\n"
            for i, item in enumerate(history, 1):
                response_text += f"{i}. **{item['query']}** ({item['timestamp'][:10]})\n"
            
            return {
                "response": response_text,
                "function_calls": ["get_search_history"]
            }
            
        except Exception as e:
            return {"response": f"Error retrieving search history: {str(e)}"}
    
    async def _handle_interests_request(self, user_id: str) -> Dict[str, Any]:
        """Handle user interests requests"""
        try:
            interests = self.db_manager.get_user_interests(user_id)
            
            if not interests:
                return {"response": "I haven't identified your research interests yet. Search for some papers and I'll start tracking your interests!"}
            
            response_text = "Based on your searches, your research interests include:\n\n"
            for i, item in enumerate(interests, 1):
                response_text += f"{i}. **{item['topic'].title()}** (searched {item['score']} times)\n"
            
            return {
                "response": response_text,
                "function_calls": ["get_user_interests"]
            }
            
        except Exception as e:
            return {"response": f"Error retrieving interests: {str(e)}"}
    
    async def _handle_general_chat(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle general conversation"""
        try:
            # Use Gemini for general academic assistant conversation
            system_prompt = """You are an Academic Research Assistant. You help users find and understand academic papers.

You can help users:
- Search for academic papers by topic, author, or year
- Summarize research papers to make them more accessible
- Track their research interests and search history
- Provide academic guidance and explanations

Respond in a helpful, friendly, and academic tone. If the user seems to want to search for papers, suggest they ask you to "find papers about [topic]"."""

            conversation_prompt = f"{system_prompt}\n\nUser: {message}\n\nAssistant:"
            
            response = self.model.generate_content(conversation_prompt)
            
            return {
                "response": response.text,
                "function_calls": ["general_chat"]
            }
            
        except Exception as e:
            return {"response": f"Error in general chat: {str(e)}"}
    
    def _extract_topics_from_query(self, query: str) -> List[str]:
        """Extract topics from search query for interest tracking"""
        topics = []
        keywords = query.lower().split()
        
        # Filter out common words
        stopwords = {"in", "on", "for", "about", "and", "or", "the", "a", "an", "with", "find", "search", "papers"}
        topics = [word for word in keywords if word not in stopwords and len(word) > 2]
        
        return topics[:3]  # Limit to top 3 topics