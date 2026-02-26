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
from tech import TECH
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
    
    config['updated_count'] += inserted_count
    with open(STATS_FILE, "w") as f: 
        json.dump(config, f, ensure_ascii=False, indent=4)
        
class UpdateScrapper:
    def __init__(self, email, password, thread_id):
        self.email = email
        self.password = password
        self.thread_id = thread_id
        log_folder = os.path.join(LOG_BASE, f'update_logs/thread_{thread_id}')
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
        self.crunch_organization_details = self.db['CorrectData']
        # self.crunch_organization_details = self.db['OrganiztionDetails']
        # self.CorrectData = self.db['CorrectData']
        self.corrupt_data = self.db['CorruptData']
        self.crunch_raw_urls = self.db['CrunchURLs']
        
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
                {"$inc": {"updated_count": count}}
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
    
    def read_crunch_details(self, batch_size=1, exclude_corrupted=True):
        if batch_size <= 0:
            return []
        
        try:
            current_time = datetime.now(self.tz)
            thirty_days_ago = current_time - timedelta(days=30)
            seven_days_ago = current_time - timedelta(days=7)
            
            organizations = []
            bulk_operations = []
            
            # Base exclusion filter
            base_filter = {}
            if exclude_corrupted:
                base_filter["corrupted_data"] = {"$ne": True}
                
                
            # condition = {"organization_url" : "https://www.crunchbase.com/organization/loreal"}
            # pipeline = [
            #         {"$match": condition},
            #         {"$sample": {"size": batch_size - len(organizations)}}
            #     ]
            # organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
            # return organizations
            
            # PRIORITY 1: Blank descriptions
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "$or": [
                        {"summary.details.description": ""},
                        {"summary.details.description": None},
                        {"summary.details.description": {"$exists": False}}
                    ]
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
                self.logger.log(f"Thread-{self.thread_id}: Found {len(organizations)} organizations with blank descriptions---------1")

            # if len(organizations) < batch_size:
            #     condition = {
            #         **base_filter,
            #         "summary.about.founded_at": {
            #                     "$in": [
            #                         "Founded 2020",
            #                         "Founded 2021", 
            #                         "Founded 2022",
            #                         "Founded 2023",
            #                         "Founded 2024",
            #                         "Founded 2025"
            #                     ]
            #                 },
            #         "$or": [
            #             {"updated_at": {"$lt": thirty_days_ago}},
            #             {"updated_at": None},
            #             {"updated_at": {"$exists": False}}
            #         ]
            #     }
            #     pipeline = [
            #         {"$match": condition},
            #         {"$sample": {"size": batch_size - len(organizations)}}
            #     ]
            #     organizations = []
            #     organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
            #     [ i['summary']['about']['founded_at'] for i in organizations]
            #     print(f"Thread-{self.thread_id}: Found {len(organizations)} organizations with blank descriptions",'---------2')
                
            
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "financial.funding_round.total_funding_amount":"obfuscated obfuscation",
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
                self.logger.log(f"Thread-{self.thread_id}: Found {len(organizations)} organizations with founded_at ---------3")
                
                
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "summary.about.founded_at": {
                                "$regex": "(2020|2021|2022|2023|2024|2025)" 
                            },
                    "$or": [
                        {"updated_at": {"$lt": thirty_days_ago}},
                        {"updated_at": None},
                        {"updated_at": {"$exists": False}}
                    ]
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
                self.logger.log(f"Thread-{self.thread_id}: Found {len(organizations)} organizations with founded_at ---------3")
                
            
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "summary.details.founded_date": {
                                "$regex": "(2020|2021|2022|2023|2024|2025)" 
                            },
                    "$or": [
                        {"updated_at": {"$lt": thirty_days_ago}},
                        {"updated_at": None},
                        {"updated_at": {"$exists": False}}
                    ]
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
                self.logger.log(f"Thread-{self.thread_id}: Found {len(organizations)} organizations with founded_date---------4")
            
            
            
            # # PRIORITY : update data which have been founded after 2020
            # if len(organizations) < batch_size:
            #     condition = {
            #         **base_filter,
            #         "$or" : [
            #             {
            #                 "summary.about.founded_at": {
            #                     "$in": [
            #                     "Founded 2020",
            #                     "Founded 2021", 
            #                     "Founded 2022",
            #                     "Founded 2023",
            #                     "Founded 2024",
            #                     "Founded 2025"
            #                     ]
            #                 }
            #             },
            #             {
            #                 "summary.about.founded_at": { 
            #                     "$regex": "(2020|2021|2022|2023|2024|2025)" 
            #                     }
            #                 },
            #             {
            #                 "summary.details.founded_date": { 
            #                     "$regex": "(2020|2021|2022|2023|2024|2025)" 
            #                     }
            #                 }
            #         ],
            #         "$or": [
            #             {"updated_at": {"$lt": thirty_days_ago}},
            #             {"updated_at": None},
            #             {"updated_at": {"$exists": False}}
            #         ]
            #     }
            #     pipeline = [
            #         {"$match": condition},
            #         {"$sample": {"size": batch_size - len(organizations)}}
            #     ]
            #     organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))

            # PRIORITY 2: Stale financial data
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "financial": {"$exists": True, "$nin": [{}, None]},
                    "summary.details.description": {"$exists": True, "$ne": "", "$ne": None},
                    # "updated_at": {"$lt": thirty_days_ago},
                    "$or": [
                        {"updated_at": {"$lt": seven_days_ago}},
                        {"updated_at": None},
                        {"updated_at": {"$exists": False}}
                    ]
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
            
            # PRIORITY 3: Obfuscated fields
            if len(organizations) < batch_size:
                condition = {
                    **base_filter,
                    "summary.details.description": {"$exists": True, "$ne": "", "$ne": None},
                    "$or": [
                        {"summary.about.founded_at": {"$regex": "obfuscate", "$options": "i"}},
                        {"financial.funding_round.table.1.money_raised": {"$regex": "obfuscate", "$options": "i"}}
                    ]
                }
                pipeline = [
                    {"$match": condition},
                    {"$sample": {"size": batch_size - len(organizations)}}
                ]
                organizations.extend(list(self.crunch_organization_details.aggregate(pipeline)))
            
            # PRIORITY 4: Flagged for update
            if len(organizations) < batch_size:
                for _ in range(3):
                    if len(organizations) >= batch_size:
                        break
                    
                    remaining = batch_size - len(organizations)
                    url_pipeline = [
                        {"$match": {"update_first": 1}},
                        {"$sample": {"size": remaining}}
                    ]
                    flagged_urls = list(self.crunch_raw_urls.aggregate(url_pipeline))
                    
                    if not flagged_urls:
                        break
                    
                    org_urls = [url_doc["url"] for url_doc in flagged_urls]
                    org_condition = {
                        **base_filter,
                        "organization_url": {"$in": org_urls},
                        "summary.details.description": {"$exists": True, "$ne": "", "$ne": None},
                        "$or": [
                            {"updated_at": {"$lt": thirty_days_ago}},
                            {"updated_at": None},
                            {"updated_at": {"$exists": False}},
                        ]
                    }
                    
                    flagged_orgs = list(self.crunch_organization_details.find(org_condition))
                    organizations.extend(flagged_orgs)
                    
                    bulk_operations.extend([
                        UpdateOne(
                            {"_id": url_doc["_id"]},
                            {"$set": {"update_first": 0, "processed_at": current_time}}
                        )
                        for url_doc in flagged_urls
                    ])

            
            # Remove duplicates
            seen_ids = set()
            unique_orgs = []
            for org in organizations:
                org_id = org.get("_id")
                if org_id and org_id not in seen_ids:
                    seen_ids.add(org_id)
                    unique_orgs.append(org)
            
            organizations = unique_orgs[:batch_size]
            
            # Mark as queued
            if organizations:
                bulk_operations.extend([
                    UpdateOne(
                        {"_id": org["_id"]},
                        {"$set": {"is_updated": 0, "update_queued_at": current_time}}
                    )
                    for org in organizations
                ])
                
                if bulk_operations:
                    try:
                        self.crunch_organization_details.bulk_write(bulk_operations, ordered=False)
                        self.logger.log(f"Thread-{self.thread_id}: Queued {len(organizations)} organizations")
                    except BulkWriteError as e:
                        self.logger.error(f"Thread-{self.thread_id}: Bulk write error: {e.details}")
                    except Exception as e:
                        self.logger.error(f"Thread-{self.thread_id}: Error in bulk write: {e}")
            
            return organizations
            
        except Exception as e:
            self.logger.error(f"Thread-{self.thread_id}: Error reading organizations: {e}")
            return []
        
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
                elif response.status_code == 404:
                    return response
                else:
                    self.logger.error(f"Thread-{self.thread_id}: Failed to fetch {url} with status {response.status_code}")
            except Exception as e:
                self.logger.error(f"Thread-{self.thread_id}: Error fetching {url}: {e}")
            self.random_sleep(5,10)
        return False
    
    def scrape_organization(self, org_url, org_name):
        """Scrape all data for an organization"""
        try:
            data = {}
            self.random_sleep()
            self.logger.log(f"Thread-{self.thread_id}: Fetching summary for {org_name}")
            summary_response = self.get_requests(f"{org_url}")
            if not summary_response :
                return None
            if summary_response.status_code == 404: 
                return 404
            
            if summary_response.status_code != 200:
                self.logger.error(f"Thread-{self.thread_id}: Failed to fetch summary for {org_name} with status {summary_response.status_code}")
                return None
            
            with open('summary_response.html', 'w', encoding='utf-8') as f: f.write(summary_response.text)
            
            summary_processor = SUMMARY()
            summary_data, financial_url, signals_and_news_url, investment_url, tech_url = summary_processor.summary_process_logic(summary_response, {})
            data.update(summary_data)
            # Scrape financial details
            if financial_url :
                self.random_sleep()
                self.logger.log(f"Thread-{self.thread_id}: Fetching financial details for {org_name}")
                finance_response = self.get_requests(f"{org_url}/financial_details")
                if not finance_response :
                    return None
                
                if finance_response.status_code != 200:
                    self.logger.error(f"Thread-{self.thread_id}: Failed to fetch financial details for {org_name} with status {finance_response.status_code}")
                    return None
                
                finance_processor = FINANCIAL()
                finance_data = finance_processor.financial_process_logic(finance_response, {})
                data.update(finance_data)
            
            # Scrape news
            if signals_and_news_url:
                self.random_sleep()
                self.logger.log(f"Thread-{self.thread_id}: Fetching news for {org_name}")
                news_response = self.get_requests(f"{org_url}/news_and_analysis")
                if not news_response :
                    return None
                
                if news_response.status_code != 200:
                    self.logger.error(f"Thread-{self.thread_id}: Failed to fetch news for {org_name} with status {news_response.status_code}")
                    return None
                
                news_processor = NEWS()
                news_data = news_processor.news_process_logic(news_response, {})
                data.update(news_data)
            
            # Scrape techs
            if signals_and_news_url:
                self.random_sleep()
                self.logger.log(f"Thread-{self.thread_id}: Fetching tech details for {org_name}")
                tech_response = self.get_requests(f"{org_url}/tech_details")
                if not tech_response :
                    return None
                
                if tech_response.status_code != 200:
                    self.logger.error(f"Thread-{self.thread_id}: Failed to fetch tech for {org_name} with status {tech_response.status_code}")
                    return None
                
                tech_processor = TECH()
                tech_data = tech_processor.tech_process_logic(tech_response, {})
                data.update(tech_data)
            return data
            
        except Exception as e:
            self.logger.error(f"Thread-{self.thread_id}: Error scraping {org_name}: {e}")
            return None
    
    def update_organization(self, org_id, scraped_data, is_corrupt = False):
        """Update organization in database, handling corrupt data separately"""
        try:
            current_time = datetime.now(self.tz)
            
            if is_corrupt:
                # Handle corrupted data
                corrupt_data = {**scraped_data,"corrupted_data": True,"detected_at": current_time,"original_collection": "crunch_organization_details"}
                if not self.corrupt_data.find_one({"organization_url": scraped_data.get("organization_url")}):
                    self.corrupt_data.insert_one(corrupt_data)
                    self.crunch_organization_details.insert_one(corrupt_data)
                else:
                    self.crunch_organization_details.update_one({"organization_url": scraped_data.get("organization_url")},{"$set": {"corrupted_data": True,"last_processed_at": current_time,"corruption_detected_at": current_time}})

                update_data = {
                    "corrupted_data": True,
                    "last_processed_at": current_time,
                    "corruption_detected_at": current_time
                }
                
                self.logger.warning(
                    f"Thread-{self.thread_id}: Corrupted data detected for org {org_id}. "
                    f"Stored in corrupt_data collection."
                )
            else:
                # Normal update for clean data
                update_data = {
                    **scraped_data,
                    "is_updated": 1,
                    "updated_at": current_time,
                    "last_processed_at": current_time,
                    "corrupted_data": False  # Explicitly mark as clean
                }
            
            # Perform the update
            result = self.crunch_organization_details.update_one(
                {"_id": org_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                self.save_stats_count(1)
                status = "flagged as corrupted" if is_corrupt else "updated successfully"
                self.logger.log(f"Thread-{self.thread_id}: Organization {org_id} {status}")
                return True
            else:
                self.logger.error(
                    f"Thread-{self.thread_id}: No changes made for organization {org_id}. "
                    f"Document may not exist."
                )
                return False
                    
        except Exception as e:
            self.logger.error(
                f"Thread-{self.thread_id}: Error updating organization {org_id}: {e}"
            )
            return False
        
    
    def run(self, batch_size=None, max_batches=None):
        batch_size = batch_size or int(os.environ.get('SCRAPER_BATCH_SIZE_UPDATE', 10))
        max_batches = max_batches or int(os.environ.get('SCRAPER_MAX_BATCHES_UPDATE', 50))
        """Main execution loop"""
        if not self.login():
            self.logger.error(f"Thread-{self.thread_id}: Cannot start - login failed")
            return
        
        self.logger.log(f"Thread-{self.thread_id}: Starting UPDATE scraping")
        batch_num = 0
        for batch_num in range(max_batches):
            try:
                batch_num += 1
                self.logger.log(f"Thread-{self.thread_id}: Processing batch {batch_num }")
                
                # Get organizations to update
                organizations = self.read_crunch_details(batch_size)
                
                if not organizations:
                    self.logger.log(f"Thread-{self.thread_id}: No more organizations to update")
                    break
                
                # Process each organization
                success_count = 0
                for org in organizations:
                    org_url = org.get('organization_url', '')
                    org_name = org.get('organization_name', 'Unknown')
                    org_id = org.get('_id')
                    if not org_url or not org_id or not org_name:
                        self.update_organization(org_id, org,is_corrupt = True)
                        self.logger.error(f"Thread-{self.thread_id}: Missing data for organization {org}")
                        continue
                    
                    self.logger.log(f"Thread-{self.thread_id}: Processing {org_name}")
                    
                    scraped_data = self.scrape_organization(org_url, org_name)
                    
                    if scraped_data == 404 or ( scraped_data['summary']['details'].get('description') in [None,''] ):
                        self.logger.log(f"Thread-{self.thread_id}: Organization {org_name} not found (404). Marking as updated.")
                        self.update_organization(org_id, org,is_corrupt = True)
                        continue
                    
                    if scraped_data:
                        if self.update_organization(org_id, scraped_data):
                            success_count += 1
                    
                    self.random_sleep(2, 5)
                
                self.logger.log(f"Thread-{self.thread_id}: Batch {batch_num + 1} completed - {success_count}/{len(organizations)} successful")
                
            except Exception as e:
                self.logger.error(f"Thread-{self.thread_id}: Error in batch {batch_num + 1}: {e}")
                time.sleep(30)
        
        self.logger.log(f"Thread-{self.thread_id}: UPDATE scraping completed")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python update_scrapper.py <email> <password> <thread_id>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    thread_id = sys.argv[3]
    scrapper = UpdateScrapper(email, password, thread_id)
    scrapper.run(batch_size=10, max_batches=50)