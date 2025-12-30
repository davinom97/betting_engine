import requests
import logging
import pandas as pd
import io
import re
from datetime import datetime
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy.orm import Session
from .database import Event

logger = logging.getLogger(__name__)

# Reliability Scores
RELIABILITY_OFFICIAL = 1.0
RELIABILITY_HIGH = 0.9
RELIABILITY_MEDIUM = 0.7

class InjuryIngestor:
    def __init__(self, session: Session):
        self.session = session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def fetch_all_injuries(self, event_ids: list[str]) -> dict:
        """
        Main entry point. Fetches injuries for relevant sports based on the events provided.
        Returns: { event_id: { player_name: { status: '...', reliability: 0.9 } } }
        """
        # 1. Identify which sports we need
        events = self.session.query(Event).filter(Event.id.in_(event_ids)).all()
        sports = set(e.sport_key for e in events)
        
        # 2. Map Events by Team for quick lookup
        # Key: (Sport, TeamNameLower) -> EventID
        team_map = {}
        for e in events:
            # Normalize names to lowercase for fuzzy matching
            sport_prefix = e.sport_key.split('_')[0] # 'basketball', 'americanfootball'
            
            # Add Home & Away to Map
            team_map[(sport_prefix, self._normalize_team(e.home_team))] = e.id
            team_map[(sport_prefix, self._normalize_team(e.away_team))] = e.id

        consolidated_injuries = {}

        # 3. Route to specific scrapers
        if any('nba' in s for s in sports):
            self._process_nba(team_map, consolidated_injuries)
        
        if any('nfl' in s for s in sports):
            self._process_nfl(team_map, consolidated_injuries)
            
        if any('nhl' in s for s in sports):
            self._process_nhl(team_map, consolidated_injuries)

        if any('ncaaf' in s for s in sports):
            self._process_ncaaf(team_map, consolidated_injuries)

        return consolidated_injuries

    # --- NBA: Official PDF Parsing ---
    def _process_nba(self, team_map, output_dict):
        logger.info("Fetching NBA Official Injury Report (PDF)...")
        try:
            # 1. Calculate Season Years (Handle Jan-July rollover)
            now = datetime.now()
            # If we are in the second half of the season (Jan-July), the "start year" was last year.
            start_year = now.year if now.month >= 10 else now.year - 1
            end_year_short = str(start_year + 1)[-2:]
            
            landing_url = f"https://official.nba.com/nba-injury-report-{start_year}-{end_year_short}-season/"
            
            r = requests.get(landing_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.content, 'html.parser')
            
            # Find the first link containing 'Injury-Report' and '.pdf'
            pdf_link = None
            for a in soup.find_all('a', href=True):
                if 'Injury-Report' in a['href'] and '.pdf' in a['href']:
                    pdf_link = a['href']
                    break
            
            if not pdf_link:
                logger.warning(f"Could not find NBA Injury PDF link on {landing_url}")
                return

            # 2. Download and Parse PDF
            logger.info(f"Downloading PDF: {pdf_link}")
            pdf_r = requests.get(pdf_link, headers=self.headers, timeout=15)
            pdf_file = io.BytesIO(pdf_r.content)
            reader = PdfReader(pdf_file)
            
            # 3. Extract Text & Regex
            for page in reader.pages:
                text = page.extract_text()
                lines = text.split('\n')
                current_team_event_id = None
                
                for line in lines:
                    line_clean = line.strip()
                    
                    # Detect Team (Simplified check against our team map)
                    found_new_team = False
                    for (sport, t_name), evt_id in team_map.items():
                        if sport == 'basketball' and len(t_name) > 3 and t_name.lower() in line_clean.lower():
                            current_team_event_id = evt_id
                            found_new_team = True
                            break
                    
                    if found_new_team: continue
                    if not current_team_event_id: continue
                    
                    # Check for Status
                    status_found = None
                    for s in ['Out', 'Questionable', 'Doubtful', 'Probable']:
                        if s in line:
                            status_found = s
                            break
                    
                    if status_found:
                        # Split name from status (Naive parse)
                        # Format: "PlayerName Status Reason"
                        parts = line.split(status_found)
                        player_name = parts[0].strip().replace(',', '') 
                        
                        if current_team_event_id not in output_dict: 
                            output_dict[current_team_event_id] = {}
                            
                        output_dict[current_team_event_id][player_name] = {
                            'status': status_found,
                            'reliability': RELIABILITY_OFFICIAL,
                            'source': 'NBA_Official'
                        }
                        
        except Exception as e:
            logger.error(f"NBA Injury Fetch Failed: {e}")

    # --- NFL: NFL.com Scraping ---
    def _process_nfl(self, team_map, output_dict):
        logger.info("Fetching NFL.com Injuries...")
        try:
            url = "https://www.nfl.com/injuries/"
            r = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.content, 'html.parser')
            
            sections = soup.find_all('section', class_='nfl-o-injury-report__club')
            
            for section in sections:
                team_header = section.find('span', class_='nfl-o-injury-report__club-name')
                if not team_header: continue
                
                team_name = self._normalize_team(team_header.text)
                
                # Find Event ID
                event_id = team_map.get(('americanfootball', team_name))
                if not event_id: continue
                
                if event_id not in output_dict: output_dict[event_id] = {}
                
                rows = section.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 3: continue
                    
                    player = cols[0].find('span', class_='nfl-c-player__name')
                    status = cols[2].text.strip() # "Game Status" column
                    
                    if player and status:
                        p_name = player.text.strip()
                        output_dict[event_id][p_name] = {
                            'status': status,
                            'reliability': RELIABILITY_OFFICIAL,
                            'source': 'NFL.com'
                        }

        except Exception as e:
            logger.error(f"NFL Injury Fetch Failed: {e}")

    # --- NHL: ESPN Scraping ---
    def _process_nhl(self, team_map, output_dict):
        logger.info("Fetching NHL Injuries (ESPN)...")
        try:
            url = "https://www.espn.com/nhl/injuries"
            # Using pandas read_html for structure
            # Note: ESPN may block non-browser UAs, headers are critical
            r = requests.get(url, headers=self.headers)
            
            # Use Beautiful Soup to find team sections
            soup = BeautifulSoup(r.content, 'html.parser')
            team_divs = soup.find_all('div', class_='Table__Title')
            
            for div in team_divs:
                team_name = self._normalize_team(div.text)
                event_id = team_map.get(('icehockey', team_name))
                if not event_id: continue
                
                table = div.find_next('table')
                if not table: continue
                
                # Parse table
                df = pd.read_html(str(table))[0]
                if event_id not in output_dict: output_dict[event_id] = {}
                
                for _, row in df.iterrows():
                    # Expected Columns: NAME, STATUS, DATE, COMMENT
                    if 'NAME' not in row: continue
                    
                    p_name = row['NAME']
                    status = row['STATUS']
                    
                    output_dict[event_id][p_name] = {
                        'status': status,
                        'reliability': RELIABILITY_HIGH,
                        'source': 'ESPN'
                    }

        except Exception as e:
            logger.error(f"NHL Injury Fetch Failed: {e}")

    # --- NCAA: Covers.com ---
    def _process_ncaaf(self, team_map, output_dict):
        logger.info("Fetching NCAA Football Injuries (Covers)...")
        try:
            url = "https://www.covers.com/sport/football/ncaaf/injuries"
            r = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.content, 'html.parser')
            
            # Covers uses 'covers-injury-team-list' containers
            cards = soup.find_all('div', class_='covers-injury-team-list')
            
            for card in cards:
                header = card.find('a', class_='covers-injury-team-header-link')
                if not header: continue
                
                team_name = self._normalize_team(header.text)
                event_id = team_map.get(('americanfootball', team_name))
                if not event_id: continue
                
                table = card.find('table')
                if not table: continue
                
                df = pd.read_html(str(table))[0]
                if event_id not in output_dict: output_dict[event_id] = {}
                
                for _, row in df.iterrows():
                    p_name = row.get('Player', '')
                    status = row.get('Status', '')
                    
                    if p_name:
                        output_dict[event_id][p_name] = {
                            'status': status,
                            'reliability': RELIABILITY_MEDIUM,
                            'source': 'Covers'
                        }

        except Exception as e:
            logger.error(f"NCAA Injury Fetch Failed: {e}")

    def _normalize_team(self, team_name: str) -> str:
        """
        Normalize team names for fuzzy matching.
        'Los Angeles Lakers' -> 'lakers'
        'New York Jets' -> 'jets'
        """
        if not team_name: return ""
        t = team_name.lower().replace('.', '')
        
        parts = t.split()
        # Take the last word usually (Lakers, Celtics, Jets)
        if len(parts) > 1:
            return parts[-1] 
        return t
