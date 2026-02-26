from bs4 import BeautifulSoup
from curl_cffi import requests
import json
import time
import random
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, ConnectionFailure
from logger import CustomLogger
from summery import SUMMARY
from news import NEWS
from finance import FINANCIAL
import pytz
import os

MONGO_URI = os.environ.get(
    'SCRAPER_MONGO_URI',
    "mongodb://admin9:i38kjmx35@localhost:27017/?authSource=admin&authMechanism=SCRAM-SHA-256&readPreference=primary&tls=true&tlsAllowInvalidCertificates=true&directConnection=true"
)
LOG_BASE = os.environ.get('SCRAPER_LOG_BASE', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'))
STATS_FILE = os.path.join(LOG_BASE, 'run_status.json')
import json
def save_run_stats(inserted_count):
    
    with open(STATS_FILE, "r") as f: 
        config = json.load(f)
    
    config['new_added_count'] += inserted_count
    with open(STATS_FILE, "w") as f: 
        json.dump(config, f, ensure_ascii=False, indent=4)
        
class NewScrapper:
    def __init__(self, email, password, thread_id):
        self.email = email
        self.password = password
        self.thread_id = thread_id
        log_folder = os.path.join(LOG_BASE, f'new_scrapper/thread_{thread_id}')
        os.makedirs(log_folder, exist_ok=True)
        self.logger = CustomLogger(log_folder=log_folder)
        
        # MongoDB setup
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=50000)
            self.client.admin.command('ping')
            self.logger.log(f"Thread-{self.thread_id}: MongoDB connection established")
        except ConnectionFailure as e:
            self.logger.error(f"Thread-{self.thread_id}: MongoDB connection failed: {e}")
            raise
        
        self.db = self.client['STARTUPSCRAPERDATA']
        self.crunch_organization_details = self.db['OrganiztionDetails']
        self.crunch_raw_urls = self.db['CrunchURLS']
        
        # Session setup
        self.session = None
        self.proxy = self.get_proxy()
        self.tz = pytz.timezone('UTC')
    
    def save_stats_count(self, count):
        """Save run statistics to the MongoDB collection"""    
        try:
            stats_collection = self.db['run_stats']
            stats_collection.update_one(
                {"_id": "update_run_stats"},
                {"$inc": {"new_added_organiztion": count}}
            )
        except Exception as e:
            self.logger.error(f"Thread-{self.thread_id}: Failed to save stats: {e}")

        
    def get_proxy(self):
        """Get random proxy"""
        plist = [
            "37.48.118.90:13082",
            "83.149.70.159:13082"
        ]
        prx = random.choice(plist)
        return {
            'http': 'http://' + prx,
            'https': 'http://' + prx
        }
    
    def login(self):
        """Login to Crunchbase"""
        for _ in range(10):
            self.random_sleep(5,10)
            try:
                self.session = requests.Session()
                login_response = self.session.post(
                    "https://www.crunchbase.com/v4/cb/sessions",
                    json={
                        "email": self.email,
                        "password": self.password
                    },
                    impersonate="chrome110",
                    proxies=self.proxy,
                    timeout=30
                )
                
                if login_response.status_code == 201:
                    self.logger.log(f"Thread-{self.thread_id}: Login successful for {self.email}")
                    return True
                else:
                    self.logger.error(f"Thread-{self.thread_id}: Login failed with status {login_response.status_code}")
                    # return False
                    
            except Exception as e:
                self.logger.error(f"Thread-{self.thread_id}: Login error: {e}")
        return False
    
    def random_sleep(self, a=3, b=7):
        """Sleep for random duration"""
        random_int = random.randint(a, b)
        self.logger.log(f"Thread-{self.thread_id}: Sleeping for {random_int} seconds")
        time.sleep(random_int)
    
    def read_crunch_details_new(self, numberofrecords=10):
        """Get new URLs to scrape with priority system"""
        current_time = datetime.now(self.tz)
        one_month_ago = current_time - timedelta(days=30)
        
        # Get existing URLs to avoid duplicates
        existing_urls = set(
            doc["organization_url"]
            for doc in self.crunch_organization_details.find(
                {"organization_url": {"$ne": None}}, 
                {"organization_url": 1}
            )
        )
        
        def filter_out_existing(docs):
            return [doc for doc in docs if doc.get("url") not in existing_urls]
        
        final_docs = []
        
        # Priority 1: Only status = pending
        self.logger.log(f"Thread-{self.thread_id}: Fetching Priority 1 URLs (status=pending)")
        priority1_match = {"status": "pending"}
        docs1 = list(self.crunch_raw_urls.aggregate([
            {"$match": priority1_match},
            {"$sample": {"size": numberofrecords * 2}}
        ]))
        docs1 = filter_out_existing(docs1)
        final_docs.extend(docs1[:numberofrecords])
        
        # Priority 2: is_read=0 or status=pending AND created_at < one_month_ago
        if len(final_docs) < numberofrecords:
            remaining = numberofrecords - len(final_docs)
            self.logger.log(f"Thread-{self.thread_id}: Fetching Priority 2 URLs (old pending/unread)")
            priority2_match = {
                "$and": [
                    {"$or": [{"is_read": 0}, {"status": "pending"}]},
                    {"$or": [
                        {"created_at": {"$lt": one_month_ago}},
                        {"created_at": {"$exists": False}}
                    ]}
                ]
            }
            docs2 = list(self.crunch_raw_urls.aggregate([
                {"$match": priority2_match},
                {"$sample": {"size": remaining * 2}}
            ]))
            docs2 = filter_out_existing(docs2)
            final_docs.extend(docs2[:remaining])
        
        # Priority 3: is_read = 0 or status = pending (no date filter)
        if len(final_docs) < numberofrecords:
            remaining = numberofrecords - len(final_docs)
            self.logger.log(f"Thread-{self.thread_id}: Fetching Priority 3 URLs (any pending/unread)")
            priority3_match = {
                "$or": [{"is_read": 0}, {"status": "pending"}]
            }
            docs3 = list(self.crunch_raw_urls.aggregate([
                {"$match": priority3_match},
                {"$sample": {"size": remaining * 2}}
            ]))
            docs3 = filter_out_existing(docs3)
            final_docs.extend(docs3[:remaining])
        
        self.logger.log(f"Thread-{self.thread_id}: Found {len(final_docs)} new URLs to scrape")
        return final_docs
    
    def get_requests(self, url):
        """Get request with retries"""
        for _ in range(10):
            try:
                response = self.session.get(url, impersonate="chrome110", proxies=self.proxy, timeout=30)
                if response.status_code == 200:
                    data = BeautifulSoup(response.text, 'html.parser')
                    if not data.find('button',{"aria-label":"Account"}):
                        self.logger.error(f"Thread-{self.thread_id}: Session may have expired while fetching {url}")
                        self.login()
                        continue
                    
                    return response
                else:
                    self.logger.error(f"Thread-{self.thread_id}: Failed to fetch {url} with status {response.status_code}")
            except Exception as e:
                self.logger.error(f"Thread-{self.thread_id}: Error fetching {url}: {e}")
            self.random_sleep(5,10)
        return False
    
    def scrape_organization(self, org_url, org_name):
        """Scrape all data for a new organization"""
        try:
            data = {}
            
            # Scrape summary
            self.random_sleep()
            self.logger.log(f"Thread-{self.thread_id}: Fetching summary for {org_name}")
            summary_response = self.get_requests(f"{org_url}")
            if not summary_response :
                return None
            
            summary_processor = SUMMARY()
            summary_data, financial_url, signals_and_news_url, investment_url, tech_url = summary_processor.summary_process_logic(summary_response, {})
            data.update(summary_data)
            
            
            # Scrape financial details
            if financial_url:
                self.random_sleep()
                self.logger.log(f"Thread-{self.thread_id}: Fetching financial details for {org_name}")
                finance_response = self.get_requests(f"{org_url}/financial_details")
                if not finance_response :
                    return None
                
                finance_processor = FINANCIAL()
                data.update(finance_processor.financial_process_logic(finance_response, {}))
            
            # Scrape news
            if signals_and_news_url:
                self.random_sleep()
                self.logger.log(f"Thread-{self.thread_id}: Fetching news for {org_name}")
                news_response = self.get_requests(f"{org_url}/news_and_analysis")
                if not news_response :
                    return None
                
                news_processor = NEWS()
                data.update(news_processor.news_process_logic(news_response, {}))
            
            return data
            
        except Exception as e:
            self.logger.error(f"Thread-{self.thread_id}: Error scraping {org_name}: {e}")
            return None
    
    def extract_org_name_from_url(self, url):
        """Extract organization name from URL"""
        try:
            # URL format: https://www.crunchbase.com/organization/loreal
            parts = url.rstrip('/').split('/')
            return parts[-1].replace('-', ' ').title()
        except:
            return "Unknown"
    
    def save_new_organization(self, url_doc, scraped_data):
        """Save new organization to database"""
        try:
            current_time = datetime.now(self.tz)
            
            org_name = self.extract_org_name_from_url(url_doc['url'])
            
            # Prepare document
            new_org = {
                "category": "Organization",
                "url_id": url_doc.get('_id', {}),
                "organization_url": url_doc['url'],
                "organization_name": org_name,
                "organization_logo": "",  # Will be filled by scraper
                **scraped_data,
                "is_updated": 1,
                "count": 0,
                "google_page": url_doc.get('google_page', 1),
                "index": url_doc.get('index', 0),
                "search_keyword": {},
                "search_sector": url_doc.get('sector', '').split('|') if url_doc.get('sector') else {},
                "search_tag": url_doc.get('tag', '').split('|') if url_doc.get('tag') else {},
                "runner_info": {
                    "summary_script": current_time,
                },
                "parentIndustry": [],
                "updated_at": current_time,
                "last_processed_at": current_time,
                "created_at": current_time
            }
            # Insert new organization
            result = self.crunch_organization_details.insert_one(new_org)
            
            # Update raw URL status
            self.crunch_raw_urls.update_one(
                {"_id": url_doc['_id']},
                {"$set": {
                    "is_read": 1,
                    "status": "completed",
                    "processed_at": current_time
                }}
            )
            
            self.logger.log(f"Thread-{self.thread_id}: Successfully saved new organization: {org_name}")
            self.save_stats_count(1)
            return True
            
        except Exception as e:
            self.logger.error(f"Thread-{self.thread_id}: Error saving organization: {e}")
            
            # Mark URL as failed
            try:
                self.crunch_raw_urls.update_one(
                    {"_id": url_doc['_id']},
                    {"$set": {
                        "status": "failed",
                        "error": str(e),
                        "failed_at": datetime.now(self.tz)
                    }}
                )
            except:
                pass
            
            return False
    
    def run(self, batch_size=None, max_batches=None):
        batch_size = batch_size or int(os.environ.get('SCRAPER_BATCH_SIZE_NEW', 10))
        max_batches = max_batches or int(os.environ.get('SCRAPER_MAX_BATCHES_NEW', 10))
        """Main execution loop"""
        if not self.login():
            self.logger.error(f"Thread-{self.thread_id}: Cannot start - login failed")
            return
        
        self.logger.log(f"Thread-{self.thread_id}: Starting NEW scraping")
        for batch_num in range(max_batches):
            try:
                self.logger.log(f"Thread-{self.thread_id}: Processing batch {batch_num + 1}/{max_batches}")
                
                # Get new URLs to scrape
                url_docs = self.read_crunch_details_new(batch_size)
                
                if not url_docs:
                    self.logger.log(f"Thread-{self.thread_id}: No more URLs to scrape")
                    self.random_sleep(50, 100)
                    break
                
                # Process each URL
                success_count = 0
                for url_doc in url_docs:
                    org_url = url_doc.get('url', '')
                    org_name = self.extract_org_name_from_url(org_url)
                    
                    self.logger.log(f"Thread-{self.thread_id}: Processing NEW: {org_name}")
                    
                    scraped_data = self.scrape_organization(org_url, org_name)
                    
                    if scraped_data:
                        if self.save_new_organization(url_doc, scraped_data):
                            success_count += 1
                    else:
                        # Mark as failed
                        self.crunch_raw_urls.update_one(
                            {"_id": url_doc['_id']},
                            {"$set": {
                                "status": "failed",
                                "failed_at": datetime.now(self.tz)
                            }}
                        )
                    
                    self.random_sleep(2, 5)
                
                self.logger.log(f"Thread-{self.thread_id}: Batch {batch_num + 1} completed - {success_count}/{len(url_docs)} successful")
                
            except Exception as e:
                self.logger.error(f"Thread-{self.thread_id}: Error in batch {batch_num + 1}: {e}")
                time.sleep(30)
                
        self.random_sleep(50, 100)
        self.logger.log(f"Thread-{self.thread_id}: NEW scraping completed")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python new_scrapper.py <email> <password> <thread_id>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    thread_id = sys.argv[3]
    
    scrapper = NewScrapper(email, password, thread_id)
    scrapper.run(batch_size=10, max_batches=10)