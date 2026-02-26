import re
import threading
import time
import json
import os
from datetime import datetime
from pymongo import MongoClient
from logger import CustomLogger
import subprocess
import sys
import argparse
import random

# ── Defaults (used when no --config-file is provided) ────────────────────────
DEFAULT_MONGO_URI = "mongodb://admin9:i38kjmx35@94.130.33.235:27017/?authSource=admin&authMechanism=SCRAM-SHA-256&readPreference=primary&tls=true&tlsAllowInvalidCertificates=true&directConnection=true"
DEFAULT_LOG_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Hardcoded accounts — only used if no config file
DEFAULT_ACCOUNTS = [
    {"email": "rikenkhadela22@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+1@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+2@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+3@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+4@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+5@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+6@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+7@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+8@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+9@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+10@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+11@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+12@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+13@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+14@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+15@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+16@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+17@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+18@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+19@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+20@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+21@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+22@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+23@gmail.com", "password": "Riken@123", "active": True},
    {"email": "rikenkhadela22+24@gmail.com", "password": "Riken@123", "active": True},
]


def load_config(config_path):
    """Load config from a JSON file written by the scraper manager."""
    with open(config_path, 'r') as f:
        return json.load(f)


def random_sleep(min_seconds, max_seconds, log=None):
    """Sleep for a random duration between min_seconds and max_seconds"""
    duration = random.uniform(min_seconds, max_seconds)
    msg = f"Sleeping for {duration:.2f} seconds"
    if log:
        log.log(msg)
    time.sleep(duration)


def parse_arguments():
    parser = argparse.ArgumentParser(description='Crunchbase Scraping Manager')
    parser.add_argument('--update', type=int, default=0, help='Number of accounts for update scraper', required=False)
    parser.add_argument('--new', type=int, default=0, help='Number of accounts for new scraper', required=False)
    parser.add_argument('--config-file', type=str, default=None, help='Path to JSON config file (written by manager)')
    parser.add_argument('--mode', type=str, choices=['all', 'new_only', 'update_only'], default='all',
                        help='Run mode: all (both scrapers), new_only, update_only')
    return parser.parse_args()


class ThreadManager:
    def __init__(self, accounts, update_threads=None, new_threads=None,
                 mongo_uri=None, log_base=None, config=None):
        self.accounts = accounts
        self.active_threads = []
        self.lock = threading.Lock()
        self.mongo_uri = mongo_uri or DEFAULT_MONGO_URI
        self.log_base = log_base or DEFAULT_LOG_BASE
        self.config = config or {}
        self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=50000)
        self.db = self.client['STARTUPSCRAPERDATA']
        self.manual_update_threads = update_threads
        self.manual_new_threads = new_threads

        os.makedirs(os.path.join(self.log_base, "main_logs"), exist_ok=True)
        self.logger = CustomLogger(log_folder=os.path.join(self.log_base, "main_logs"))

    def get_active_accounts(self):
        """Get list of active accounts"""
        return [acc for acc in self.accounts if acc.get('active', False)]

    def calculate_thread_distribution(self, active_count):
        """
        Calculate thread distribution based on active accounts
        Rules:
        - 1 account: alternating (1 update, then 1 new)
        - 2 accounts: 1 update, 1 new
        - 3 accounts: 2 update, 1 new
        - 4+ accounts: all update, 0 new (unless manual config)
        Max 5 threads per type
        """
        # If manual configuration provided, use it
        if self.manual_update_threads is not None or self.manual_new_threads is not None:
            update = self.manual_update_threads if self.manual_update_threads is not None else 0
            new = self.manual_new_threads if self.manual_new_threads is not None else 0

            total_needed = update + new
            if total_needed > active_count:
                self.logger.error(f"Not enough accounts! Need {total_needed}, have {active_count}")
                self.logger.log(f"Adjusting: update={min(update, active_count)}, new={max(0, active_count - update)}")
                update = min(update, active_count)
                new = max(0, active_count - update)

            return {'update': update, 'new': new, 'alternating': False}

        # Default automatic distribution
        if active_count == 1:
            return {'update': 1, 'new': 0, 'alternating': True}
        elif active_count == 2:
            return {'update': 1, 'new': 1, 'alternating': False}
        elif active_count == 3:
            return {'update': 2, 'new': 1, 'alternating': False}
        else:
            update_threads = active_count
            new_threads = 0
            return {'update': update_threads, 'new': new_threads, 'alternating': False}

    def start_scraper_thread(self, script_name, account, thread_id):
        """Start a scraper thread"""
        try:
            self.logger.log(f"Starting {script_name} with account {account['email']} (Thread-{thread_id})")

            # Build command with optional config extras
            cmd = [sys.executable, script_name,
                   account['email'],
                   account['password'],
                   str(thread_id)]

            # Pass log_base and mongo_uri via environment
            env = os.environ.copy()
            env['SCRAPER_LOG_BASE'] = self.log_base
            env['SCRAPER_MONGO_URI'] = self.mongo_uri

            # Pass batch settings via environment if available from config
            if self.config.get('batch_size_new'):
                env['SCRAPER_BATCH_SIZE_NEW'] = str(self.config['batch_size_new'])
            if self.config.get('batch_size_update'):
                env['SCRAPER_BATCH_SIZE_UPDATE'] = str(self.config['batch_size_update'])
            if self.config.get('max_batches_new'):
                env['SCRAPER_MAX_BATCHES_NEW'] = str(self.config['max_batches_new'])
            if self.config.get('max_batches_update'):
                env['SCRAPER_MAX_BATCHES_UPDATE'] = str(self.config['max_batches_update'])

            # Run from the script's directory
            script_dir = os.path.dirname(os.path.abspath(script_name)) or os.path.dirname(os.path.abspath(__file__))

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=script_dir,
            )

            return process
        except Exception as e:
            self.logger.error(f"Error starting {script_name}: {e}")
            return None

    def monitor_thread(self, process, script_name, thread_id):
        """Monitor a thread and handle its completion"""
        try:
            stdout, stderr = process.communicate(timeout=3600)  # 1 hour timeout

            if process.returncode == 0:
                self.logger.log(f"{script_name} Thread-{thread_id} completed successfully")
            else:
                self.logger.error(f"{script_name} Thread-{thread_id} failed with code {process.returncode}")
                if stderr:
                    self.logger.error(f"Error output: {stderr.decode()}")

        except subprocess.TimeoutExpired:
            self.logger.error(f"{script_name} Thread-{thread_id} timeout - killing process")
            process.kill()
        except Exception as e:
            self.logger.error(f"Error monitoring {script_name} Thread-{thread_id}: {e}")

    def run_alternating_mode(self, account):
        """Run alternating mode for single account"""
        self.logger.log("Running in ALTERNATING mode (1 account)")
        cycle = 0

        while True:
            try:
                if cycle % 2 == 0:
                    # Run update scraper
                    self.logger.log(f"Cycle {cycle}: Running UPDATE scraper")
                    process = self.start_scraper_thread('update_scrapper.py', account, 1)
                else:
                    # Run new scraper
                    self.logger.log(f"Cycle {cycle}: Running NEW scraper")
                    process = self.start_scraper_thread('new_scrapper.py', account, 1)

                if process:
                    self.monitor_thread(process,
                                      'update_scrapper.py' if cycle % 2 == 0 else 'new_scrapper.py',
                                      1)

                cycle += 1
                time.sleep(5)  # Small delay between cycles

            except KeyboardInterrupt:
                self.logger.log("Alternating mode interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Error in alternating mode: {e}")
                time.sleep(30)

    def run_parallel_mode(self, active_accounts, distribution):
        """Run parallel mode with multiple threads"""
        self.logger.log(f"Running in PARALLEL mode: {distribution['update']} update threads, {distribution['new']} new threads")

        while True:
            try:
                threads = []
                account_index = 0

                # Start update threads
                for i in range(distribution['update']):
                    if account_index < len(active_accounts):
                        account = active_accounts[account_index]
                        process = self.start_scraper_thread('update_scrapper.py', account, i+1)

                        if process:
                            thread = threading.Thread(
                                target=self.monitor_thread,
                                args=(process, 'update_scrapper.py', i+1)
                            )
                            thread.start()
                            threads.append(thread)

                        account_index += 1

                # Start new threads
                for i in range(distribution['new']):
                    if account_index < len(active_accounts):
                        account = active_accounts[account_index]
                        process = self.start_scraper_thread('new_scrapper.py', account, i+1)

                        if process:
                            thread = threading.Thread(
                                target=self.monitor_thread,
                                args=(process, 'new_scrapper.py', i+1)
                            )
                            thread.start()
                            threads.append(thread)

                        account_index += 1

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                self.logger.log("All threads completed. Starting new cycle...")
                time.sleep(10)  # Delay between cycles

            except KeyboardInterrupt:
                self.logger.log("Parallel mode interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Error in parallel mode: {e}")
                time.sleep(30)

    def start(self):
        """Main entry point"""
        self.logger.log("=" * 80)
        self.logger.log("Starting Crunchbase Scraping Manager")
        self.logger.log("=" * 80)
        for _ in range(10):
            active_accounts = self.get_active_accounts()

            if not active_accounts:
                self.logger.error("No active accounts found! Please activate at least one account.")
                return

            self.logger.log(f"Found {len(active_accounts)} active account(s)")

            distribution = self.calculate_thread_distribution(len(active_accounts))
            self.logger.log(f"Thread distribution: {distribution}")

            if distribution.get('alternating', False):
                # Single account - alternating mode
                self.run_alternating_mode(active_accounts[0])
            else:
                # Multiple accounts - parallel mode
                self.run_parallel_mode(active_accounts, distribution)

            random_sleep(30, 60, self.logger)  # Wait before restarting the loop


if __name__ == "__main__":
    args = parse_arguments()

    # ── Load config from file (written by manager) or use defaults ────────
    config = {}
    accounts = DEFAULT_ACCOUNTS
    mongo_uri = DEFAULT_MONGO_URI
    log_base = DEFAULT_LOG_BASE

    if args.config_file and os.path.isfile(args.config_file):
        config = load_config(args.config_file)
        accounts = config.get('accounts', DEFAULT_ACCOUNTS)
        mongo_uri = config.get('mongo_uri', DEFAULT_MONGO_URI)
        log_base = config.get('log_base_path', DEFAULT_LOG_BASE)
        print(f"[Config] Loaded from {args.config_file}: {len(accounts)} accounts")

    os.makedirs(os.path.join(log_base, "main_logs"), exist_ok=True)
    logger = CustomLogger(log_folder=os.path.join(log_base, "main_logs"))

    update_accounts_ratio = config.get('update_ratio', 0.8)

    # Get active accounts count
    active_accounts = [acc for acc in accounts if acc.get('active', False)]
    accounts_len = len(active_accounts)

    if accounts_len == 0:
        logger.error("No active accounts found!")
        sys.exit(1)

    # ── Determine update/new split ────────────────────────────────────────
    update_acc = args.update or config.get('update_account_count', 0)
    new_acc = args.new or config.get('new_account_count', 0)

    # Mode override from config or CLI
    mode = args.mode or config.get('mode', 'all')

    if mode == 'new_only':
        update_acc = 0
        new_acc = new_acc or accounts_len
    elif mode == 'update_only':
        new_acc = 0
        update_acc = update_acc or accounts_len

    # If no arguments provided, split accounts using ratio
    if not update_acc and not new_acc:
        update_acc = int(accounts_len * update_accounts_ratio)
        new_acc = accounts_len - update_acc

    # If only update provided, use remaining for new
    elif update_acc and not new_acc:
        new_acc = max(0, accounts_len - update_acc)

    # If only new provided, use remaining for update
    elif new_acc and not update_acc:
        update_acc = max(0, accounts_len - new_acc)

    # Both provided - validate
    else:
        total = update_acc + new_acc
        if total > accounts_len:
            logger.error(f"Not enough accounts! Requested {total}, have {accounts_len}")
            sys.exit(1)

    logger.log(f"Configuration: {update_acc} update threads, {new_acc} new threads (Total active accounts: {accounts_len})")
    logger.log(f"Mode: {mode}")

    manager = ThreadManager(
        accounts=accounts,
        update_threads=update_acc,
        new_threads=new_acc,
        mongo_uri=mongo_uri,
        log_base=log_base,
        config=config,
    )
    try:
        manager.start()
    except KeyboardInterrupt:
        logger.log("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.log("Main script terminated")