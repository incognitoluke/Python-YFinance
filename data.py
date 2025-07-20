from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import sqlite3
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Database setup
DATABASE = 'watchlist.db'

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create watchlist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default stocks if table is empty
    cursor.execute('SELECT COUNT(*) FROM watchlist')
    if cursor.fetchone()[0] == 0:
        default_stocks = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA']
        cursor.executemany('INSERT INTO watchlist (symbol) VALUES (?)', [(s,) for s in default_stocks])
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Watchlist API endpoints
@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    """Get all symbols in the watchlist"""
    try:
        conn = get_db_connection()
        watchlist = conn.execute(
            'SELECT symbol, added_date FROM watchlist ORDER BY added_date'
        ).fetchall()
        conn.close()
        
        result = []
        for item in watchlist:
            result.append({
                'symbol': item['symbol'],
                'added_date': item['added_date']
            })
        
        return jsonify({
            'watchlist': result,
            'count': len(result)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/watchlist/<symbol>', methods=['POST'])
def add_to_watchlist(symbol):
    """Add a symbol to the watchlist"""
    try:
        symbol = symbol.upper()
        
        # Validate symbol by checking if it exists
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Check if we can get basic info (this validates the symbol)
        if not info.get('symbol') and not info.get('longName'):
            return jsonify({'error': 'Invalid symbol'}), 400
        
        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO watchlist (symbol) VALUES (?)',
                (symbol,)
            )
            conn.commit()
            
            result = {
                'symbol': symbol,
                'message': f'{symbol} added to watchlist',
                'company_name': info.get('longName', 'N/A')
            }
            
        except sqlite3.IntegrityError:
            conn.rollback()
            return jsonify({'error': f'{symbol} already in watchlist'}), 409
        finally:
            conn.close()
        
        return jsonify(result), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
def remove_from_watchlist(symbol):
    """Remove a symbol from the watchlist"""
    try:
        symbol = symbol.upper()
        
        conn = get_db_connection()
        cursor = conn.execute('DELETE FROM watchlist WHERE symbol = ?', (symbol,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': f'{symbol} not found in watchlist'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'symbol': symbol,
            'message': f'{symbol} removed from watchlist'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Remove the shares update endpoint
@app.route('/api/watchlist/data')
def get_watchlist_with_data():
    """Get watchlist with current stock data"""
    try:
        # Get watchlist from database
        conn = get_db_connection()
        watchlist_items = conn.execute(
            'SELECT symbol FROM watchlist ORDER BY added_date'
        ).fetchall()
        conn.close()
        
        if not watchlist_items:
            return jsonify({
                'watchlist': []
            })
        
        symbols = [item['symbol'] for item in watchlist_items]
        
        # Get stock data for all symbols
        period = request.args.get('period', '1d')
        interval = request.args.get('interval', '5m')
        
        results = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period, interval=interval)
                info = ticker.info

                if not hist.empty:
                    data = []
                    for index, row in hist.iterrows():
                        if interval in ['1m', '2m', '5m', '15m', '30m']:
                            # Convert to standard time format (12-hour with AM/PM)
                            hour = index.hour
                            minute = index.minute
                            if hour == 0:
                                time_str = f"12:{minute:02d} AM"
                            elif hour < 12:
                                time_str = f"{hour}:{minute:02d} AM"
                            elif hour == 12:
                                time_str = f"12:{minute:02d} PM"
                            else:
                                time_str = f"{hour-12}:{minute:02d} PM"
                            abbreviated_date = time_str
                        elif interval in ['1h', '90m']:
                            # Convert to standard time format for hourly
                            hour = index.hour
                            if hour == 0:
                                abbreviated_date = "12:00 AM"
                            elif hour < 12:
                                abbreviated_date = f"{hour}:00 AM"
                            elif hour == 12:
                                abbreviated_date = "12:00 PM"
                            else:
                                abbreviated_date = f"{hour-12}:00 PM"
                        elif interval == '1d':
                            abbreviated_date = index.strftime('%m/%d')
                        elif interval == '1wk':
                            # For 1-week view, show day of week
                            abbreviated_date = index.strftime('%a')  # Mon, Tue, Wed, etc.
                        elif interval == '1mo':
                            # For 1-month view, show date
                            abbreviated_date = index.strftime('%m/%d')
                        elif interval in ['3mo', '6mo']:
                            # For longer periods, show month/year
                            abbreviated_date = index.strftime('%b %y')
                        else:
                            # For 5-year charts and others, show just the year
                            abbreviated_date = index.strftime('%Y')

                        data.append({
                            'date': abbreviated_date,
                            'price': round(float(row['Close']), 2)
                        })

                    current_price = round(float(hist['Close'].iloc[-1]), 2)
                    previous_price = round(float(hist['Close'].iloc[-2]), 2) if len(hist) > 1 else current_price
                    
                    results[symbol] = {
                        'company_name': info.get('longName', 'N/A'),
                        'data': data,
                        'current_price': current_price,
                        'previous_price': previous_price
                    }
                else:
                    results[symbol] = {'error': 'No data found'}

            except Exception as e:
                results[symbol] = {'error': str(e)}
        
        watchlist_data = []
        for symbol in symbols:
            stock_data = results.get(symbol)
            if stock_data and not stock_data.get('error'):
                current_price = stock_data['current_price']
                previous_price = stock_data['previous_price']
                
                change = current_price - previous_price
                change_percent = (change / previous_price) * 100 if previous_price != 0 else 0
                
                watchlist_data.append({
                    'symbol': symbol,
                    'name': stock_data['company_name'],
                    'price': current_price,
                    'change': change,
                    'changePercent': change_percent
                })
        
        return jsonify({
            'watchlist': watchlist_data,
            'count': len(watchlist_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Original stock data endpoints (unchanged)
@app.route('/api/stock/<symbol>')
def get_stock_data(symbol):
    try:
        period = request.args.get('period', '1d')
        interval = request.args.get('interval', '5m')

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        info = ticker.info

        if hist.empty:
            return jsonify({'error': f'No data found for symbol {symbol}'}), 404

        data = []
        for index, row in hist.iterrows():
            if interval in ['1m', '2m', '5m', '15m', '30m']:
                # Convert to standard time format (12-hour with AM/PM)
                hour = index.hour
                minute = index.minute
                if hour == 0:
                    time_str = f"12:{minute:02d} AM"
                elif hour < 12:
                    time_str = f"{hour}:{minute:02d} AM"
                elif hour == 12:
                    time_str = f"12:{minute:02d} PM"
                else:
                    time_str = f"{hour-12}:{minute:02d} PM"
                abbreviated_date = time_str
            elif interval in ['1h', '90m']:
                # Convert to standard time format for hourly
                hour = index.hour
                if hour == 0:
                    abbreviated_date = "12:00 AM"
                elif hour < 12:
                    abbreviated_date = f"{hour}:00 AM"
                elif hour == 12:
                    abbreviated_date = "12:00 PM"
                else:
                    abbreviated_date = f"{hour-12}:00 PM"
            elif interval == '1d':
                abbreviated_date = index.strftime('%m/%d')
            elif interval == '1wk':
                # For 1-week view, show day of week
                abbreviated_date = index.strftime('%a')  # Mon, Tue, Wed, etc.
            elif interval == '1mo':
                # For 1-month view, show date
                abbreviated_date = index.strftime('%m/%d')
            elif interval in ['3mo', '6mo']:
                # For longer periods, show month/year
                abbreviated_date = index.strftime('%b %y')
            else:
                # For 5-year charts and others, show just the year
                abbreviated_date = index.strftime('%Y')

            data.append({
                'date': abbreviated_date,
                'full_date': index.isoformat(),
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
                'volume': int(row['Volume']),
                'price': round(float(row['Close']), 2)
            })

        return jsonify({
            'symbol': symbol.upper(),
            'company_name': info.get('longName', 'N/A'),
            'period': period,
            'interval': interval,
            'data': data,
            'count': len(data)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/<symbol>/simple')
def get_simple_stock_data(symbol):
    try:
        period = request.args.get('period', '1d')
        interval = request.args.get('interval', '5m')

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return jsonify({'error': f'No data found for symbol {symbol}'}), 404

        dates = []
        prices = []

        for index, row in hist.iterrows():
            if interval in ['1m', '2m', '5m', '15m', '30m']:
                # Convert to standard time format (12-hour with AM/PM)
                hour = index.hour
                minute = index.minute
                if hour == 0:
                    time_str = f"12:{minute:02d} AM"
                elif hour < 12:
                    time_str = f"{hour}:{minute:02d} AM"
                elif hour == 12:
                    time_str = f"12:{minute:02d} PM"
                else:
                    time_str = f"{hour-12}:{minute:02d} PM"
                abbreviated_date = time_str
            elif interval in ['1h', '90m']:
                # Convert to standard time format for hourly
                hour = index.hour
                if hour == 0:
                    abbreviated_date = "12:00 AM"
                elif hour < 12:
                    abbreviated_date = f"{hour}:00 AM"
                elif hour == 12:
                    abbreviated_date = "12:00 PM"
                else:
                    abbreviated_date = f"{hour-12}:00 PM"
            elif interval == '1d':
                abbreviated_date = index.strftime('%m/%d')
            elif interval == '1wk':
                # For 1-week view, show day of week
                abbreviated_date = index.strftime('%a')  # Mon, Tue, Wed, etc.
            elif interval == '1mo':
                # For 1-month view, show date
                abbreviated_date = index.strftime('%m/%d')
            elif interval in ['3mo', '6mo']:
                # For longer periods, show month/year
                abbreviated_date = index.strftime('%b %y')
            else:
                # For 5-year charts and others, show just the year
                abbreviated_date = index.strftime('%Y')

            dates.append(abbreviated_date)
            prices.append(round(float(row['Close']), 2))

        return jsonify({
            'symbol': symbol.upper(),
            'dates': dates,
            'prices': prices
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/<symbol>/current')
def get_current_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period='1d', interval='1m')

        if hist.empty:
            return jsonify({'error': f'No data found for symbol {symbol}'}), 404

        current_price = round(float(hist['Close'].iloc[-1]), 2)

        return jsonify({
            'symbol': symbol.upper(),
            'current_price': current_price,
            'company_name': info.get('longName', 'N/A'),
            'market_cap': info.get('marketCap', 'N/A'),
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'last_updated': hist.index[-1].isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/<symbol>/intraday')
def get_intraday_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1d', interval='1m')

        if hist.empty:
            return jsonify({'error': f'No data found for symbol {symbol}'}), 404

        data = []
        for index, row in hist.iterrows():
            time_str = index.strftime('%H:%M')
            data.append({
                'name': time_str,
                'value': round(float(row['Close']), 2),
                'volume': int(row['Volume'])
            })

        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/multiple')
def get_multiple_stocks():
    try:
        symbols_param = request.args.get('symbols', 'AAPL')
        symbols = [s.strip().upper() for s in symbols_param.split(',')]

        period = request.args.get('period', '1d')
        interval = request.args.get('interval', '5m')

        results = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period, interval=interval)
                info = ticker.info

                if not hist.empty:
                    data = []
                    for index, row in hist.iterrows():
                        if interval in ['1m', '2m', '5m', '15m', '30m']:
                            # Convert to standard time format (12-hour with AM/PM)
                            hour = index.hour
                            minute = index.minute
                            if hour == 0:
                                time_str = f"12:{minute:02d} AM"
                            elif hour < 12:
                                time_str = f"{hour}:{minute:02d} AM"
                            elif hour == 12:
                                time_str = f"12:{minute:02d} PM"
                            else:
                                time_str = f"{hour-12}:{minute:02d} PM"
                            abbreviated_date = time_str
                        elif interval in ['1h', '90m']:
                            # Convert to standard time format for hourly
                            hour = index.hour
                            if hour == 0:
                                abbreviated_date = "12:00 AM"
                            elif hour < 12:
                                abbreviated_date = f"{hour}:00 AM"
                            elif hour == 12:
                                abbreviated_date = "12:00 PM"
                            else:
                                abbreviated_date = f"{hour-12}:00 PM"
                        elif interval == '1d':
                            abbreviated_date = index.strftime('%m/%d')
                        elif interval == '1wk':
                            # For 1-week view, show day of week
                            abbreviated_date = index.strftime('%a')  # Mon, Tue, Wed, etc.
                        elif interval == '1mo':
                            # For 1-month view, show date
                            abbreviated_date = index.strftime('%m/%d')
                        elif interval in ['3mo', '6mo']:
                            # For longer periods, show month/year
                            abbreviated_date = index.strftime('%b %y')
                        else:
                            # For 5-year charts and others, show just the year
                            abbreviated_date = index.strftime('%Y')

                        data.append({
                            'date': abbreviated_date,
                            'price': round(float(row['Close']), 2)
                        })

                    results[symbol] = {
                        'company_name': info.get('longName', 'N/A'),
                        'data': data,
                        'current_price': round(float(hist['Close'].iloc[-1]), 2)
                    }
                else:
                    results[symbol] = {'error': 'No data found'}

            except Exception as e:
                results[symbol] = {'error': str(e)}

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Stock Data API',
        'database': 'connected' if os.path.exists(DATABASE) else 'not found'
    })

@app.route('/api/info')
def api_info():
    endpoints = {
        'watchlist_endpoints': {
            '/api/watchlist': {
                'GET': 'Get all watchlist symbols',
                'example': '/api/watchlist'
            },
            '/api/watchlist/<symbol>': {
                'POST': 'Add symbol to watchlist',
                'DELETE': 'Remove symbol from watchlist',
                'example': '/api/watchlist/AAPL'
            },
            '/api/watchlist/data': {
                'GET': 'Get watchlist with current stock data',
                'example': '/api/watchlist/data'
            }
        },
        'stock_endpoints': {
            '/api/stock/<symbol>': {
                'description': 'Get historical stock data',
                'parameters': ['period', 'interval'],
                'example': '/api/stock/AAPL?period=1d&interval=5m'
            },
            '/api/stock/<symbol>/simple': {
                'description': 'Get simplified stock data (dates and prices)',
                'example': '/api/stock/AAPL/simple'
            },
            '/api/stock/<symbol>/current': {
                'description': 'Get current price and basic info',
                'example': '/api/stock/AAPL/current'
            },
            '/api/stock/<symbol>/intraday': {
                'description': "Get today's intraday data",
                'example': '/api/stock/AAPL/intraday'
            },
            '/api/stocks/multiple': {
                'description': 'Get data for multiple stocks',
                'parameters': ['symbols'],
                'example': '/api/stocks/multiple?symbols=AAPL,GOOGL,MSFT'
            }
        },
        'valid_periods': ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'],
        'valid_intervals': ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
    }
    return jsonify(endpoints)

if __name__ == '__main__':
    print("Initializing database...")
    init_db()
    print("Starting Stock Data API Server with Database...")
    print("Available endpoints:")
    print("Watchlist endpoints:")
    print("- GET /api/watchlist")
    print("- POST /api/watchlist/AAPL")
    print("- DELETE /api/watchlist/AAPL")
    print("- GET /api/watchlist/data")
    print("\nStock endpoints:")
    print("- GET /api/stock/AAPL")
    print("- GET /api/stock/AAPL/simple")
    print("- GET /api/stock/AAPL/current")
    print("- GET /api/stock/AAPL/intraday")
    print("- GET /api/stocks/multiple?symbols=AAPL,GOOGL")
    print("- GET /api/health")
    print("- GET /api/info")

    app.run(debug=True, host='0.0.0.0', port=5000)