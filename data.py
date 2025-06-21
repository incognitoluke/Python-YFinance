from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

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
                abbreviated_date = index.strftime('%H:%M')
            elif interval in ['1h', '90m']:
                abbreviated_date = index.strftime('%I:%M %p')
            elif interval == '1d':
                abbreviated_date = index.strftime('%m/%d')
            elif interval in ['1wk', '1mo']:
                abbreviated_date = index.strftime('%b %y')
            else:
                abbreviated_date = index.strftime('%m/%d/%y')

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
                abbreviated_date = index.strftime('%H:%M')
            elif interval in ['1h', '90m']:
                abbreviated_date = index.strftime('%I:%M %p')
            elif interval == '1d':
                abbreviated_date = index.strftime('%m/%d')
            elif interval in ['1wk', '1mo']:
                abbreviated_date = index.strftime('%b %y')
            else:
                abbreviated_date = index.strftime('%m/%d/%y')

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
                            abbreviated_date = index.strftime('%H:%M')
                        elif interval in ['1h', '90m']:
                            abbreviated_date = index.strftime('%I:%M %p')
                        elif interval == '1d':
                            abbreviated_date = index.strftime('%m/%d')
                        elif interval in ['1wk', '1mo']:
                            abbreviated_date = index.strftime('%b %y')
                        else:
                            abbreviated_date = index.strftime('%m/%d/%y')

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
        'service': 'Stock Data API'
    })

@app.route('/api/info')
def api_info():
    endpoints = {
        'endpoints': {
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
    print("Starting Stock Data API Server...")
    print("Available endpoints:")
    print("- GET /api/stock/AAPL")
    print("- GET /api/stock/AAPL/simple")
    print("- GET /api/stock/AAPL/current")
    print("- GET /api/stock/AAPL/intraday")
    print("- GET /api/stocks/multiple?symbols=AAPL,GOOGL")
    print("- GET /api/health")
    print("- GET /api/info")

    app.run(debug=True, host='0.0.0.0', port=5000)
