import os
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage
from typing import List, Dict, Any
import json
import re
from datetime import datetime
from openai import OpenAI
from api_integrations import AcademicAPIClient
from database import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

# OpenAI client pointing to Gemini
openai_client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

class AcademicTutorAgent:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.api_client = AcademicAPIClient()
        self.llm = ChatOpenAI(
            model="gemini-2.0-flash-exp",
            temperature=0.1,
            openai_api_key=api_key,
            openai_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            model_kwargs={"top_p": 0.8}
        )
        self.agent_executor = self._create_agent()
        self.conversation_memory = {}  # Simple in-memory storage for MVP
    
    def _create_agent(self):
        # Define tools for function calling
        tools = [
            Tool(
                name="search_academic",
                description="Search for academic papers. Input: 'query|year' (year optional)",
                func=self._search_academic_papers
            ),
            Tool(
                name="generate_summary",
                description="Generate summary of a specific paper. Input: paper_id",
                func=self._generate_paper_summary
            ),
            Tool(
                name="get_search_history",
                description="Get user's previous searches. Input: user_id",
                func=self._get_user_search_history
            ),
            Tool(
                name="get_user_interests",
                description="Get user's research interests. Input: user_id",
                func=self._get_user_interests
            )
        ]
        
        # Create system prompt
        system_prompt = """You are an Academic Research Assistant. You help users find and understand academic papers.

Your capabilities:
1. Search academic papers using search_academic(query|year)
2. Summarize papers using generate_summary(paper_id)  
3. Track user interests and search history
4. Provide context-aware recommendations

When users ask for papers:
- Use search_academic function
- Extract relevant topics to update user interests
- Provide clear, numbered results

When users want summaries:
- Use generate_summary with the paper ID
- Provide comprehensive but accessible explanations

When users ask about their history:
- Use get_search_history or get_user_interests functions
- Present information in a helpful format

Be conversational, helpful, and academic in tone."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
            ("assistant", "{agent_scratchpad}")
        ])
        
        agent = create_openai_functions_agent(self.llm, tools, prompt)
        return AgentExecutor(agent=agent, tools=tools, verbose=True)
    
    async def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        try:
            # Store conversation context
            if user_id not in self.conversation_memory:
                self.conversation_memory[user_id] = []
            
            self.conversation_memory[user_id].append({"role": "user", "message": message})
            
            # Process with agent
            response = await self._run_agent(user_id, message)
            
            # Store response
            self.conversation_memory[user_id].append({"role": "assistant", "message": response["response"]})
            
            # Log to database
            self.db_manager.log_chat_session(
                user_id, 
                message, 
                response["response"], 
                response.get("function_calls", [])
            )
            
            return response
            
        except Exception as e:
            return {"response": f"I encountered an error: {str(e)}", "error": True}
    
    async def _run_agent(self, user_id: str, message: str) -> Dict[str, Any]:
        # Add user context to message
        enhanced_message = f"User ID: {user_id}\nMessage: {message}"
        
        # Run the agent
        result = self.agent_executor.invoke({"input": enhanced_message})
        
        # Parse any special outputs (papers, summaries)
        response_data = {
            "response": result["output"],
            "function_calls": []  # Track what functions were called
        }
        
        # Extract structured data if present
        if "PAPERS_FOUND:" in result["output"]:
            response_data["papers"] = self._extract_papers_from_response(result["output"])
        
        if "SUMMARY_GENERATED:" in result["output"]:
            response_data["summary"] = self._extract_summary_from_response(result["output"])
        
        return response_data
    
    def _search_academic_papers(self, query_input: str) -> str:
        """Search for academic papers"""
        try:
            # Parse input
            parts = query_input.split("|")
            query = parts[0].strip()
            year = parts[1].strip() if len(parts) > 1 else None
            
            # Search papers
            papers = self.api_client.search_papers(query, year=year)
            
            if not papers:
                return "No papers found for this query."
            
            # Cache papers and extract topics for interest tracking
            topics = self._extract_topics_from_query(query)
            user_id = self._extract_user_id_from_context()
            
            for paper in papers:
                self.db_manager.cache_paper(paper)
            
            # Update user interests and search history
            if user_id:
                self.db_manager.log_search(user_id, query)
                for topic in topics:
                    self.db_manager.update_user_interest(user_id, topic)
            
            # Format response
            result = "PAPERS_FOUND:\n"
            for i, paper in enumerate(papers, 1):
                result += f"{i}. **{paper['title']}** ({paper['year']})\n"
                result += f"   Authors: {', '.join(paper['authors'][:3])}\n"
                result += f"   URL: {paper['url']}\n"
                result += f"   Paper ID: {paper['id']}\n\n"
            
            return result
            
        except Exception as e:
            return f"Error searching papers: {str(e)}"
    
    def _generate_paper_summary(self, paper_id: str) -> str:
        """Generate summary for a specific paper"""
        try:
            # Check if we have cached summary
            cached_paper = self.db_manager.get_cached_paper(paper_id)
            if cached_paper and cached_paper.get("summary"):
                return f"SUMMARY_GENERATED:\n{cached_paper['summary']}"
            
            # Generate new summary
            if cached_paper and cached_paper.get("abstract"):
                summary = self.api_client.generate_summary(
                    cached_paper["title"], 
                    cached_paper["abstract"]
                )
                
                # Cache the summary
                self.db_manager.save_paper_summary(paper_id, summary)
                
                return f"SUMMARY_GENERATED:\n{summary}"
            else:
                return "Paper not found in cache. Please search for papers first."
                
        except Exception as e:
            return f"Error generating summary: {str(e)}"
    
    def _get_user_search_history(self, user_id: str) -> str:
        """Get user's search history"""
        try:
            history = self.db_manager.get_user_search_history(user_id, limit=10)
            
            if not history:
                return "No search history found."
            
            result = "Your recent searches:\n"
            for item in history:
                result += f"• {item['query']} ({item['timestamp'][:10]})\n"
            
            return result
            
        except Exception as e:
            return f"Error retrieving search history: {str(e)}"
    
    def _get_user_interests(self, user_id: str) -> str:
        """Get user's interests"""
        try:
            interests = self.db_manager.get_user_interests(user_id)
            
            if not interests:
                return "No research interests tracked yet."
            
            result = "Your research interests:\n"
            for item in interests:
                result += f"• {item['topic'].title()} (searched {item['score']} times)\n"
            
            return result
            
        except Exception as e:
            return f"Error retrieving interests: {str(e)}"
    
    def _extract_topics_from_query(self, query: str) -> List[str]:
        """Extract topics from search query for interest tracking"""
        # Simple keyword extraction - can be enhanced with NLP
        topics = []
        keywords = query.lower().split()
        
        # Filter out common words
        stopwords = {"in", "on", "for", "about", "and", "or", "the", "a", "an", "with"}
        topics = [word for word in keywords if word not in stopwords and len(word) > 2]
        
        return topics[:3]  # Limit to top 3 topics
    
    def _extract_user_id_from_context(self) -> str:
        """Extract user ID from conversation context - simplified for MVP"""
        # In a real implementation, this would be passed through the context
        return "default_user"  # Placeholder for MVP
    
    def _extract_papers_from_response(self, response: str) -> List[Dict]:
        """Extract papers data from agent response"""
        # This would parse the structured paper data
        # Simplified for MVP
        return []
    
    def _extract_summary_from_response(self, response: str) -> str:
        """Extract summary from agent response"""
        if "SUMMARY_GENERATED:" in response:
            return response.split("SUMMARY_GENERATED:")[1].strip()
        return ""