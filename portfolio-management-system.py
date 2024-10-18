from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import aiohttp
from aiolimiter import AsyncLimiter
import aiosqlite
from tabulate import tabulate
import time
from datetime import datetime
import logging
from cachetools import TTLCache
import os
from dotenv import load_dotenv
import sys
import json
import math
from aiohttp_retry import RetryClient, ExponentialRetry
import yfinance as yf
import click
import matplotlib.pyplot as plt
from logging.handlers import RotatingFileHandler
from io import BytesIO
import base64
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# Load environment variables from a .env file if present
load_dotenv()

# Set up logging with both console and file handlers
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed logs

# Console handler for INFO and above
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
console_handler.setFormatter(console_formatter)

# File handler for DEBUG and above with rotation
file_handler = RotatingFileHandler('portfolio.log', maxBytes=5*1024*1024, backupCount=3)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
file_handler.setFormatter(file_formatter)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Configuration Constants (can be set via environment variables)
RATE_LIMIT = int(os.getenv('RATE_LIMIT', '10'))  # max requests per second
CACHE_TTL = int(os.getenv('CACHE_TTL', '3600'))  # cache for 1 hour
CACHE_MAXSIZE = int(os.getenv('CACHE_MAXSIZE', '100'))
DATABASE_PATH = os.getenv('DATABASE_PATH', 'positions.db')
RETRY_TOTAL = int(os.getenv('RETRY_TOTAL', '3'))
RETRY_BACKOFF_FACTOR = float(os.getenv('RETRY_BACKOFF_FACTOR', '0.5'))
RETRY_STATUS_CODES = json.loads(os.getenv('RETRY_STATUS_CODES', '[500,502,503,504]'))

# Set up rate limiting
rate_limiter = AsyncLimiter(max_rate=RATE_LIMIT, time_period=1)

# Set up caching with TTLCache
cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL)

# Define Pydantic models for data validation
class Stock(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: str = 'USD'
    usd_price: Optional[float] = 0.0
    timestamp: Optional[int] = 0

class AnalyticsReport(BaseModel):
    total_portfolio_value: float
    average_stock_price: float
    weighted_average_stock_price: float
    number_of_unique_stocks: int
    portfolio_volatility: Optional[float] = None
    portfolio_sharpe_ratio: Optional[float] = None

class Position(BaseModel):
    stock: Stock
    quantity: int

class Portfolio(BaseModel):
    name: str
    positions: List[Position]

    def get_total_value(self) -> float:
        return sum(position.quantity * position.stock.usd_price for position in self.positions if position.stock.usd_price)

# Response Models
class AnalyticsReport(BaseModel):
    analytics_report: str

class OptimizationReport(BaseModel):
    optimization_report: str

class PlotResponse(BaseModel):
    image: str  # Base64-encoded image

class UpdateResponse(BaseModel):
    status: str

class SummaryResponse(BaseModel):
    summary: str

class ReportResponse(BaseModel):
    status: str

# Initialize FastAPI app
app = FastAPI()

# Async function to fetch stock data using yfinance
async def fetch_stock_data(ticker: str) -> Optional[dict]:
    loop = asyncio.get_event_loop()
    try:
        stock = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
        logger.debug(f"Fetched data for {ticker}: {stock}")
        return stock
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None

# Async function to fetch currency exchange rate using yfinance
async def fetch_currency_rate(from_currency: str, to_currency: str) -> Optional[float]:
    loop = asyncio.get_event_loop()
    try:
        currency_pair = f"{from_currency.upper()}{to_currency.upper()}=X"
        rate_info = await loop.run_in_executor(None, lambda: yf.Ticker(currency_pair).info)
        rate = rate_info.get('regularMarketPrice')
        if rate:
            logger.debug(f"Fetched currency rate {from_currency} to {to_currency}: {rate}")
            return rate
        else:
            logger.warning(f"Currency rate {from_currency} to {to_currency} not found.")
            return None
    except Exception as e:
        logger.error(f"Error fetching currency rate {from_currency} to {to_currency}: {e}")
        return None

# Async function to initialize the database with stocks, positions, and snapshots tables
async def init_db(db: aiosqlite.Connection):
    await db.execute('''
        CREATE TABLE IF NOT EXISTS stocks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            name TEXT,
            exchange TEXT,
            currency TEXT
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS positions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            usd_price REAL NOT NULL,
            total_usd_price REAL NOT NULL,
            percentage REAL NOT NULL,
            date INTEGER NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id),
            UNIQUE(stock_id, date)
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date INTEGER NOT NULL UNIQUE,
            total_value REAL NOT NULL
        )
    ''')
    await db.commit()
    logger.debug("Initialized the database and ensured the stocks, positions, and portfolio_snapshots tables exist.")

# Async function to upsert stocks into the database
async def upsert_stock(db: aiosqlite.Connection, stock_data: dict) -> Optional[int]:
    try:
        await db.execute('''
            INSERT INTO stocks (ticker, name, exchange, currency)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name=excluded.name,
                exchange=excluded.exchange,
                currency=excluded.currency
        ''', (
            stock_data.get('symbol'),
            stock_data.get('longName'),
            stock_data.get('exchange'),
            stock_data.get('currency', 'USD')
        ))
        await db.commit()
        cursor = await db.execute('SELECT id FROM stocks WHERE ticker = ?', (stock_data.get('symbol'),))
        row = await cursor.fetchone()
        if row:
            logger.debug(f"Upserted stock {stock_data.get('symbol')} with ID {row[0]}")
            return row[0]
    except Exception as e:
        logger.error(f"Error upserting stock data {stock_data.get('symbol')}: {e}")
    return None

# Async function to upsert positions into the database
async def upsert_position(db: aiosqlite.Connection, stock_id: int, quantity: int, usd_price: float, total_usd: float, percentage: float, date: int):
    try:
        await db.execute('''
            INSERT INTO positions (stock_id, quantity, usd_price, total_usd_price, percentage, date)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                quantity=excluded.quantity,
                usd_price=excluded.usd_price,
                total_usd_price=excluded.total_usd_price,
                percentage=excluded.percentage
        ''', (stock_id, quantity, usd_price, total_usd, percentage, date))
        logger.debug(f"Upserted position for stock_id {stock_id} at date {date}")
    except Exception as e:
        logger.error(f"Error upserting position for stock_id {stock_id} at date {date}: {e}")

# Async function to update portfolio
async def update_portfolio(portfolio: Portfolio):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await init_db(db)
        total_value = portfolio.get_total_value()
        if total_value == 0:
            logger.warning("Total portfolio value is zero. Exiting update.")
            return

        for position in portfolio.positions:
            # Fetch stock data and upsert
            stock_info = await fetch_stock_data(position.stock.ticker)
            if not stock_info:
                logger.warning(f"Skipping position {position.stock.ticker} due to fetch error.")
                continue  # Skip if stock data is not available
            stock = Stock(
                ticker=stock_info.get('symbol'),
                name=stock_info.get('longName', ''),
                exchange=stock_info.get('exchange', ''),
                currency=stock_info.get('currency', 'USD'),
                usd_price=stock_info.get('regularMarketPrice', 0.0),
                timestamp=int(time.time())
            )
            stock_id = await upsert_stock(db, stock.dict())
            if not stock_id:
                logger.warning(f"Skipping position {position.stock.ticker} due to stock upsert error.")
                continue  # Skip if stock upsert failed

            # Handle currency conversion
            if stock.currency != 'USD':
                conversion_rate = await fetch_currency_rate(stock.currency, 'USD')
                if not conversion_rate:
                    logger.warning(f"Skipping position {position.stock.ticker} due to missing currency conversion rate.")
                    continue  # Skip if conversion rate is unavailable
                usd_price = stock.usd_price * conversion_rate
            else:
                usd_price = stock.usd_price

            total_usd = position.quantity * usd_price
            percentage = (total_usd / total_value) * 100
            date = stock.timestamp

            await upsert_position(db, stock_id, position.quantity, usd_price, total_usd, percentage, date)

        # Insert portfolio snapshot
        try:
            await db.execute('''
                INSERT INTO portfolio_snapshots (date, total_value)
                VALUES (?, ?)
                ON CONFLICT(date) DO NOTHING
            ''', (int(time.time()), total_value))
            await db.commit()
            logger.debug(f"Inserted portfolio snapshot: {total_value} at {int(time.time())}")
        except Exception as e:
            logger.error(f"Error inserting portfolio snapshot: {e}")
            raise HTTPException(status_code=500, detail="Failed to create portfolio snapshot")

    logger.info("Portfolio update completed.")

# Async function to fetch and display portfolio summary
async def display_portfolio_summary():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Fetch all positions and related stock info
        query = '''
            SELECT stocks.ticker, stocks.exchange, stocks.currency, positions.quantity, positions.usd_price,
                   positions.total_usd_price, positions.percentage, positions.date
            FROM positions
            JOIN stocks ON positions.stock_id = stocks.id
            ORDER BY positions.percentage DESC
        '''
        cursor = await db.execute(query)
        rows = await cursor.fetchall()

    position_data_display = []
    for row in rows:
        ticker, exchange, currency, quantity, usd_price, total_usd, percentage, date = row
        formatted_time = datetime.fromtimestamp(date).strftime('%Y-%m-%d %H:%M:%S') if date else 'N/A'
        position_data_display.append([
            ticker,
            exchange,
            currency,
            quantity,
            f"{usd_price:.2f}",
            f"{total_usd:.2f}",
            f"{percentage:.2f}%",
            formatted_time
        ])

    # Calculate total portfolio value
    total_value = sum(float(row[5]) for row in rows)

    # Sort positions by percentage descending
    position_data_display.sort(key=lambda x: float(x[6].strip('%')), reverse=True)

    # Display the table
    print(tabulate(position_data_display,
                   headers=['Ticker', 'Exchange', 'Currency', 'Quantity', 'USD Price', 'Total USD Value', '% of Portfolio', 'Time'],
                   tablefmt='psql',
                   floatfmt='.2f'
                   ))

    print(f'\nTotal Portfolio Value: ${total_value:.2f}')

    # Generate a pie chart
    if rows:
        labels = [row[0] for row in rows]
        sizes = [float(row[5]) for row in rows]
        plt.figure(figsize=(10, 7))
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.title('Portfolio Distribution')
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        plt.show()
    else:
        print("No positions to display.")

# Async function to generate performance report
async def generate_performance_report():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = '''
            SELECT date, total_value
            FROM portfolio_snapshots
            ORDER BY date ASC
        '''
        cursor = await db.execute(query)
        rows = await cursor.fetchall()

    if not rows:
        print("No portfolio snapshots available to generate a report.")
        return

    dates = [datetime.fromtimestamp(row[0]) for row in rows]
    values = [row[1] for row in rows]

    # Display the table
    table_data = [
        [
            date.strftime('%Y-%m-%d %H:%M:%S'),
            f"${value:.2f}"
        ]
        for date, value in zip(dates, values)
    ]

    print(tabulate(table_data, headers=['Date', 'Total Portfolio Value'], tablefmt='psql', floatfmt='.2f'))

    # Generate a line chart for portfolio growth over time
    plt.figure(figsize=(12, 6))
    plt.plot(dates, values, marker='o', linestyle='-')
    plt.title('Portfolio Growth Over Time')
    plt.xlabel('Date')
    plt.ylabel('Total Portfolio Value (USD)')
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    logger.info("Performance report generated successfully.")

# Async function to generate optimization report (Placeholder)
async def generate_optimization_report():
    # Implement portfolio optimization logic here
    # For example, using Modern Portfolio Theory, Sharpe Ratio, etc.
    optimization_recommendations = "Optimization feature is under development."
    return optimization_recommendations