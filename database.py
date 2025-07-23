import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any
import os

class DatabaseManager:
    def __init__(self, db_path: str = "academic_assistant.db"):
        self.db_path = db_path
        self.init_tables()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # User queries and search history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    search_type TEXT DEFAULT 'academic',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User interests/topics tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_interests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    interest_score INTEGER DEFAULT 1,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, topic)
                )
            """)
            
            # Cached papers and results
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT UNIQUE,
                    title TEXT,
                    authors TEXT,
                    year INTEGER,
                    abstract TEXT,
                    url TEXT,
                    summary TEXT,
                    search_query TEXT,
                    cached_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Chat sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    message TEXT,
                    response TEXT,
                    function_calls TEXT,  -- JSON string of function calls made
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    file_path TEXT,
                    arxiv_id TEXT,
                    download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER
                )
            """)
            
            conn.commit()
    
    def log_search(self, user_id: str, query: str, search_type: str = "academic"):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO search_history (user_id, query, search_type) VALUES (?, ?, ?)",
                (user_id, query, search_type)
            )
            conn.commit()
    
    def update_user_interest(self, user_id: str, topic: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_interests (user_id, topic, interest_score, last_accessed)
                VALUES (?, ?, 
                    COALESCE((SELECT interest_score FROM user_interests WHERE user_id = ? AND topic = ?) + 1, 1),
                    CURRENT_TIMESTAMP)
            """, (user_id, topic.lower(), user_id, topic.lower()))
            conn.commit()
    
    def get_user_search_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT query, search_type, timestamp 
                FROM search_history 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (user_id, limit))
            
            results = cursor.fetchall()
            return [
                {"query": row[0], "search_type": row[1], "timestamp": row[2]}
                for row in results
            ]
    
    def get_user_interests(self, user_id: str, limit: int = 10) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT topic, interest_score, last_accessed
                FROM user_interests 
                WHERE user_id = ? 
                ORDER BY interest_score DESC, last_accessed DESC
                LIMIT ?
            """, (user_id, limit))
            
            results = cursor.fetchall()
            return [
                {"topic": row[0], "score": row[1], "last_accessed": row[2]}
                for row in results
            ]
    
    def cache_paper(self, paper_data: Dict):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO cached_papers 
                (paper_id, title, authors, year, abstract, url, search_query)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                paper_data.get("id", ""),
                paper_data.get("title", ""),
                json.dumps(paper_data.get("authors", [])),
                paper_data.get("year", 0),
                paper_data.get("abstract", ""),
                paper_data.get("url", ""),
                paper_data.get("search_query", "")
            ))
            conn.commit()
    
    def get_cached_paper(self, paper_id: str) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT paper_id, title, authors, year, abstract, url, summary, search_query
                FROM cached_papers 
                WHERE paper_id = ?
            """, (paper_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    "id": result[0],
                    "title": result[1],
                    "authors": json.loads(result[2]) if result[2] else [],
                    "year": result[3],
                    "abstract": result[4],
                    "url": result[5],
                    "summary": result[6],
                    "search_query": result[7]
                }
            return {}
        
    def debug_cached_papers(self) -> List[Dict]:
        """Debug method to see what papers are cached"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT paper_id, title FROM cached_papers ORDER BY cached_date DESC LIMIT 10")
            results = cursor.fetchall()
            return [{"paper_id": row[0], "title": row[1]} for row in results]
    
    def save_paper_summary(self, paper_id: str, summary: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE cached_papers SET summary = ? WHERE paper_id = ?",
                (summary, paper_id)
            )
            conn.commit()
    
    def log_chat_session(self, user_id: str, message: str, response: str, function_calls: List[str] = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (user_id, message, response, function_calls)
                VALUES (?, ?, ?, ?)
            """, (user_id, message, response, json.dumps(function_calls or [])))
            conn.commit()
    
    def log_paper_download(self, user_id: str, paper_id: str, file_path: str, arxiv_id: str = None, file_size: int = None):
        """Log a paper download"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get file size if not provided
            if file_size is None and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
            
            cursor.execute("""
                INSERT INTO paper_downloads (user_id, paper_id, file_path, arxiv_id, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, paper_id, file_path, arxiv_id, file_size))
            conn.commit()
    
    def get_user_downloads(self, user_id: str, limit: int = 20) -> List[Dict]:
        """Get user's download history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pd.paper_id, pd.file_path, pd.download_date, pd.file_size, pd.arxiv_id,
                       cp.title, cp.authors
                FROM paper_downloads pd
                LEFT JOIN cached_papers cp ON pd.paper_id = cp.paper_id
                WHERE pd.user_id = ?
                ORDER BY pd.download_date DESC
                LIMIT ?
            """, (user_id, limit))
            
            results = cursor.fetchall()
            return [
                {
                    "paper_id": row[0],
                    "file_path": row[1],
                    "download_date": row[2],
                    "file_size": row[3],
                    "arxiv_id": row[4],
                    "title": row[5],
                    "authors": json.loads(row[6]) if row[6] else []
                }
                for row in results
            ]
    
    def check_paper_downloaded(self, user_id: str, paper_id: str) -> Dict:
        """Check if a paper has been downloaded by the user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path, download_date, file_size
                FROM paper_downloads 
                WHERE user_id = ? AND paper_id = ?
                ORDER BY download_date DESC
                LIMIT 1
            """, (user_id, paper_id))
            
            result = cursor.fetchone()
            if result:
                return {
                    "downloaded": True,
                    "file_path": result[0],
                    "download_date": result[1],
                    "file_size": result[2],
                    "exists": os.path.exists(result[0]) if result[0] else False
                }
            return {"downloaded": False}

def init_db():
    """Initialize database - call this at startup"""
    db = DatabaseManager()
    print("Database initialized successfully")